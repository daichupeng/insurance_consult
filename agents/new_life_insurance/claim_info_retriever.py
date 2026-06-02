"""
Claim Info Retriever agent.

For each of the three claim scenarios — **death benefit**, **critical illness**,
and **disability** — this agent gathers the policy-document context needed to
later build a full benefit *calculator* (formulae, lookup tables, definitions,
exclusions, payout rules).

Retrieval backend is selectable via the module-level ``RETRIEVAL`` variable
(or the ``retrieval=`` constructor arg):

  - ``"rag"``      — Qdrant semantic search over chunked policy ``.md``
                     (``tools.RAG.rag_search``); returns discrete chunks scoped
                     to one policy by name. This is the original setup.
  - ``"graphrag"`` — the GraphRAG knowledge-graph index built from the
                     ``raw_policies/`` PDFs (``graphrag/output/``, queried via
                     ``graphrag query``); returns one synthesized, citation-backed
                     answer per query, searched across the whole corpus.

Architecture
------------
Like the other agents in this folder (``criteria_generator``,
``profile_analyzer``, ``graph_rag_retriever``) the per-scenario loop runs as a
LangGraph ``StateGraph``:

    retrieve → review → (refine ↺ retrieve | END)

``retrieve``  searches the selected backend for the current query.
``review``    scores each retrieved context's relevance (LLM, 0–1), keeps the
              top 3 that clear a threshold, and judges whether the kept context
              is *sufficient* to build a calculator.
``refine``    queues the LLM's follow-up queries targeting the missing info.

The router ends the loop when the context is sufficient, when there is no
actionable follow-up query, or after ``max_rounds`` (default 3) rounds.

The public :meth:`ClaimInfoRetriever.retrieve` runs the graph once per scenario
and returns one :class:`ClaimRetrievalResult` each, carrying the de-duplicated
relevant contexts collected across all rounds plus the final sufficiency verdict
and the query trail.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from tools.RAG import rag_search as _rag_search

logger = logging.getLogger(__name__)
load_dotenv()

_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"
_GRAPHRAG_DIR = _PROJECT_ROOT / "graphrag"

# ── Retrieval backend ──────────────────────────────────────────────────────────
# Which retriever the agent uses to fetch claim context:
#   "rag"      → Qdrant semantic search over chunked policy .md  (tools.RAG.rag_search).
#                Returns discrete chunks, scoped to a single policy by name.
#   "graphrag" → the GraphRAG knowledge-graph index built from raw_policies/ PDFs
#                (graphrag/output/, queried via `graphrag query`). Returns one
#                synthesized, citation-backed answer per query (not chunks) and
#                searches across the whole corpus (no per-policy filter in the CLI).
RETRIEVAL = "rag"  # "rag" | "graphrag"

# GraphRAG query method when RETRIEVAL == "graphrag" (see graphrag/run_query.py).
GRAPHRAG_METHOD = "local"  # "local" | "global" | "drift"

# Relevance below this (0–1) is discarded; only the best clearing it are kept.
RELEVANCE_THRESHOLD = 0.5
TOP_K_PER_QUERY = 6          # chunks pulled from RAG per query
TOP_CONTEXTS_PER_ROUND = 3   # kept per round after scoring
MAX_ROUNDS = 3


# ── Claim scenarios ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Scenario:
    key: str
    label: str
    seed_query: str


SCENARIOS: List[_Scenario] = [
    _Scenario(
        key="death",
        label="Benefits at Death",
        seed_query=(
            "components of the death benefit: sum assured payable on death, "
            "guaranteed and non-guaranteed bonuses, multipliers, and how the "
            "death benefit amount is calculated"
        ),
    ),
    _Scenario(
        key="critical_illness",
        label="Critical Illness",
        seed_query=(
            "critical illness benefit: covered critical illnesses, payout amount "
            "or percentage of sum assured, severity tiers (early/intermediate/"
            "advanced), and how the critical illness claim amount is calculated"
        ),
    ),
    _Scenario(
        key="disability",
        label="Disability",
        seed_query=(
            "total and permanent disability (TPD) benefit: definition of "
            "disability, payout amount or percentage of sum assured, age limits, "
            "and how the disability claim amount is calculated"
        ),
    ),
]


# ── Structured output for the reviewer ─────────────────────────────────────────

class _ScoredContext(BaseModel):
    index: int = Field(description="1-based index of the context as presented to you.")
    relevance: float = Field(description="Relevance to the query, 0.0–1.0.")
    reason: str = Field(default="", description="One short clause justifying the score.")
    summary: str = Field(
        default="",
        description=(
            "A 1-2 sentence summary of the calculator-relevant information this "
            "context contributes (the formula, rate, table, tier, or definition "
            "it provides). Used to track what is already known."
        ),
    )


class _ReviewResult(BaseModel):
    """LLM review of one round of retrieved contexts."""
    scores: List[_ScoredContext] = Field(
        description="A relevance score for every context presented, by index."
    )
    sufficient: bool = Field(
        description=(
            "True only if the kept contexts contain enough to build a FULL "
            "benefit calculator: the payout formula/rule AND every lookup table, "
            "rate, factor and term definition it references. False if anything "
            "is missing, undefined, or merely alluded to."
        )
    )
    missing_info: str = Field(
        default="",
        description=(
            "If not sufficient, a concrete description of what is missing "
            "(e.g. 'multiplier factor table by age', 'definition of TPD', "
            "'CI severity payout percentages')."
        ),
    )
    follow_up_queries: List[str] = Field(
        default_factory=list,
        description=(
            "If not sufficient, 1–3 fresh search queries phrased as the concept "
            "to look for, each targeting one piece of the missing information. "
            "Empty when sufficient."
        ),
    )


class _RefineResult(BaseModel):
    """LLM plan for the next retrieval round."""
    next_query: str = Field(
        description=(
            "The single most important next search query to run — the one that "
            "best closes the gap toward a full calculator, given what is already "
            "known and what has already been searched. Phrased as the concept to "
            "find, not keywords."
        )
    )
    pruned_pending: List[str] = Field(
        default_factory=list,
        description=(
            "The remaining pending queries to keep, with duplicates and queries "
            "that are similar/redundant to next_query or to each other removed. "
            "Does NOT include next_query."
        ),
    )


# ── LangGraph state ────────────────────────────────────────────────────────────

class ClaimRetrieverState(TypedDict):
    scenario_key: str
    scenario_label: str
    policy_stem: str
    query: str                    # query for the current round
    pending_queries: List[str]    # follow-up queries queued for later rounds
    queries_used: List[str]       # every query asked so far (dedupe + trail)
    blocks: List[str]             # raw retrieved contexts for the current round
    contexts: List[dict]          # kept RetrievedContext-shaped dicts (all rounds)
    known_information: List[str]  # summaries of the kept contexts (all rounds)
    seen: List[str]               # fingerprints of kept contexts (dedupe)
    sufficient: bool
    missing_info: str
    iterations: int               # rounds completed


# ── Result containers ──────────────────────────────────────────────────────────

@dataclass
class RetrievedContext:
    text: str
    relevance: float
    query: str
    round_no: int


@dataclass
class ClaimRetrievalResult:
    scenario_key: str
    scenario_label: str
    contexts: List[RetrievedContext] = field(default_factory=list)
    known_information: List[str] = field(default_factory=list)
    sufficient: bool = False
    missing_info: str = ""
    queries_used: List[str] = field(default_factory=list)
    rounds_run: int = 0

    def as_text(self) -> str:
        """Human-readable dump of the relevant contexts for this scenario."""
        head = (
            f"### {self.scenario_label}  "
            f"(sufficient={self.sufficient}, rounds={self.rounds_run}, "
            f"contexts={len(self.contexts)})"
        )
        if self.missing_info and not self.sufficient:
            head += f"\nStill missing: {self.missing_info}"
        if self.known_information:
            head += "\nKnown information:\n" + "\n".join(
                f"  - {k}" for k in self.known_information
            )
        body = "\n\n".join(
            f"[relevance={c.relevance:.2f} | round {c.round_no} | query: {c.query}]\n{c.text}"
            for c in self.contexts
        ) or "(no relevant contexts found)"
        return f"{head}\n\n{body}"


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _resolve_policy_stem(policy_name: str) -> Optional[str]:
    """Map a free-form policy name to the `.md` file stem RAG indexed it under."""
    if not _POLICIES_DIR.exists() or not policy_name:
        return None
    target = _normalise(policy_name)
    for md in _POLICIES_DIR.rglob("*.md"):
        if _normalise(md.stem) == target:
            return md.stem
    return None


def _split_rag_results(raw: str) -> List[str]:
    """Split rag_search's formatted output back into individual result blocks."""
    raw = (raw or "").strip()
    if not raw or raw.startswith("[RAG index not built]") or raw == "No matching chunks found.":
        return []
    # rag_search joins blocks with a blank line and each starts with "--- Result N".
    blocks = re.split(r"\n\n(?=--- Result \d+)", raw)
    return [b.strip() for b in blocks if b.strip()]


