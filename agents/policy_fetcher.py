"""
Policy Fetcher Agent — LangGraph pipeline that:

  1. extract_params  — LLM maps UserRequirements → CrawlerParams (structured output)
  2. call_crawler    — invokes the Playwright crawler tool
  3. parse_policies  — LLM normalises every raw policy dict into NormalizedPolicy
                       (handles arbitrary field names / value formats from the crawler)
  4. check_download  — programmatically checks / downloads missing PDFs

Each step is timed and logged so you can see exactly where time is spent.
"""

import json
import logging
import operator
import os
import subprocess
import time
from pathlib import Path
from typing import Annotated, Callable, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from schema.models import UserRequirements
from tools.policy_tools import check_policy_exists, download_policy_pdf

logger = logging.getLogger(__name__)
load_dotenv()

_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))


# ── Timing helper ─────────────────────────────────────────────────────────────

class _Timer:
    def __init__(self, label: str):
        self.label = label
        self._start = None

    def __enter__(self):
        self._start = time.perf_counter()
        logger.info("[PolicyFetcher] ▶ %s …", self.label)
        return self

    def __exit__(self, *_):
        elapsed = time.perf_counter() - self._start
        logger.info("[PolicyFetcher] ✓ %s  %.2fs", self.label, elapsed)


# ── Pydantic models ───────────────────────────────────────────────────────────

class CrawlerParams(BaseModel):
    product_type: str  = Field(description="One of: term, whole, endowment")
    dob: str           = Field(description="Date of birth DD/MM/YYYY")
    gender: str        = Field(description="M or F")
    smoker: bool       = Field(description="True if applicant smokes")
    ci: bool           = Field(description="True if Critical Illness benefit is required")
    sum_assured:    int = Field(default=500000, description="Sum assured SGD (term/whole)")
    coverage_term:  int = Field(default=20, description="Coverage term years (term/endowment)")
    premium_term:   int = Field(default=20, description="Premium payment term years (whole)")
    premium_amount: int = Field(default=300, description="Annual premium SGD (endowment)")


class NormalizedPolicy(BaseModel):
    """One policy as it will be stored in state and sent to the frontend."""
    policy_name: str          = Field(description="Full name: '<Insurer> <Product Name>'")
    insurer: str              = Field(description="Insurer company name")
    annual_premium: str       = Field(default="N/A", description="Annual premium, e.g. 'S$ 266'")
    coverage_term_years: str  = Field(default="N/A", description="Coverage term, e.g. '16' or 'Whole Life'")
    premium_term_years: str   = Field(default="N/A", description="Premium term, e.g. '16'")
    total_premium: str        = Field(default="N/A", description="Total premium payable")
    distribution_cost: str    = Field(default="N/A", description="Distribution cost")
    credit_rating: str        = Field(default="N/A", description="Credit rating, e.g. 'A2 (Moody\\'s)'")
    guaranteed_maturity_benefit: str = Field(default="N/A", description="Guaranteed maturity benefit (endowment only)")
    product_summary_url: str  = Field(default="", description="URL to product summary PDF")
    brochure_url: str         = Field(default="", description="URL to brochure PDF")


class NormalizedPoliciesList(BaseModel):
    policies: List[NormalizedPolicy]


# ── LangGraph state ───────────────────────────────────────────────────────────

class FetcherState(TypedDict):
    requirements_text: str
    crawler_params: Optional[dict]
    raw_json: str                              # raw JSON string from crawler
    normalized: List[dict]                     # after LLM parse
    enriched: List[dict]                       # after check / download
    messages: Annotated[List, operator.add]


# ── Crawler LangChain tool ─────────────────────────────────────────────────────

