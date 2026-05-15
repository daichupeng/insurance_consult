import logging
import operator
from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from graphs.claim_agent.state import ClaimAgentState

from agents.claim_agent.substates import AnalyzerState
from agents.claim_agent.medical_analysis_agent import medical_node
from agents.claim_agent.initial_cost_agent import cost_node

logger = logging.getLogger(__name__)

class ClaimDetailParameter(BaseModel):
    key: str = Field(description="Name of the detail, e.g. 'incident_date', 'claim_amount'")
    value: str = Field(description="Value of the detail.")

class IncidentAnalysisResult(BaseModel):
    claim_scenario: str = Field(description="High-level description of what happened.")
    claim_details: List[ClaimDetailParameter] = Field(description="List of extracted details of the incident.")
    missing_info: List[str] = Field(description="List of information the user needs to provide for incident assessment. Do not include what the user has explicitly expressed unable to provide.", default_factory=list)
    clarification_question: str = Field(description="If missing_info is non-empty, the exact question to ask the user to clarify.")

# --- Planner ---
class PlannerDecision(BaseModel):
    next_node: Literal["medical", "cost", "reviewer", "ask_user"] = Field(
        description="The next agent to route to. 'medical' for medical specific analysis. 'cost' for medical cost analysis. 'ask_user' if information is missing. 'reviewer' if enough info is gathered."
    )
    reasoning: str = Field(description="Why this decision was made.")
    clarification_question: str = Field(description="Only populate if next_node='ask_user'. The exact phrasing.", default="")

def planner_node(state: AnalyzerState, llm) -> Dict:
    prompt = """
    You are the Planner in a Claim Incident Analysis team.
    Our goal: clearly understand the user's situation, roughly how much cost is incurred, and what treatments or damage exists.
    The user's insurance coverage should not be listed as a missing information since it is saved in the system.
    You should not ask the user about insurance coverage, or potential costs yet to be incurred. If you need information on future costs, you can get the cost agent to make reasonable estimates.
    If the user is unable to provide certain information due to the nature of the incident or current constraints, do not ask the question persistently. 
 
    Address the review of the findings if there is any. Only route to 'reviewer' if you think the comments in the review have been addressed.
 
    Decide the next step:
    1. 'medical': Use medical subagent to get a list of questions regarding medical symptoms, test results, and diagnosis. Also use this agent to record the medical information into the **information recorded**. When you suspect there are more medical related information the user could provide, use this node to generate a list of missing information to ask the user.
    2. 'cost': Use cost subagent to generate a list of questions regarding medical costs and record the costs provided by user into the **information recorded**.
    3. 'ask_user': When there is any questions fed back by the sub agents that have not been answered by the user, ask the user for clarification. If the user explicitly states unable to provide certain information, do not ask for it again.
    4. 'reviewer': All the relevant information have been gathered under **information recorded**. Now get the reviewer to review information recorded. 
    
    ** Information recorded **
    Symptoms reported by user:
    {symptoms_str}
 
    Tests reported by user:
    {tests_str}
 
    Procedures conducted as reported by user:
    {procedures_str}
 
    Suspected diagnosis reported by user:
    {diagnosis_str}
 
    Current costs reported by user:
    {cost_str}
 
    Review of the previous summary:
    {review}
 
    Questions to ask the user:
    {missing_info_str}
    """

    
    symptoms_str = "\n".join([f"- {f}" for f in state.get("symptoms", [])])
    if not symptoms_str: 
        symptoms_str = "None."
 
    tests_str = "\n".join([f"- {f}" for f in state.get("tests_done", [])])
    if not tests_str: 
        tests_str = "None."
 
    cost_str = "\n".join([f"- Item: {c.item_name}, Cost: {c.item_cost}" if hasattr(c, 'item_name') else f"- {c}" for c in state.get("incurred_cost_items", [])])
    if not cost_str: 
        cost_str = "None."
 
    procedures_str = "\n".join([f"- {f}" for f in state.get("procedures_conducted", [])])
    if not procedures_str: 
        procedures_str = "None."
 
    missing_info_str = "\n".join([f"- {f}" for f in state.get("missing_info", [])])
    if not missing_info_str: 
        missing_info_str = "None."
 
    review_str = "\n".join([f"- {f}" for f in state.get("review", [])])
    if not review_str: 
        review_str = "None."
    
    formatted_prompt = prompt.format(symptoms_str=symptoms_str, tests_str=tests_str, cost_str=cost_str, procedures_str=procedures_str,review=review_str,diagnosis_str=state.get('primary_diagnosis','None'),missing_info_str=missing_info_str)
    
    structured_llm = llm.with_structured_output(PlannerDecision, method="function_calling")
    resp: PlannerDecision = structured_llm.invoke([SystemMessage(content=formatted_prompt)] + state.get('messages', []))
    
    return {
        "next_action": resp.next_node,
        "clarification_question": resp.clarification_question,
        "missing_info": [resp.clarification_question] if resp.next_node == "ask_user" else []
    }

