"""
LangChain tools backed by the GraphRAG knowledge graph.

Loaded once at module import.  The config and parquet artefacts from
graphrag/output/ are held in module-level variables so every tool call
shares the same in-memory data without reloading from disk.

Tools
-----
graphrag_local_search   Entity-focused search — best for specific, factual
                        lookups about a named policy (benefit details,
                        exclusion clauses, premium figures, waiting periods).

graphrag_global_search  Community-level map-reduce across all documents —
                        best for comparative or holistic questions
                        (how does policy A compare to B on affordability?
                        which policies include a CI waiver rider?).

list_available_policies Re-exported from search_tools so the agent sees the
                        full tool surface in one import.

remove_context          Re-exported from search_tools.
"""

import asyncio
import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_core.tools import tool

import graphrag.api as api
from graphrag.config.load_config import load_config

logger = logging.getLogger(__name__)

# ── One-time initialisation ───────────────────────────────────────────────────

_PROJECT_ROOT  = Path(__file__).parent.parent
_GRAPHRAG_ROOT = _PROJECT_ROOT / "graphrag"
_OUTPUT_DIR    = _GRAPHRAG_ROOT / "output"

# GRAPHRAG_API_KEY must be set before load_config substitutes ${GRAPHRAG_API_KEY}
load_dotenv(_PROJECT_ROOT / ".env")
if not os.environ.get("GRAPHRAG_API_KEY"):
    os.environ["GRAPHRAG_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")

_cfg               = load_config(_GRAPHRAG_ROOT)
_entities          = pd.read_parquet(_OUTPUT_DIR / "entities.parquet")
_communities       = pd.read_parquet(_OUTPUT_DIR / "communities.parquet")
_community_reports = pd.read_parquet(_OUTPUT_DIR / "community_reports.parquet")
_text_units        = pd.read_parquet(_OUTPUT_DIR / "text_units.parquet")
_relationships     = pd.read_parquet(_OUTPUT_DIR / "relationships.parquet")

logger.info(
    "GraphRAG tools ready — %d entities, %d communities, %d text units",
    len(_entities), len(_communities), len(_text_units),
)


def _run_async(coro):
    """
    Run an async coroutine safely from a synchronous context.

    Creates a fresh event loop each time so it works regardless of whether
    the caller is inside a running loop (e.g. FastAPI, Jupyter) or not.
    This is intentionally simple and safe; the overhead of a new loop per
    tool call is negligible compared to the LLM round-trip.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def graphrag_local_search(query: str) -> str:
    """
    Search the insurance policy knowledge graph for specific, entity-level
    information.

    Uses GraphRAG local search: finds entities most relevant to the query,
    then assembles context from their descriptions, relationships, and the
    source text units they appear in.

    Best used for:
    - Specific benefit details for a named policy
      ("What is the death benefit payout for AIA Guaranteed Protect Plus III?")
    - Exclusion clauses or conditions for a specific policy
      ("What conditions are excluded under AIA Pro Lifetime Protector II?")
    - Premium rates, sum-assured limits, waiting periods for a named policy

    Args:
        query: A precise, factual question. Include the policy name when
               asking about a specific policy.
    """
    print(f"\n[GraphRAG local]  {query}")
    result, _ = _run_async(
        api.local_search(
            config=_cfg,
            entities=_entities,
            communities=_communities,
            community_reports=_community_reports,
            text_units=_text_units,
            relationships=_relationships,
            covariates=None,
            community_level=2,
            response_type="multiple paragraphs",
            query=query,
        )
    )
    return result if isinstance(result, str) else str(result)


@tool
def graphrag_global_search(query: str) -> str:
    """
    Search across ALL insurance policies using community-level synthesis.

    Uses GraphRAG global search: scores every community report in the
    knowledge graph against the query, then performs a map-reduce to
    produce a synthesised answer spanning all documents.

    Best used for:
    - Cross-policy comparisons
      ("Which policies offer the most comprehensive critical illness coverage?")
    - Holistic questions not tied to a single policy
      ("What rider options are available across all AIA policies?")
    - Identifying patterns or differences between policies on a criterion

    Args:
        query: A comparative or holistic question spanning multiple policies.
               Do NOT name a single policy — use graphrag_local_search for that.
    """
    print(f"\n[GraphRAG global] {query}")
    result, _ = _run_async(
        api.global_search(
            config=_cfg,
            entities=_entities,
            communities=_communities,
            community_reports=_community_reports,
            community_level=2,
            dynamic_community_selection=True,
            response_type="multiple paragraphs",
            query=query,
        )
    )
    return result if isinstance(result, str) else str(result)


# Re-export shared tools so callers only need one import
from tools.search_tools import list_available_policies, remove_context, query_expansion

__all__ = [
    "graphrag_local_search",
    "graphrag_global_search",
    "list_available_policies",
    "remove_context",
    "query_expansion",
]