@tool
def crawl_comparefirst(
    product_type: str,
    dob: str,
    gender: str,
    smoker: bool,
    ci: bool,
    count: int = 10,
    sum_assured: int = 500000,
    coverage_term: int = 20,
    premium_term: int = 20,
    premium_amount: int = 300,
) -> str:
    """
    Crawl comparefirst.sg and return the top N life-insurance policies
    (ranked lowest-premium-first) as a JSON string.

    Args:
        product_type:   One of "term", "whole", "endowment".
        dob:            Date of birth in DD/MM/YYYY format.
        gender:         "M" or "F".
        smoker:         True if the applicant smokes.
        ci:             True if Critical Illness benefit is required.
        count:          How many policies to return (default 10).
        sum_assured:    Desired sum assured in SGD (term / whole life).
        coverage_term:  Coverage term in years (term / endowment).
        premium_term:   Premium payment term in years (whole life).
        premium_amount: Annual premium amount in SGD (endowment only).
    """
    from tools.policyCrawler.crawler import crawl_policies
    try:
        print("[Fetching Policies]: Searching for " + product_type + " policies for " + dob + " " + gender + " " + str(smoker) + " " + str(ci) + " " + str(sum_assured) + " " + str(coverage_term) + " " + str(premium_term) + " " + str(premium_amount))
        results = crawl_policies(
            product_type=product_type,
            dob=dob,
            gender=gender,
            smoker=smoker,
            ci=ci,
            sum_assured=sum_assured,
            premium_amount=premium_amount,
            coverage_term=coverage_term,
            premium_term=premium_term,
            count=count,
            headless=True,
        )
        return json.dumps(results, ensure_ascii=False)
    except Exception as exc:
        logger.error("[PolicyFetcher] crawl_comparefirst error: %s", exc, exc_info=True)
        return json.dumps({"error": str(exc)})


# ── Graph nodes ───────────────────────────────────────────────────────────────

def _node_extract_params(state: FetcherState) -> dict:
    """LLM: UserRequirements text → CrawlerParams."""
    with _Timer("extract_params (LLM)"):
        extractor = _llm.with_structured_output(CrawlerParams)
        prompt = (
            "You are a parameter extractor for a life-insurance policy crawler.\n\n"
            "Given the user's insurance requirements, extract the crawler parameters.\n\n"
            "Rules:\n"
            "- product_type: pick the most appropriate among 'term', 'whole', 'endowment'. Default 'term'.\n"
            "- dob: convert any age / dob to DD/MM/YYYY. If only age given, use 01/01/<current_year - age>.\n"
            "- gender: 'M' for male, 'F' for female. Default 'M'.\n"
            "- smoker: True only if explicitly mentioned as smoker.\n"
            "- ci: True if critical illness / CI benefit mentioned.\n"
            "- sum_assured: desired coverage in SGD. Default 500000.\n"
            "- coverage_term: years. Default 20.\n"
            "- premium_term: payment term years (whole life). Default 20.\n"
            "- premium_amount: annual premium for endowment. Default 300.\n\n"
            f"User requirements:\n{state['requirements_text']}"
        )
        try:
            params: CrawlerParams = extractor.invoke([SystemMessage(content=prompt)])
            logger.info("[PolicyFetcher] Extracted params: %s", params.model_dump())
            return {"crawler_params": params.model_dump()}
        except Exception as exc:
            logger.error("[PolicyFetcher] param extraction failed: %s", exc)
            defaults = CrawlerParams(
                product_type="term", dob="01/01/1990",
                gender="M", smoker=False, ci=False,
            )
            return {"crawler_params": defaults.model_dump()}


def _node_call_crawler(state: FetcherState) -> dict:
    """Call the crawler with the extracted params."""
    p = state["crawler_params"]
    logger.info(
        "[PolicyFetcher] Crawling — type=%s dob=%s gender=%s smoker=%s ci=%s "
        "sa=%s cov=%sy prem_term=%sy pa=%s",
        p["product_type"], p["dob"], p["gender"],
        p["smoker"], p["ci"],
        p["sum_assured"], p["coverage_term"], p["premium_term"], p["premium_amount"],
    )
    with _Timer(f"crawl_comparefirst ({p['product_type']})"):
        raw = crawl_comparefirst.invoke(p)
    logger.info("[PolicyFetcher] Crawler raw output (%d chars)", len(raw))
    return {"raw_json": raw}