class ReviewDecision(BaseModel):
    is_passed: bool = Field(description="True if the summary captures everything perfectly, inferences are reasonable, and no information is missing. False if there are gaps.")
    feedback: str = Field(description="If is_passed is False, explain what is missing or wrong.")

def reviewer_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: reviewing findings...")
    prompt = """
    You are the Reviewer in a Claim Incident Analysis team. Review the conversation history and the summaries below.
    Make sure all the information about costs are captured.
    Identify if all information provided by the user that is relating to costs is properly captured, if the inferences and assumptions are reasonable, and if there could be potential missing information we need from the user.
    If the information is not related to costs or has no implications on costs, you can ignore it.
    The user's insurance coverage should not be listed as a missing information.
 
    Symptoms reported by user:
    {symptoms_str}
 
    Tests reported by user:
    {tests_str}
 
    Procedures conducted as reported by user:
    {procedures_str}
 
    Suspected diagnosis reported by user:
    {diagnosis_str}
 
    Current costs reported by user:
    {cost_str}
    """
    symptoms_str = "\n".join([f"- {f}" for f in state.get("symptoms", [])])
    tests_str = "\n".join([f"- {f}" for f in state.get("tests_done", [])])
    costs_str = "\n".join([f"- {f}" for f in state.get("incurred_cost_items", [])])
    procedures_str = "\n".join([f"- {f}" for f in state.get("procedures_conducted", [])])
    
    formatted = prompt.format(
        symptoms_str=symptoms_str or "None.", 
        tests_str=tests_str or "None.", 
        cost_str=costs_str or "None.", 
        procedures_str=procedures_str or "None.",
        diagnosis_str=state.get('primary_diagnosis','None')
    )
    
    structured_llm = llm.with_structured_output(ReviewDecision, method="function_calling")
    resp: ReviewDecision = structured_llm.invoke([SystemMessage(content=formatted)] + state.get('messages', []))
    
    if resp.is_passed:
        return {"review_passed": True, "review_count": state.get("review_count", 0) + 1}
    else:
        # Route back to planner with feedback
        return {"review_passed": False, "review": [f"[Reviewer Feedback] {resp.feedback}"], "review_count": state.get("review_count", 0) + 1}

def route_reviewer(state: AnalyzerState) -> str:
    if state.get("review_passed") or state.get("review_count", 0) >= 2:
        return END
    return "planner"

def route_planner(state: AnalyzerState) -> str:
    act = state["next_action"]
    if act == "ask_user":
        return END
    return act

# Define the Sub-Graph
def build_incident_graph(llm):
    from functools import partial
    
    builder = StateGraph(AnalyzerState)
    builder.add_node("planner", partial(planner_node, llm=llm))
    builder.add_node("medical", partial(medical_node, llm=llm))
    builder.add_node("cost", partial(cost_node, llm=llm))
    builder.add_node("reviewer", partial(reviewer_node, llm=llm))
    
    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", route_planner, {
        "medical": "medical",
        "cost": "cost",
        "reviewer": "reviewer",
        END: END
    })
    builder.add_edge("medical", "planner")
    builder.add_edge("cost", "planner")
    builder.add_conditional_edges("reviewer", route_reviewer, {
        "planner": "planner",
        END: END
    })
    
    return builder.compile()

def incident_analysis(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent] Running incident_analysis (Planner/Executor)...")
    
    subgraph = build_incident_graph(llm)
    
    # Initialize inner state from persistent state or defaults
    if state.get("analyzer_state"):
        inner_state = state["analyzer_state"]
        # Ensure we use the latest messages list which includes the current user message
        inner_state["messages"] = state["messages"]
    else:
        inner_state = {
            "messages": state["messages"],
            "symptoms": [],
            "tests_done": [],
            "procedures_conducted": [],
            "primary_diagnosis": None,
            "incurred_cost_items": [],
            "missing_info": [],
            "clarification_question": "",
            "review_passed": False,
            "review_count": 0,
            "next_action": ""
        }
    
    final_inner = subgraph.invoke(inner_state, {"recursion_limit": 100})
    
    new_messages = []
    if len(final_inner.get("missing_info", [])) > 0:
        # Prefer clarification_question if present, otherwise take the first item from missing_info
        msg = final_inner.get("clarification_question") or final_inner.get("missing_info")[0]
        if msg:
            new_messages.append(AIMessage(content=msg))
        
    return {
        "symptoms": final_inner.get("symptoms", []),
        "tests_done": final_inner.get("tests_done", []),
        "procedures_conducted": final_inner.get("procedures_conducted", []),
        "primary_diagnosis": final_inner.get("primary_diagnosis", None),
        "incurred_cost_items": final_inner.get("incurred_cost_items", []),
        "analyzer_state": dict(final_inner),
        "missing_info": final_inner.get("missing_info", []),
        "messages": new_messages
    }
