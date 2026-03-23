"""
GraphRAG-backed retriever — parallel execution across all (policy × item) pairs.

Architecture
------------
Each combination of (policy, filter/criterion) is an independent retrieval task.
All tasks are dispatched concurrently via ThreadPoolExecutor so that N policies
× M items run at the same time instead of sequentially.

Within each task the LangGraph query_planner → tool_executor → reflector loop
runs as before — the parallelism is at the task level, not inside the loop.

Concurrency cap
---------------
max_workers defaults to min(total_tasks, MAX_CONCURRENT_TASKS).
Raise MAX_CONCURRENT_TASKS via env var RETRIEVER_MAX_WORKERS to trade speed
for API rate-limit headroom (or lower it to be conservative).

Thread-safety
-------------
graphrag_tools._run_async() creates a fresh event loop per call so every
worker thread gets its own loop — no shared state.
"""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from schema.models import Policy, ScoringCriteria, ScoringItem, RetrieverState
from tools.graphrag_tools import (
    graphrag_global_search,
    graphrag_local_search,
    list_available_policies,
    remove_context,
)

logger = logging.getLogger(__name__)
load_dotenv()

_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
_PROJECT_ROOT = Path(__file__).parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"  # all subfolders scanned recursively

_TOOLS    = [graphrag_local_search, graphrag_global_search, list_available_policies, remove_context]
_TOOL_MAP = {t.name: t for t in _TOOLS}

MAX_CONCURRENT_TASKS = int(os.getenv("RETRIEVER_MAX_WORKERS", "16"))


# ── Structured output for the reflector ──────────────────────────────────────

class ReflectorOutput(BaseModel):
    is_sufficient: bool = Field(
        description="True if the retrieved context contains sufficient information."
    )
    feedback: str = Field(
        description="If not sufficient, what should the query planner do next."
    )


# ── Task descriptor (one per policy × item pair) ──────────────────────────────

@dataclass
class _RetrievalTask:
    policy_name: str
    item: ScoringItem
    mode: str          # "filter" or "criterion"
    task_index: int    # original position, used to preserve ordering


# ── Retriever ─────────────────────────────────────────────────────────────────