def _node_parse_policies(state: FetcherState) -> dict:
    """LLM: raw crawler JSON → List[NormalizedPolicy]."""
    raw = state["raw_json"]

    # Sanity-check for crawler error
    try:
        probe = json.loads(raw)
        if isinstance(probe, dict) and "error" in probe:
            logger.error("[PolicyFetcher] Crawler returned error: %s", probe["error"])
            return {"normalized": []}
    except json.JSONDecodeError:
        logger.error("[PolicyFetcher] Crawler returned non-JSON: %s", raw[:200])
        return {"normalized": []}

    with _Timer("parse_policies (LLM)"):
        parser = _llm.with_structured_output(NormalizedPoliciesList)
        prompt = (
            "You are a data normaliser for insurance policy records.\n\n"
            "Given a JSON array of raw policy objects from a web crawler, "
            "normalise each one into the required structured format.\n\n"
            "Rules:\n"
            "- policy_name: '<insurer> <product_name>' (combine both fields).\n"
            "- annual_premium: keep the 'S$ NNN' string but ensure exactly one 'S$' prefix "
            "and a clean number. Remove duplicated currency symbols.\n"
            "- coverage_term_years / premium_term_years: extract just the number of years "
            "as a string (e.g. '16'). If 'Whole Life' keep as 'Whole Life'.\n"
            "- total_premium / distribution_cost: keep 'S$ NNN' format or 'N/A'.\n"
            "- credit_rating: keep the full rating string, e.g. 'A2 (Moody\\'s)'.\n"
            "- guaranteed_maturity_benefit: keep 'S$ NNN' or 'N/A'.\n"
            "- URLs: keep exactly as-is.\n\n"
            f"Raw crawler output:\n{raw}"
        )
        try:
            result: NormalizedPoliciesList = parser.invoke([SystemMessage(content=prompt)])
            policies = [p.model_dump() for p in result.policies]
            logger.info("[PolicyFetcher] LLM normalised %d policies", len(policies))
            for i, p in enumerate(policies):
                logger.info(
                    "  [%d] %s | premium=%s | cover=%sy | rating=%s",
                    i + 1, p["policy_name"], p["annual_premium"],
                    p["coverage_term_years"], p["credit_rating"],
                )
            return {"normalized": policies}
        except Exception as exc:
            logger.error("[PolicyFetcher] LLM parse failed: %s", exc, exc_info=True)
            return {"normalized": []}


def _node_check_download(state: FetcherState) -> dict:
    """Programmatically check / download each policy PDF."""
    policies = state["normalized"]
    if not policies:
        return {"enriched": []}

    logger.info("[PolicyFetcher] Checking / downloading %d policies …", len(policies))
    enriched = []

    for i, p in enumerate(policies):
        policy_name = p.get("policy_name", "")
        product_summary_url = p.get("product_summary_url", "")
        insurer = p.get("insurer", policy_name.split()[0] if policy_name else "unknown").lower()

        t0 = time.perf_counter()
        exists = check_policy_exists.invoke({"policy_name": policy_name})
        p["local_pdf_available"] = exists
        elapsed_check = time.perf_counter() - t0
        logger.info(
            "  [%d/%d] exists=%s  (%.2fs)  %s",
            i + 1, len(policies), exists, elapsed_check, policy_name,
        )

        if not exists and product_summary_url:
            t1 = time.perf_counter()
            status = download_policy_pdf.invoke({
                "policy_name": policy_name,
                "product_summary_url": product_summary_url,
                "insurer": insurer,
            })
            elapsed_dl = time.perf_counter() - t1
            p["download_status"] = status
            p["local_pdf_available"] = "Already exists" in status or "Downloaded" in status
            logger.info(
                "  [%d/%d] download: %s  (%.2fs)",
                i + 1, len(policies), status[:80], elapsed_dl,
            )
        else:
            p["download_status"] = "Already in local DB" if exists else "No product summary URL"

        enriched.append(p)

    return {"enriched": enriched}

def _node_index_new_policies(state: FetcherState) -> dict:
    """If any policies were downloaded, run prepare_input and run_index."""
    policies = state["enriched"]
    
    needs_indexing = any(
        "Downloaded" in p.get("download_status", "") 
        for p in policies
    )
    
    if needs_indexing:
        logger.info("[PolicyFetcher] New policies downloaded. Triggering GraphRAG indexing...")
        base_dir = Path(__file__).parent.parent
        prepare_script = base_dir / "graphrag" / "prepare_input.py"
        index_script = base_dir / "graphrag" / "run_index.py"
        
        with _Timer("GraphRAG Indexing"):
            try:
                subprocess.run(["uv", "run", "python", str(prepare_script)], check=True)
                subprocess.run(["uv", "run", "python", str(index_script)], check=True)
                logger.info("[PolicyFetcher] GraphRAG indexing completed successfully.")
            except subprocess.CalledProcessError as e:
                logger.error("[PolicyFetcher] GraphRAG indexing failed: %s", e)
    else:
        logger.info("[PolicyFetcher] No new policies downloaded. Skipping GraphRAG indexing.")
        
    return {}

# ── Build graph ───────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(FetcherState)
    g.add_node("extract_params",   _node_extract_params)
    g.add_node("call_crawler",     _node_call_crawler)
    g.add_node("parse_policies",   _node_parse_policies)
    g.add_node("check_download",   _node_check_download)
    g.add_node("index_new_policies", _node_index_new_policies)

    g.add_edge(START,             "extract_params")
    g.add_edge("extract_params",  "call_crawler")
    g.add_edge("call_crawler",    "parse_policies")
    g.add_edge("parse_policies",  "check_download")
    g.add_edge("check_download",  "index_new_policies")
    g.add_edge("index_new_policies", END)

    return g.compile()


