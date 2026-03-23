"""
Conversational insurance profile builder — Planner → Executor → Reviewer loop.

Architecture
------------
The agent runs as a LangGraph StateGraph with three roles:

  Planner   Conducts the conversation with the user via the `ask_user` tool.
            Asks open questions, follows up on what matters, and records
            everything into a list of RequirementItems. Calls `FinalizeRound`
            when it's done asking for this round.

  Reviewer  Independently audits the gathered requirements and decides whether
            they are sufficient to generate meaningful scoring criteria and
            retrieve relevant policies. If not, produces specific feedback on
            what is still missing or unclear.

  Routing   After Reviewer: if sufficient (or max iterations reached) → END.
            Otherwise → Planner again with reviewer feedback.

Core philosophy
---------------
The single most important question in life insurance is:
  "Who or what does the money go to if a claim is made, and what will they
   need it for?"
Everything else (coverage amount, duration, policy type, budget) flows from
the answer to that question. The Planner starts there and lets the
conversation develop naturally — it is NOT a fixed-field form.
"""

import logging
import os
from typing import Annotated, Callable, List, Optional, Tuple
import operator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from schema.models import RequirementItem, UserRequirements

load_dotenv()
logger = logging.getLogger(__name__)
_llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))

MAX_ITERATIONS = 4  # max planner→reviewer rounds before forced submission

# ── State ────────────────────────────────────────────────────────────────────

class ProfilerState(TypedDict):
    initial_input: str
    conversation: Annotated[List, operator.add]   # accumulated Q&A messages
    gathered_items: List[RequirementItem]          # full list, replaced each round
    reviewer_feedback: str                         # feedback from last review
    is_sufficient: bool
    iterations: int


# ── Tool schemas ─────────────────────────────────────────────────────────────

class FinalizeRound(BaseModel):
    """
    Call this when you have finished asking questions for this round.
    Provide the COMPLETE list of requirements gathered so far — not just the new ones. Previously captured items should be preserved and updated if the user provided more detail.
    """
    items: List[RequirementItem]


class ReviewerOutput(BaseModel):
    is_sufficient: bool = Field(
        description=(
            "True only when ALL of the following are clear enough to generate a meaningful policy comparison:\n"
            "1. Beneficiary & purpose — who gets the money and what for?"
            "2. Coverage need — rough amount and duration"
            "3. Key eligibility factors"
            "4. Budget — annual premium they can afford"
            "A good-faith estimate is fine; perfection is not required."
        )
    )
    missing_areas: List[str] = Field(
        default_factory=list,
        description="Specific areas that are still unclear or absent.",
    )
    feedback: str = Field(
        description=(
            "Actionable guidance for the next questioning round — name exactly what to ask about and why it matters. Empty string if is_sufficient."
        )
    )


# ── Prompts ──────────────────────────────────────────────────────────────────

_PLANNER_PROMPT = """\
You are a caring and perceptive life insurance consultant conducting a client intake conversation.

## Core philosophy
The most important question in life insurance is:
  "Who or what does the money go to if a claim is made — and what will they need it for?"
Start there if this is the first round. Everything else follows naturally.

## How to conduct the conversation
- Ask open, human questions — not a checklist.
- Listen and follow up on what's meaningful:
    • Mentioned a mortgage? Ask the outstanding balance and whether their partner could service it alone.
    • Mentioned young children? Ask their ages (drives the duration).
    • Mentioned a business? Ask about business debts or partners.
- You may ask multiple questions per round, but group them naturally — don't fire a list of unrelated questions at once.
- If an answer is vague, ask for clarification.
- If something seems inconsistent (e.g. very low budget for high coverage), 
flag it gently and discuss it.
- When you recommend a value (e.g. a coverage multiple), explain the reasoning clearly and ask for explicit confirmation before recording it as confirmed.

## What to capture (not a fixed checklist — follow the conversation)
  beneficiary_purpose   Who depends on them and what the payout would cover
  age / health / occupation / smoker_status   Eligibility factors
  existing_coverage     Any current life insurance
  coverage_need         How much and roughly for how long
  financial_obligations  Mortgage, debts, dependants' needs
  budget                Annual premium they can comfortably afford

## When to call FinalizeRound
Call FinalizeRound when you feel you've gathered enough for this round and want the reviewer to assess sufficiency. You do NOT need everything — just enough to meaningfully compare policies. The reviewer will tell you if more is needed.

## RequirementItem fields
  key               snake_case identifier
  label             Human-readable name for the UI
  value             String, number, list, or boolean
  source            "User input" | "Recommended" | "Inferred"
  reasoning         Why inferred/recommended (omit for direct user inputs)
  confirmed_by_user True only if the user explicitly agreed to a recommendation
"""

