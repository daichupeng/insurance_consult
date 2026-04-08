"""
MD-based retriever — agentic version with tools and verbose logging.

Architecture
------------
For each (policy × scoring item) pair the agent:
  1. Resolves the policy's .md file from raw_policies/ (fuzzy stem match).
  2. Runs a ReAct agent (create_react_agent) that can use:
     - md_local_search (searches the local markdown document)
     - query_expansion (generates search variations)
     - remove_context (flags irrelevant snippets)
     - list_available_policies (check policy inventory)

Verbose Logging
---------------
Explicit print statements are added to ensure clear visibility in the terminal 
during the retrieval process.

Public interface
----------------
    MDRetriever().retrieve(
        criteria        : ScoringCriteria,
        on_policy_done  : Optional[Callable] = None,
        crawled_policies: Optional[List[dict]] = None,
    ) -> List[Policy]

This mirrors GraphRAGRetriever.retrieve() exactly.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from schema.models import Policy, PolicyBasicInfo, ScoringCriteria, ScoringItem
from tools.search_tools import query_expansion, remove_context, list_available_policies
from tools.cache_manager import CacheManager

logger = logging.getLogger(__name__)
load_dotenv()

_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
_PROJECT_ROOT = Path(__file__).parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"

# Initialize Cache Manager
_cache = CacheManager()

MAX_CONCURRENT_TASKS = int(os.getenv("RETRIEVER_MAX_WORKERS", "16"))

# Maximum characters of the MD document sent to the LLM to stay within context window.
# ~120k chars ≈ ~30k tokens — safe for gpt-4o.
_MAX_MD_CHARS = 120_000


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalise(name: str) -> str:
    """Lower-case and strip non-alphanumeric chars for fuzzy file matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find_md_file(policy_name: str) -> Path | None:
    """
    Locate the .md file for *policy_name* under _POLICIES_DIR.
    Matches on the normalised stem (case-insensitive, punctuation-stripped).
    """
    target = _normalise(policy_name)
    if not _POLICIES_DIR.exists():
        return None
    for md in _POLICIES_DIR.rglob("*.md"):
        if _normalise(md.stem) == target:
            return md
    return None


@tool
def md_local_search(query: str, policy_name: str) -> str:
    """
    Searches the local Markdown product summary for a specific insurance policy.
    Uses a multi-layer cache (Answer -> Fragment -> Hard Search).
    
    Args:
        query: The specific detail or question to search for in the document.
        policy_name: The EXACT name of the policy to search within.
    """
    print(f"\n[MD Tool]: Searching document '{policy_name}' for: '{query}'")
    
    # --- Step 1: Layer A Check (Answer) ---
    cached_answer = _cache.get_answer(query)
    if cached_answer:
        print(f"  -> Layer A Cache Hit!")
        return cached_answer

    # --- Step 2: Layer B Check (Fragment) ---
    cached_fragment_data = _cache.get_fragment(query)
    if cached_fragment_data:
        print(f"  -> Layer B Cache Hit! Generating answer from fragment...")
        _, fragment = cached_fragment_data
        prompt = (
            f"You are searching an insurance policy document fragment: {policy_name}.\n\n"
            f"GOAL: Find information relevant to: {query}\n\n"
            f"--- FRAGMENT CONTENT ---\n{fragment}\n--- END ---\n\n"
            "INSTRUCTIONS:\n"
            "Extract every passage relevant to the goal. Quote verbatim where possible. "
            "If the information is not found, clearly state 'Information not found in the fragment'."
        )
        response = _llm.invoke([SystemMessage(content=prompt)])
        result = response.content.strip()
        # Store in Layer A
        _cache.store_cache(query, answer=result)
        return result

    # --- Step 3: Hard Search (Cache Miss) ---
    print(f"  -> Cache Miss. Performing Hard Search on .md file...")
    md_path = _find_md_file(policy_name)
    if not md_path:
        return f"Error: No .md file found for policy '{policy_name}'."
    
    try:
        text = md_path.read_text(encoding="utf-8")
        if len(text) > _MAX_MD_CHARS:
            text = text[:_MAX_MD_CHARS]
            
        prompt = (
            f"You are searching an insurance policy document: {policy_name}.\n\n"
            f"GOAL: Find information relevant to: {query}\n\n"
            f"--- DOCUMENT CONTENT ---\n{text}\n--- END ---\n\n"
            "INSTRUCTIONS:\n"
            "Extract every passage relevant to the goal. Quote verbatim where possible. "
            "If the information is not found, clearly state 'Information not found in the document'."
        )
        
        response = _llm.invoke([SystemMessage(content=prompt)])
        result = response.content.strip()
        
        # Update Cache (Layer B and Layer A)
        # We use the full extracted result as the fragment for Layer B if it's concise
        # otherwise we might need a separate extraction for "context fragment"
        _cache.store_cache(query, answer=result, fragment=result)
        
        print(f"  -> Found {len(result)} chars of relevant context. Cache updated.")
        return result
        
    except Exception as exc:
        return f"Error reading document: {exc}"