_GRAPH = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

class PolicyFetcher:
    """
    Fetch, parse, and locally cache the top-N policies from comparefirst.sg.

    Parameters
    ----------
    count : int
        Number of policies to fetch (default 10).
    """

    def __init__(self, count: int = 10):
        self.count = count

    def fetch(
        self,
        requirements: UserRequirements,
        on_policy_found: Optional[Callable] = None,
    ) -> List[dict]:
        """
        Run the full fetcher pipeline and return a list of normalised policy
        dicts (each with policy_name, annual_premium, coverage_term_years, …).

        on_policy_found is called with each policy dict as it becomes available
        during check_download so the frontend can stream incrementally.
        """
        t_total = time.perf_counter()
        logger.info(
            "[PolicyFetcher] ══════ Starting fetch (count=%d) ══════", self.count
        )

        req_text = requirements.to_text()

        initial: FetcherState = {
            "requirements_text": req_text,
            "crawler_params": None,
            "raw_json": "",
            "normalized": [],
            "enriched": [],
            "messages": [],
        }

        # Inject count into the crawler call via state override
        _original_crawl = _node_call_crawler

        def _crawl_with_count(state: FetcherState) -> dict:
            # Patch count into params before calling
            state = dict(state)
            state["crawler_params"] = {**state["crawler_params"], "count": self.count}
            return _original_crawl(state)

        # Re-compile a fresh graph with the count-patched node
        g = StateGraph(FetcherState)
        g.add_node("extract_params",  _node_extract_params)
        g.add_node("call_crawler",    _crawl_with_count)
        g.add_node("parse_policies",  _node_parse_policies)
        g.add_node("check_download",  self._make_check_download_node(on_policy_found))
        g.add_node("index_new_policies", _node_index_new_policies)

        g.add_edge(START,            "extract_params")
        g.add_edge("extract_params", "call_crawler")
        g.add_edge("call_crawler",   "parse_policies")
        g.add_edge("parse_policies", "check_download")
        g.add_edge("check_download", "index_new_policies")
        g.add_edge("index_new_policies", END)
        app = g.compile()

        final = app.invoke(initial)
        result = final.get("enriched", [])

        elapsed = time.perf_counter() - t_total
        logger.info(
            "[PolicyFetcher] ══════ Done — %d policies in %.2fs ══════",
            len(result), elapsed,
        )
        return result

    @staticmethod
    def _make_check_download_node(on_policy_found: Optional[Callable]):
        """Returns a check_download node that fires the streaming callback."""
        def _node(state: FetcherState) -> dict:
            policies = state["normalized"]
            if not policies:
                return {"enriched": []}

            logger.info(
                "[PolicyFetcher] Checking / downloading %d policies …", len(policies)
            )
            enriched = []

            for i, p in enumerate(policies):
                policy_name = p.get("policy_name", "")
                product_summary_url = p.get("product_summary_url", "")
                insurer = (
                    p.get("insurer", policy_name.split()[0] if policy_name else "unknown")
                    .lower()
                )

                t0 = time.perf_counter()
                exists = check_policy_exists.invoke({"policy_name": policy_name})
                p["local_pdf_available"] = exists
                logger.info(
                    "  [%d/%d] exists=%-5s (%.2fs)  %s",
                    i + 1, len(policies), exists,
                    time.perf_counter() - t0, policy_name,
                )

                if not exists and product_summary_url:
                    t1 = time.perf_counter()
                    status = download_policy_pdf.invoke({
                        "policy_name": policy_name,
                        "product_summary_url": product_summary_url,
                        "insurer": insurer,
                    })
                    p["download_status"] = status
                    p["local_pdf_available"] = (
                        "Already exists" in status or "Downloaded" in status
                    )
                    logger.info(
                        "  [%d/%d] download: %s  (%.2fs)",
                        i + 1, len(policies), status[:80],
                        time.perf_counter() - t1,
                    )
                else:
                    p["download_status"] = (
                        "Already in local DB" if exists else "No product summary URL"
                    )

                enriched.append(p)

                if on_policy_found:
                    try:
                        on_policy_found(dict(p))
                    except Exception as cb_exc:
                        logger.warning(
                            "[PolicyFetcher] on_policy_found error: %s", cb_exc
                        )

            return {"enriched": enriched}

        return _node