def _dedup_key(block: str) -> str:
    """Content fingerprint of a retrieved block, ignoring volatile framing.

    The `--- Result N (score=X) ---` header line varies between retrievals of the
    SAME underlying chunk (different rank/score across queries), so it must be
    excluded — otherwise the same content slips past the dedup. We key on the
    rest of the block (Policy / Section / Text / surrounding context), which is
    stable for a given chunk. For GraphRAG (no such header) the whole text is used.
    """
    stripped = re.sub(r"^---\s*Result\s+\d+\s*\(score=[^)]*\)\s*---\s*\n?", "", block).strip()
    # Collapse whitespace so trivial formatting differences don't defeat the key.
    return re.sub(r"\s+", " ", stripped)


def _graphrag_query(query: str, method: str = GRAPHRAG_METHOD) -> List[str]:
    """Query the GraphRAG index by shelling out to `graphrag query`.

    Mirrors graphrag/run_query.py: points `--root` at the graphrag/ dir and
    passes the OpenAI key through as GRAPHRAG_API_KEY. GraphRAG returns a single
    synthesized, citation-backed answer (not chunks), so this returns it as a
    one-element list to fit the same per-context scoring contract as RAG.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("[ClaimInfoRetriever] OPENAI_API_KEY missing; cannot query GraphRAG.")
        return []

    env = {**os.environ, "GRAPHRAG_API_KEY": api_key}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "graphrag", "query",
             "--root", str(_GRAPHRAG_DIR), "--method", method, query],
            capture_output=True, text=True, env=env, timeout=300,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[ClaimInfoRetriever] GraphRAG query timed out for %r", query)
        return []
    if proc.returncode != 0:
        logger.warning("[ClaimInfoRetriever] GraphRAG query failed: %s",
                       (proc.stderr or "").strip()[:400])
        return []

    # The CLI prints an info line ("SUCCESS: ... Search Response:") before the
    # answer body; strip everything up to and including it when present.
    out = (proc.stdout or "").strip()
    m = re.search(r"Search Response:\s*", out)
    if m:
        out = out[m.end():].strip()
    return [out] if out else []


# ── Agent ───────────────────────────────────────────────────────────────────────

class ClaimInfoRetriever:
    """Per-scenario retrieve → review → refine loop as a LangGraph StateGraph."""

    def __init__(
        self,
        retrieval: str = RETRIEVAL,
        graphrag_method: str = GRAPHRAG_METHOD,
        max_rounds: int = MAX_ROUNDS,
        threshold: float = RELEVANCE_THRESHOLD,
        top_k: int = TOP_K_PER_QUERY,
        top_contexts: int = TOP_CONTEXTS_PER_ROUND,
    ):
        if retrieval not in ("rag", "graphrag"):
            raise ValueError(f"retrieval must be 'rag' or 'graphrag', got {retrieval!r}")
        self.retrieval = retrieval
        self.graphrag_method = graphrag_method
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.top_k = top_k
        self.top_contexts = top_contexts
        self._reviewer = _llm.with_structured_output(_ReviewResult)
        self._refiner = _llm.with_structured_output(_RefineResult)

        # Build the per-scenario graph: retrieve → review → (refine ↺ | END)
        graph = StateGraph(ClaimRetrieverState)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("review",   self._review_node)
        graph.add_node("refine",   self._refine_node)

        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "review")
        graph.add_conditional_edges(
            "review",
            self._route_after_review,
            {"refine": "refine", "end": END},
        )
        graph.add_edge("refine", "retrieve")

        self.app = graph.compile()

    # ── Backend search ─────────────────────────────────────────────────────────

    def _search(self, query: str, policy_stem: str) -> List[str]:
        if self.retrieval == "graphrag":
            # GraphRAG has no per-policy filter in the CLI, so fold the policy
            # name into the query text to bias the search toward it.
            gq = f"For the policy '{policy_stem}': {query}" if policy_stem else query
            print(f"[ClaimInfoRetriever] GraphRAG ({self.graphrag_method}) searching for query={gq!r}")
            return _graphrag_query(gq, method=self.graphrag_method)

        print(f"[ClaimInfoRetriever] RAG searching for query={query!r} policy_stem={policy_stem!r}")
        try:
            raw = _rag_search(query, policy_name=policy_stem or "", top_k=self.top_k)
        except Exception as exc:
            logger.warning("[ClaimInfoRetriever] rag_search failed for %r: %s", query, exc)
            return []
        return _split_rag_results(raw)

    # ── Graph nodes ──────────────────────────────────────────────────────────────

    def _retrieve_node(self, state: ClaimRetrieverState) -> dict:
        query = state["query"]
        print(f"[ClaimInfoRetriever] {state['scenario_key']} round {state['iterations'] + 1}"
              f"/{self.max_rounds} query={query!r}")
        blocks = self._search(query, state["policy_stem"])
        return {
            "blocks": blocks,
            "queries_used": state["queries_used"] + [query],
            "iterations": state["iterations"] + 1,
        }

    def _review_node(self, state: ClaimRetrieverState) -> dict:
        scenario_label = state["scenario_label"]
        query = state["query"]
        blocks = state["blocks"]
        print(f"[ClaimInfoRetriever] Reviewing for query={query!r} scenario={scenario_label!r}")

        if not blocks:
            return {
                "sufficient": False,
                "missing_info": f"No contexts retrieved for the {scenario_label} claim.",
                "pending_queries": state["pending_queries"],  # unchanged
            }

        review = self._review(scenario_label, query, blocks)

        # Keep the top-N blocks that clear the threshold this round, discarding
        # any whose text we have already kept in a previous round.
        contexts = list(state["contexts"])
        known = list(state["known_information"])
        seen = list(state["seen"])
        scored = sorted(
            (s for s in review.scores if 1 <= s.index <= len(blocks)),
            key=lambda s: s.relevance,
            reverse=True,
        )
        kept = 0
        for s in scored:
            if s.relevance < self.threshold or kept >= self.top_contexts:
                continue
            text = blocks[s.index - 1]
            fingerprint = _dedup_key(text)
            if fingerprint in seen:
                continue  # same chunk already kept (any earlier query) — discard
            seen.append(fingerprint)
            contexts.append({
                "text": text, "relevance": s.relevance,
                "query": query, "round_no": state["iterations"],
            })
            summary = (s.summary or "").strip()
            if summary:
                known.append(summary)
            kept += 1

        # If everything retrieved this round was a duplicate of what we already
        # have, treat it as if no new context came back: not sufficient, and
        # leave the existing pending queries untouched so refine picks the next.
        if kept == 0:
            print(f"[ClaimInfoRetriever] {state['scenario_key']} all retrieved contexts "
                  "were duplicates; treating as no new contexts.")
            return {
                "contexts": contexts,
                "known_information": known,
                "seen": seen,
                "sufficient": False,
                "missing_info": (
                    f"No new contexts for the {scenario_label} claim; last query "
                    "only returned already-seen material."
                ),
                "pending_queries": state["pending_queries"],
            }

        # Queue follow-ups for later rounds (deduped against what we've asked).
        pending = list(state["pending_queries"])
        if not review.sufficient:
            for q in review.follow_up_queries:
                q = (q or "").strip()
                if q and q not in state["queries_used"] and q not in pending:
                    pending.append(q)

        return {
            "contexts": contexts,
            "known_information": known,
            "seen": seen,
            "sufficient": review.sufficient,
            "missing_info": review.missing_info,
            "pending_queries": pending,
        }

    def _refine_node(self, state: ClaimRetrieverState) -> dict:
        """Use the LLM to choose the most important next query and prune the rest.

        Given what is already known, the queries already run, and the queued
        pending queries, the LLM picks the single highest-value next query and
        returns the remaining pending queries with duplicates/near-duplicates
        removed. Falls back to popping the first pending query on any error.
        """
        pending = list(state["pending_queries"])

        known = state["known_information"]
        known_text = "\n".join(f"- {k}" for k in known) or "(nothing yet)"
        used_text = "\n".join(f"- {q}" for q in state["queries_used"]) or "(none)"
        pending_text = "\n".join(f"- {q}" for q in pending) or "(none)"

        prompt = (
            "You are planning the next retrieval round while gathering reference "
            f"material to build a FULL benefit calculator for the "
            f"**{state['scenario_label']}** claim of a life-insurance policy.\n\n"
            f"What is already known (summaries of accepted contexts):\n{known_text}\n\n"
            f"Still missing:\n{state['missing_info'] or '(unspecified)'}\n\n"
            f"Queries already run (do NOT repeat these):\n{used_text}\n\n"
            f"Candidate pending queries:\n{pending_text}\n\n"
            "Choose the SINGLE most important next query — the one that best "
            "closes the gap toward a complete calculator given what is already "
            "known. It may be one of the pending candidates or a sharper "
            "reformulation. Then return the remaining pending queries to keep, "
            "removing any that are duplicates of, or essentially similar to, your "
            "chosen next query or to each other. Do not include the chosen query "
            "in that list."
        )
        try:
            plan: _RefineResult = self._refiner.invoke([SystemMessage(content=prompt)])
            next_query = (plan.next_query or "").strip()
            if not next_query:
                raise ValueError("empty next_query")
            pruned = [q.strip() for q in plan.pruned_pending
                      if q and q.strip() and q.strip() != next_query]
            # Keep only queries we have not already run.
            pruned = [q for q in pruned if q not in state["queries_used"]]
            print(f"[ClaimInfoRetriever] {state['scenario_key']} refine → next={next_query!r} "
                  f"| pending kept={len(pruned)}")
            return {"query": next_query, "pending_queries": pruned}
        except Exception as exc:
            logger.warning("[ClaimInfoRetriever] refine planning failed: %s; "
                           "falling back to first pending query.", exc)
            next_query = pending.pop(0)
            return {"query": next_query, "pending_queries": pending}

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route_after_review(self, state: ClaimRetrieverState) -> str:
        if state["sufficient"]:
            print(f"[ClaimInfoRetriever] {state['scenario_key']} sufficient after round "
                  f"{state['iterations']}")
            return "end"
        if state["iterations"] >= self.max_rounds:
            print(f"[ClaimInfoRetriever] {state['scenario_key']} hit max rounds "
                  f"({self.max_rounds}); stopping.")
            return "end"
        if not state["pending_queries"]:
            print(f"[ClaimInfoRetriever] {state['scenario_key']} no follow-up queries; stopping.")
            return "end"
        return "refine"

    # ── Reviewer LLM call ───────────────────────────────────────────────────────

    def _review(self, scenario_label: str, query: str, blocks: List[str]) -> _ReviewResult:
        numbered = "\n\n".join(f"[Context {i}]\n{b}" for i, b in enumerate(blocks, 1))
        prompt = (
            "You are assembling reference material to build a FULL benefit "
            f"calculator for the **{scenario_label}** claim of a life-insurance "
            "policy.\n\n"
            f"Search query for this round:\n{query}\n\n"
            "Below are the retrieved policy-document contexts. Each context shows "
            "its `Section:` heading path and, around the matched `Text:`, a "
            "`Preceding context:` and `Following context:` (the neighbouring "
            "chunks under the same section, or '(none)' at a section boundary). "
            "Use the heading path and the surrounding context together with the "
            "matched text when judging relevance and sufficiency — e.g. a lookup "
            "table whose rates spill into the following context, or a defined "
            "term that appears in the preceding context.\n\n"
            "Do these things:\n"
            "1. Score each context's relevance to the query on a 0.0–1.0 scale "
            "(by its [Context N] index), taking the section path and surrounding "
            "context into account. For each, also give a 1-2 sentence `summary` "
            "of the calculator-relevant information it contributes (the formula, "
            "rate, table, tier, or definition).\n"
            "2. Decide whether the relevant contexts collectively give you enough "
            "to actually COMPUTE the benefit — i.e. the payout formula/rule AND "
            "every lookup table, rate, factor, severity tier, and term definition "
            "that formula depends on. If a needed table, percentage, or "
            "definition is referenced but not shown, or a term is used but never "
            "defined, it is NOT sufficient.\n"
            "If not sufficient, name the missing information concretely and "
            "propose 1–3 fresh search queries (phrased as the concept to find, "
            "not keywords) that would close the gap.\n\n"
            f"Contexts:\n{numbered}"
        )
        try:
            return self._reviewer.invoke([SystemMessage(content=prompt)])
        except Exception as exc:
            logger.warning("[ClaimInfoRetriever] review failed: %s", exc)
            # On reviewer failure, keep the raw blocks at threshold but mark
            # insufficient so the loop can retry with the seed query.
            return _ReviewResult(
                scores=[_ScoredContext(index=i, relevance=self.threshold)
                        for i in range(1, len(blocks) + 1)],
                sufficient=False,
                missing_info="Reviewer error; could not assess sufficiency.",
                follow_up_queries=[],
            )

    # ── Public interface ──────────────────────────────────────────────────────

    def _run_scenario(self, scenario: _Scenario, policy_stem: str) -> ClaimRetrievalResult:
        initial: ClaimRetrieverState = {
            "scenario_key": scenario.key,
            "scenario_label": scenario.label,
            "policy_stem": policy_stem,
            "query": scenario.seed_query,
            "pending_queries": [],
            "queries_used": [],
            "blocks": [],
            "contexts": [],
            "known_information": [],
            "seen": [],
            "sufficient": False,
            "missing_info": "",
            "iterations": 0,
        }
        # max_rounds rounds, each possibly running retrieve→review→refine; give
        # the graph generous headroom over the round cap (the router enforces it).
        final = self.app.invoke(initial, {"recursion_limit": self.max_rounds * 3 + 5})
        return ClaimRetrievalResult(
            scenario_key=scenario.key,
            scenario_label=scenario.label,
            contexts=[RetrievedContext(**c) for c in final["contexts"]],
            known_information=final["known_information"],
            sufficient=final["sufficient"],
            missing_info=final["missing_info"],
            queries_used=final["queries_used"],
            rounds_run=final["iterations"],
        )

    def retrieve(self, policy_name: str = "") -> List[ClaimRetrievalResult]:
        """Run all three claim scenarios for *policy_name*.

        Pass an empty *policy_name* to search across every indexed policy.
        Returns one :class:`ClaimRetrievalResult` per scenario.
        """
        if self.retrieval == "graphrag":
            # GraphRAG is indexed from PDFs (no .md stems); use the name as-is to
            # bias the query. Empty name → search the whole corpus.
            policy_stem = policy_name or ""
        else:
            policy_stem = _resolve_policy_stem(policy_name) or ""
            if policy_name and not policy_stem:
                logger.warning(
                    "[ClaimInfoRetriever] no .md stem for '%s'; searching all policies.",
                    policy_name,
                )
        return [self._run_scenario(sc, policy_stem) for sc in SCENARIOS]


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Usage: python -m agents.new_life_insurance.claim_info_retriever [policy_name] [rag|graphrag]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    mode = sys.argv[2] if len(sys.argv) > 2 else RETRIEVAL
    for res in ClaimInfoRetriever(retrieval=mode).retrieve(name):
        print("\n" + "=" * 80)
        print(res.as_text())