# ── Task descriptor ───────────────────────────────────────────────────────────

@dataclass
class _RetrievalTask:
    policy_name: str
    item: ScoringItem
    mode: str          # "filter" | "criterion"
    task_index: int
    policy_index: int


# ── Retriever ─────────────────────────────────────────────────────────────────

class MDRetriever:
    """
    Retriever backed by Markdown policy documents using an agentic approach.
    """

    def __init__(self) -> None:
        self._progress_lock = threading.Lock()
        self._completed = 0
        
        # Start background MD5 watcher
        self._stop_watcher = threading.Event()
        self._watcher_thread = threading.Thread(target=self._run_watcher, daemon=True)
        self._watcher_thread.start()
        
        # Define agent tools
        self.tools = [
            md_local_search,
            query_expansion,
            remove_context,
            list_available_policies
        ]
        
        system_prompt = (
            "You are a specialized Insurance Retrieval Agent. "
            "Your goal is to find evidence for specific filters or scoring criteria "
            "within Markdown policy documents.\n\n"
            "GUIDELINES:\n"
            "1. ALWAYS start by using 'md_local_search' with the provided policy name.\n"
            "2. If the initial search is insufficient, use 'query_expansion' to try alternative terms.\n"
            "3. If multiple attempts fail to find a specific detail (like a credit rating), "
            "report what you DID find and state clearly that the decimal detail is missing.\n"
            "4. Be thorough but concise in your final summary of evidence."
        )
        
        # We create the agent but we'll invoke it per task
        self.agent_executor = create_react_agent(_llm, self.tools, prompt=system_prompt)

    def _run_watcher(self):
        """Periodically syncs file hashes and invalidates cache if needed."""
        while not self._stop_watcher.is_set():
            try:
                invalidated = _cache.sync_and_invalidate()
                if invalidated:
                    print(f"\n[Cache Watcher] Invalidated entries for: {', '.join(invalidated)}")
            except Exception as e:
                logger.error(f"Error in cache watcher: {e}")
            
            # Wait 60 seconds before next check
            self._stop_watcher.wait(60)

    def stop(self):
        """Stops the background watcher."""
        self._stop_watcher.set()
        if self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=1)

    # ── Single-task execution ─────────────────────────────────────────────────

    def _run_task(
        self,
        task: _RetrievalTask,
        total: int,
    ) -> Tuple[_RetrievalTask, List[str]]:
        """
        Runs the ReAct agent for one (policy, item) task.
        """
        t0 = time.perf_counter()
        
        if task.mode == "filter":
            prompt = (
                f"Identify evidence in the policy '{task.policy_name}' for this hard filter:\n"
                f"Filter Requirement: {task.item.description}\n\n"
                "Search the document and provide the specific evidence found."
            )
        else:
            prompt = (
                f"Gather information from the policy '{task.policy_name}' about this scoring item:\n"
                f"Item: {task.item.item}\n"
                f"Description: {task.item.description}\n"
                f"Scoring Rules: {task.item.scoring_rules}\n\n"
                "Search the document and summarize the findings."
            )

        print(f"\n[MDRetriever] 🚀 Starting task {self._completed + 1}/{total}: {task.policy_name} | {task.item.item or task.item.description[:40]}")

        try:
            # Task-specific agent invocation
            # Note: We don't share state between tasks to avoid cross-contamination
            response = self.agent_executor.invoke({"messages": [HumanMessage(content=prompt)]})
            
            # Extract the final answer and any collected evidence from tool outputs
            # In a ReAct agent, the last message is the AI's final response
            final_content = response["messages"][-1].content
            
            # Form context as if it was a list of snippets (compatible with GraphRAG format)
            context = [f"[MDRetriever Agent Output]\n{final_content}"]
            
        except Exception as exc:
            logger.error("[MDRetriever] Task failed for %s: %s", task.policy_name, exc)
            context = []

        with self._progress_lock:
            self._completed += 1
            done = self._completed
            
        elapsed = time.perf_counter() - t0
        print(f"[MDRetriever] ✅ Completed in {elapsed:.1f}s — {task.policy_name} | {task.item.item or task.item.description[:40]}")
        
        return task, context

    # ── Public interface ──────────────────────────────────────────────────────

    def retrieve(
        self,
        criteria: ScoringCriteria,
        on_policy_done: Optional[Callable] = None,
        crawled_policies: Optional[List[dict]] = None,
    ) -> List[Policy]:
        """
        Parallel execution of the MDRetriever Agent across all policy-item pairs.
        """
        # ── Setup policy list ───────────────────────────────────────────────
        crawled_info_list: List[PolicyBasicInfo] = []
        crawled_return_rates: List[float] = []

        if crawled_policies is not None:
            available_policies: List[str] = []
            for p in crawled_policies:
                name = p.get("policy_name", "")
                if name:
                    available_policies.append(name)
                    crawled_return_rates.append(float(p.get("return_rate", 0.0)))
                    crawled_info_list.append(PolicyBasicInfo(
                        insurer=p.get("insurer", ""),
                        sub_type=p.get("sub_type", ""),
                        sub_information=p.get("sub_information", ""),
                        annual_premium=p.get("annual_premium", "N/A"),
                        coverage_term_years=p.get("coverage_term_years", "N/A"),
                        premium_term_years=p.get("premium_term_years", "N/A"),
                        total_premium=p.get("total_premium", "N/A"),
                        distribution_cost=p.get("distribution_cost", "N/A"),
                        credit_rating=p.get("credit_rating", "N/A"),
                        guaranteed_maturity_benefit=p.get("guaranteed_maturity_benefit", "N/A"),
                        product_summary_url=p.get("product_summary_url", ""),
                        brochure_url=p.get("brochure_url", ""),
                    ))
            print(f"[MDRetriever] Using {len(available_policies)} crawled policies from session.")
        else:
            # Fall back to discovering policies via .md files on disk
            available_policies = (
                [f.stem for f in sorted(_POLICIES_DIR.rglob("*.md"))]
                if _POLICIES_DIR.exists() else []
            )
            print(f"[MDRetriever] No session policies provided. Found {len(available_policies)} policies on disk.")

        if not available_policies:
            logger.warning("[MDRetriever] No policy documents found.")
            return []

        # ── Build task list ───────────────────────────────────────────────
        tasks: List[_RetrievalTask] = []
        idx = 0
        for policy_idx, policy_name in enumerate(available_policies):
            for f_text in (criteria.filters or []):
                tasks.append(_RetrievalTask(
                    policy_name=policy_name,
                    item=ScoringItem(item="Hard Filter", description=f_text,
                                     scoring_rules="N/A", weight=0),
                    mode="filter",
                    task_index=idx,
                    policy_index=policy_idx,
                ))
                idx += 1
            for crit_item in (criteria.criteria or []):
                tasks.append(_RetrievalTask(
                    policy_name=policy_name,
                    item=crit_item,
                    mode="criterion",
                    task_index=idx,
                    policy_index=policy_idx,
                ))
                idx += 1

        total = len(tasks)
        n_workers = min(total, MAX_CONCURRENT_TASKS)
        self._completed = 0

        print(f"\n[MDRetriever] ══════ Running {total} tasks concurrently (Workers: {n_workers}) ══════")

        # ── Execution ─────────────────────────────────────────────────────
        n_filters = len(criteria.filters or [])
        n_criteria = len(criteria.criteria or [])
        tasks_per_policy = n_filters + n_criteria

        policy_lock = threading.Lock()
        policy_done_counts: Dict[int, int] = defaultdict(int)
        policy_ctx: Dict[int, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        results: Dict[int, List[str]] = {}

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_map = {
                executor.submit(self._run_task, task, total): task
                for task in tasks
            }
            for future in as_completed(future_map):
                try:
                    completed_task, context = future.result()
                    results[completed_task.task_index] = context
                except Exception as exc:
                    failed = future_map[future]
                    results[failed.task_index] = []
                    completed_task = failed
                    context = []

                if on_policy_done and tasks_per_policy > 0:
                    with policy_lock:
                        pidx = completed_task.policy_index
                        pname = completed_task.policy_name
                        item_key = (
                            completed_task.item.description
                            if completed_task.mode == "filter"
                            else completed_task.item.item
                        )
                        policy_ctx[pidx][item_key].extend(context)
                        policy_done_counts[pidx] += 1
                        if policy_done_counts[pidx] >= tasks_per_policy:
                            basic = (
                                crawled_info_list[pidx]
                                if crawled_info_list and pidx < len(crawled_info_list)
                                else PolicyBasicInfo()
                            )
                            partial = Policy(
                                policy_name=pname,
                                basic_info=basic,
                                return_rate=(
                                    crawled_return_rates[pidx]
                                    if crawled_return_rates and pidx < len(crawled_return_rates)
                                    else 0.0
                                ),
                                policy_document="", # Don't send the full text back during streaming update
                                fulfil_filters=(False, "Evaluating..."),
                                scoring=[],
                                retrieved_context=dict(policy_ctx[pidx]),
                            )
                            try:
                                on_policy_done(partial)
                            except Exception as cb_exc:
                                logger.warning("[MDRetriever] on_policy_done error: %s", cb_exc)

        # ── Final assembly ────────────────────────────────────────────────
        all_policies: List[Policy] = []
        task_idx = 0

        for policy_idx, policy_name in enumerate(available_policies):
            retrieved_ctx: Dict[str, List[str]] = {}

            for f_text in (criteria.filters or []):
                retrieved_ctx[f_text] = results.get(task_idx, [])
                task_idx += 1

            for crit in (criteria.criteria or []):
                retrieved_ctx[crit.item] = results.get(task_idx, [])
                task_idx += 1

            basic = (
                crawled_info_list[policy_idx]
                if crawled_info_list and policy_idx < len(crawled_info_list)
                else PolicyBasicInfo()
            )
            all_policies.append(Policy(
                policy_name=policy_name,
                basic_info=basic,
                return_rate=(
                    crawled_return_rates[policy_idx]
                    if crawled_return_rates and policy_idx < len(crawled_return_rates)
                    else 0.0
                ),
                policy_document="", 
                fulfil_filters=(False, "Retrieved context successfully."),
                scoring=[],
                retrieved_context=retrieved_ctx,
            ))

        print(f"\n[MDRetriever] ══════ ALL RETRIEVAL TASKS COMPLETED ══════\n")
        return all_policies