class GraphRAGRetriever:
    """
    Retriever backed by a GraphRAG knowledge graph.

    Creates one independent LangGraph agent per (policy × item) pair and
    runs all of them concurrently.
    """

    def __init__(self):
        self._reflector_llm = _llm.with_structured_output(ReflectorOutput)
        self._progress_lock = threading.Lock()
        self._completed = 0

        workflow = StateGraph(RetrieverState)
        workflow.add_node("query_planner", self._query_planner_node)
        workflow.add_node("tool_executor", self._tool_executor_node)
        workflow.add_node("reflector",    self._reflector_node)
        workflow.add_node("increment",    self._increment_node)

        workflow.add_edge(START, "query_planner")
        workflow.add_conditional_edges(
            "query_planner",
            self._route_after_planner,
            {"tool_executor": "tool_executor", "reflector": "reflector"},
        )
        workflow.add_edge("tool_executor", "query_planner")
        workflow.add_conditional_edges(
            "reflector",
            self._route_after_reflector,
            {"query_planner": "query_planner", "next": "increment", "end": END},
        )
        workflow.add_edge("increment", "query_planner")

        self.app = workflow.compile()

    # ── Routing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _route_after_planner(state: RetrieverState) -> str:
        last = state["messages"][-1]
        return "tool_executor" if getattr(last, "tool_calls", None) else "reflector"

    @staticmethod
    def _route_after_reflector(state: RetrieverState) -> str:
        last = state["messages"][-1]
        if "Reflector: All good" in last.content:
            return "end" if state["current_item_index"] + 1 >= len(state["search_items"]) else "next"
        return "query_planner"

    # ── Graph nodes ───────────────────────────────────────────────────────────

    def _query_planner_node(self, state: RetrieverState) -> dict:
        item = state["search_items"][state["current_item_index"]]

        goal_text = (
            f"Your current goal is to find evidence for this hard filter:\nFilter: {item.description}"
            if state.get("mode") == "filter"
            else f"Your current goal is to gather information about:\nItem: {item.item}\nDescription: {item.description}"
        )

        system_prompt = SystemMessage(content=(
            f"You are a Query Planner for a life insurance knowledge graph. {goal_text}\n\n"
            "Use graphrag_local_search for specific, named-policy lookups and "
            "graphrag_global_search for cross-policy comparisons. "
            "Break the goal into sub-queries as needed. "
            "When you have enough context, say 'DONE'."
        ))

        response = _llm.bind_tools(_TOOLS).invoke([system_prompt] + state["messages"])
        return {"messages": [response]}

    def _tool_executor_node(self, state: RetrieverState) -> dict:
        last = state["messages"][-1]
        tool_messages: List[ToolMessage] = []
        collected = list(state.get("collected_context", []))

        for call in last.tool_calls:
            name, args = call["name"], call["args"]
            tool = _TOOL_MAP.get(name)
            res  = tool.invoke(args) if tool else f"Unknown tool: {name}"

            if name in ("graphrag_local_search", "graphrag_global_search"):
                if res and not res.lower().startswith("i'm sorry"):
                    collected.append(f"[{name}] Query: {args.get('query', name)}\n\n{res}")
            elif name == "remove_context":
                snippet = args.get("snippet", "")
                if snippet:
                    before    = len(collected)
                    collected = [c for c in collected if snippet not in c]
                    removed   = before - len(collected)
                    res = f"Removed {removed} item(s)." if removed else "No matching item found."

            tool_messages.append(ToolMessage(content=str(res), tool_call_id=call["id"]))

        return {"messages": tool_messages, "collected_context": collected}

    def _reflector_node(self, state: RetrieverState) -> dict:
        item       = state["search_items"][state["current_item_index"]]
        iterations = state.get("iterations", 0)

        if iterations >= 2:
            return {
                "messages":   [HumanMessage(content="Reflector: All good (limit reached). Proceed to next.")],
                "iterations": iterations + 1,
            }

        goal_text    = (f"Filter: {item.description}" if state.get("mode") == "filter"
                        else f"Item: {item.item}\nDescription: {item.description}")
        context_text = "\n\n".join(state.get("collected_context", [])) or "No context collected yet."

        prompt = (
            f"You are a Reflector evaluating retrieved information.\n"
            f"Goal:\n{goal_text}\n\nRetrieved Context:\n{context_text}\n\n"
            "Evaluate whether the context is sufficient to assess the goal. "
            "If yes, set is_sufficient=True. "
            "If no, set is_sufficient=False and describe what the query planner should search for next."
        )

        result: ReflectorOutput = self._reflector_llm.invoke([SystemMessage(content=prompt)])

        if result.is_sufficient:
            return {"messages": [HumanMessage(content="Reflector: All good. Proceed to next.")],
                    "iterations": iterations + 1}
        return {"messages": [HumanMessage(content=(
                    f"Reflector Feedback: {result.feedback}\n"
                    "Please use tools to address this, then say 'DONE'."))],
                "iterations": iterations + 1}

    @staticmethod
    def _increment_node(state: RetrieverState) -> dict:
        return {"current_item_index": state["current_item_index"] + 1, "iterations": 0}

    # ── Single-task execution (one policy × one item) ─────────────────────────

    def _run_task(self, task: _RetrievalTask, total: int) -> Tuple[_RetrievalTask, List[str]]:
        """Run the retrieval agent for a single (policy, item) pair."""
        state = RetrieverState(
            search_items=[task.item],
            mode=task.mode,
            current_item_index=0,
            collected_context=[],
            messages=[SystemMessage(content=f"Focus solely on the policy named: {task.policy_name}")],
            iterations=0,
        )
        result = self.app.invoke(state)
        context = result["collected_context"]

        with self._progress_lock:
            self._completed += 1
            done = self._completed
        logger.info(
            "[Retriever] %d/%d done — %s | %s: %s",
            done, total,
            task.policy_name,
            task.mode,
            task.item.item if task.mode == "criterion" else task.item.description[:60],
        )
        return task, context

    # ── Public interface ──────────────────────────────────────────────────────

    def retrieve(self, criteria: ScoringCriteria) -> List[Policy]:
        """
        Dispatch one retrieval agent per (policy × item) pair and run them all
        concurrently. Returns Policy objects ready for the PolicyScorer.
        """
        available_policies: List[str] = (
            [f.stem for f in sorted(_POLICIES_DIR.rglob("*.pdf"))]
            if _POLICIES_DIR.exists() else []
        )
        if not available_policies:
            logger.warning("No policy PDFs found in %s", _POLICIES_DIR)
            return []

        # ── Build flat task list ───────────────────────────────────────────
        tasks: List[_RetrievalTask] = []
        idx = 0
        for policy_name in available_policies:
            for f_text in (criteria.filters or []):
                tasks.append(_RetrievalTask(
                    policy_name=policy_name,
                    item=ScoringItem(item="Hard Filter", description=f_text,
                                     scoring_rules="N/A", weight=0),
                    mode="filter",
                    task_index=idx,
                ))
                idx += 1
            for crit_item in (criteria.criteria or []):
                tasks.append(_RetrievalTask(
                    policy_name=policy_name,
                    item=crit_item,
                    mode="criterion",
                    task_index=idx,
                ))
                idx += 1

        total       = len(tasks)
        n_workers   = min(total, MAX_CONCURRENT_TASKS)
        self._completed = 0

        logger.info(
            "[GraphRAGRetriever] %d policies × (%d filters + %d criteria) = %d tasks "
            "→ running with %d parallel workers",
            len(available_policies),
            len(criteria.filters or []),
            len(criteria.criteria or []),
            total,
            n_workers,
        )

        # ── Run all tasks in parallel ──────────────────────────────────────
        results: Dict[int, List[str]] = {}   # task_index → collected_context

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
                    logger.error(
                        "[Retriever] Task failed — %s | %s: %s",
                        failed.policy_name, failed.mode, exc,
                    )
                    results[failed.task_index] = []

        # ── Assemble Policy objects (preserve policy order) ────────────────
        all_policies: List[Policy] = []
        task_idx = 0

        for policy_name in available_policies:
            filters_context:  List[str] = []
            criteria_context: List[str] = []

            for _ in (criteria.filters or []):
                filters_context.extend(results.get(task_idx, []))
                task_idx += 1

            for _ in (criteria.criteria or []):
                criteria_context.extend(results.get(task_idx, []))
                task_idx += 1

            all_policies.append(Policy(
                policy_name=policy_name,
                fulfil_filters=(False, "Pending evaluation by Policy Scorer"),
                scoring=[(0, ScoringItem(item="Pending", description="",
                                         scoring_rules="", weight=0),
                          "Pending evaluation by Policy Scorer")],
                retrieved_context={"filters": filters_context, "criteria": criteria_context},
            ))

        return all_policies