_REVIEWER_PROMPT = """
You are a senior insurance underwriter reviewing a client intake profile to decide whether enough information has been gathered to proceed with a meaningful policy comparison.

A profile is sufficient when ALL of the following are clear:
1. Beneficiary & purpose — who gets the money, and what will it be used for?
2. Coverage need — a rough amount and duration (even a range or a debt figure to cover is enough).
3. Key eligibility factors — age, occupation, health status, smoker status.
4. Budget — at least an indication of what annual premium they can afford.

Good-faith estimates are acceptable; exact figures are not required.
If even one of the four points above is genuinely unclear, set is_sufficient to False and provide specific actionable feedback.
"""


# ── Agent class ───────────────────────────────────────────────────────────────

class ProfileAnalyzer:
    def __init__(self, confirm_callback: Optional[Callable[[str], Optional[str]]] = None):
        """
        Args:
            confirm_callback: callable(question) -> answer for web use.
                              When None, falls back to the CLI interactive tool.
        """
        if confirm_callback is not None:
            cb = confirm_callback

            @tool
            def ask_user(question: str) -> str:
                """
                Send a question or message to the user and wait for their reply.
                Use this to ask follow-up questions, request clarification, present
                a recommendation for confirmation, or flag a concern. You may include
                multiple related questions in a single call for natural conversation flow.
                """
                return cb(question) or ""

            self._ask_tool = ask_user
        else:
            from tools.interactive_tools import confirm_requirements as cli_tool
            self._ask_tool = cli_tool

        self._reviewer_llm = _llm.with_structured_output(ReviewerOutput)

        # Build the LangGraph
        graph = StateGraph(ProfilerState)
        graph.add_node("planner",  self._planner_node)
        graph.add_node("reviewer", self._reviewer_node)

        graph.add_edge(START, "planner")
        graph.add_edge("planner", "reviewer")
        graph.add_conditional_edges(
            "reviewer",
            self._route_after_reviewer,
            {"planner": "planner", END: END},
        )

        self.app = graph.compile()

    # ── Nodes ────────────────────────────────────────────────────────────────

    def _planner_node(self, state: ProfilerState) -> dict:
        """Conduct a round of conversation with the user, then call FinalizeRound."""

        # Build system message with current context
        header_parts = [_PLANNER_PROMPT]

        if state["gathered_items"]:
            profile_text = UserRequirements(items=state["gathered_items"]).to_text()
            header_parts.append(f"## Requirements captured so far\n{profile_text}")

        if state["reviewer_feedback"]:
            header_parts.append(
                f"## Reviewer says these areas still need attention\n"
                f"{state['reviewer_feedback']}\n"
                "Please address these specifically in this round."
            )

        messages = [SystemMessage(content="\n\n".join(header_parts))]

        # Initial user message is always visible for context
        messages.append(HumanMessage(content=state["initial_input"]))

        # Add accumulated conversation history from previous rounds
        if state["conversation"]:
            messages += list(state["conversation"])

        llm_with_tools = _llm.bind_tools([self._ask_tool, FinalizeRound])
        new_conversation: list = []

        logger.info("[ProfileAnalyzer] Planner round %d", state["iterations"] + 1)

        while True:
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            if not getattr(response, "tool_calls", None):
                # Nudge back on track
                messages.append(HumanMessage(
                    content=(
                        "Please continue: use `ask_user` to gather more information, "
                        "or `FinalizeRound` to submit what you have so far."
                    )
                ))
                continue

            tool_messages: list[ToolMessage] = []
            finalized_items: Optional[List[RequirementItem]] = None

            for call in response.tool_calls:
                if call["name"] == "ask_user":
                    answer = self._ask_tool.invoke(call["args"])
                    tool_messages.append(ToolMessage(content=answer, tool_call_id=call["id"]))

                elif call["name"] == "FinalizeRound":
                    raw_items = call["args"].get("items", [])
                    finalized_items = [
                        RequirementItem(**item) if isinstance(item, dict) else item
                        for item in raw_items
                    ]
                    tool_messages.append(
                        ToolMessage(content="Round finalized.", tool_call_id=call["id"])
                    )

            messages.extend(tool_messages)

            # Track new Q&A pairs for the conversation history
            if any(c["name"] == "ask_user" for c in response.tool_calls):
                new_conversation.append(response)
                new_conversation.extend(tool_messages)

            if finalized_items is not None:
                logger.info(
                    "[ProfileAnalyzer] Planner finalized %d items", len(finalized_items)
                )
                return {
                    "conversation": new_conversation,
                    "gathered_items": finalized_items,
                }

    def _reviewer_node(self, state: ProfilerState) -> dict:
        """Audit the gathered requirements and decide if they are sufficient."""
        logger.info(
            "[ProfileAnalyzer] Reviewer assessing %d items (iteration %d)",
            len(state["gathered_items"]),
            state["iterations"] + 1,
        )

        if not state["gathered_items"]:
            return {
                "is_sufficient": False,
                "reviewer_feedback": (
                    "Nothing has been captured yet. Start by asking who the money "
                    "would go to and what it would be used for."
                ),
                "iterations": state["iterations"] + 1,
            }

        profile_text = UserRequirements(items=state["gathered_items"]).to_text()
        prompt = (
            f"{_REVIEWER_PROMPT}\n\n"
            f"## Current client profile\n{profile_text}"
        )

        result: ReviewerOutput = self._reviewer_llm.invoke(
            [SystemMessage(content=prompt)]
        )

        if result.is_sufficient:
            logger.info("[ProfileAnalyzer] Reviewer: sufficient — proceeding")
            feedback = ""
        else:
            parts = []
            if result.missing_areas:
                parts.append("Missing: " + "; ".join(result.missing_areas) + ".")
            if result.feedback:
                parts.append(result.feedback)
            feedback = " ".join(parts)
            logger.info("[ProfileAnalyzer] Reviewer: not sufficient — %s", feedback)

        return {
            "is_sufficient": result.is_sufficient,
            "reviewer_feedback": feedback,
            "iterations": state["iterations"] + 1,
        }

    # ── Routing ──────────────────────────────────────────────────────────────

    @staticmethod
    def _route_after_reviewer(state: ProfilerState) -> str:
        if state["is_sufficient"] or state["iterations"] >= MAX_ITERATIONS:
            if not state["is_sufficient"]:
                logger.warning(
                    "[ProfileAnalyzer] Max iterations reached — submitting best-effort profile"
                )
            return END
        return "planner"

    # ── Public interface ──────────────────────────────────────────────────────

    def analyze_profile(
        self,
        user_input: str,
        existing_profile: Optional[UserRequirements] = None,
    ) -> Tuple[UserRequirements, list]:
        """
        Run the planner→reviewer loop until the profile is deemed sufficient.
        Returns (UserRequirements, conversation_messages).
        """
        initial_items = existing_profile.items if existing_profile else []

        initial_state: ProfilerState = {
            "initial_input": user_input,
            "conversation": [],
            "gathered_items": initial_items,
            "reviewer_feedback": "",
            "is_sufficient": False,
            "iterations": 0,
        }

        final_state = self.app.invoke(initial_state)
        profile = UserRequirements(items=final_state["gathered_items"])
        return profile, final_state["conversation"]
