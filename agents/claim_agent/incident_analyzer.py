import logging
import operator
from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from graphs.claim_agent.state import ClaimAgentState

logger = logging.getLogger(__name__)

class ClaimDetailParameter(BaseModel):
    key: str = Field(description="Name of the detail, e.g. 'incident_date', 'claim_amount'")
    value: str = Field(description="Value of the detail.")

class IncidentAnalysisResult(BaseModel):
    claim_scenario: str = Field(description="High-level description of what happened.")
    claim_details: List[ClaimDetailParameter] = Field(description="List of extracted details of the incident.")
    missing_info: List[str] = Field(description="List of information the user needs to provide for incident assessment. Do not include what the user has explicitly expressed unable to provide.", default_factory=list)
    clarification_question: str = Field(description="If missing_info is non-empty, the exact question to ask the user to clarify.")

# --- Sub-Graph State ---
class AnalyzerState(TypedDict):
    messages: Annotated[List[Any], operator.add]
    findings: List[str]
    potential_costs: List[Dict[str, Any]]
    next_action: str
    clarification_question: str
    claim_scenario: str
    claim_details: Dict[str, Any]
    review: str
    missing_info: List[str]
    review_passed: bool
    review_count: int

# --- Planner ---
class PlannerDecision(BaseModel):
    next_node: Literal["medical", "cost", "summarizer", "ask_user"] = Field(
        description="The next agent to route to. 'medical' for medical specific analysis. 'cost' for medical cost analysis. 'ask_user' if information is missing. 'summarizer' if enough info is gathered."
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
    
    Conversation History:
    {messages}
    
    Current Findings from Specialists and Reviewers:
    {findings}

    Current cost analysis:
    {costs}
    
    Previous summary of the incident:
    {summary}

    Review of the previous summary:
    {review}

    Address the review of the summary if there is any. Only route to 'summarizer' if you think the comments in the review have been addressed.

    Decide the next step:
    1. 'medical': If there is injury/illness, analyze treatments needed.
    2. 'cost': Analyze potential costs based on medical findings. Only route to 'cost' if medical node is done and we have obtained all information possible.
    3. 'ask_user': If critical info is severely missing (e.g., we know they are hurt, but not what happened). 
       CRITICAL RULE: If the user expressed that they are unable to provide certain information for now, accept that the piece of information cannot be provided for now.
    4. 'summarizer': We have enough context across findings and chat to build the final scenario.
    """
    
    # Process history string safely (supports both dict and langchain message formats)
    msgs = state.get('messages', [])
    parsed_msgs = []
    for m in msgs:
        if isinstance(m, dict):
            parsed_msgs.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
        else:
            role = getattr(m, 'type', 'unknown')
            content = getattr(m, 'content', '')
            parsed_msgs.append(f"{role}: {content}")
            
    msg_history = "\n".join(parsed_msgs)
    
    findings_str = "\n".join([f"- {f}" for f in state.get("findings", [])])
    if not findings_str: 
        findings_str = "None."

    costs_str = "\n".join([f"- {f}" for f in state.get("potential_costs", [])])
    if not costs_str: 
        costs_str = "None."

    summary_str = "\n".join([f"- {f}" for f in state.get("claim_details", [])])
    if not summary_str: 
        summary_str = "None."

    review_str = "\n".join([f"- {f}" for f in state.get("review", [])])
    if not review_str: 
        review_str = "None."
    
    formatted_prompt = prompt.format(messages=msg_history, findings=findings_str, costs=costs_str, summary=summary_str, review=review_str)
    
    structured_llm = llm.with_structured_output(PlannerDecision, method="function_calling")
    resp: PlannerDecision = structured_llm.invoke([SystemMessage(content=formatted_prompt)])
    
    return {
        "next_action": resp.next_node,
        "clarification_question": resp.clarification_question,
        "missing_info": [resp.clarification_question] if resp.next_node == "ask_user" else []
    }


class MedicalAnalysis(BaseModel):
    findings: str = Field(description="A comprehensive clinical/medical summary of the incident, treatments, expected pathways, and potential cost scenarios.")
    potential_costs: List[str] = Field(description="List of potential costs identified for treatments or procedures.", default_factory=list)
    missing_info: List[str] = Field(description="List of specific clarifying questions about the user's medical condition or treatment plan that are needed but missing.", default_factory=list)

def medical_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: medical analysis...")
    prompt = """
    You are an expert Medical Claims Analyst. Your task is to perform a clinical review of the conversation.
    
    Instructions:
    1. Holistically evaluate the medical incident, detailing the exact nature of the injury or illness.
    2. Identify all treatments, procedures, diagnostics, and medical equipment involved or likely required.
    3. Project expected clinical pathways, timeline for recovery (best, expected, and worst-case scenarios).
    4. List any missing medical information critical for a thorough incident assessment, unless the user explicitly indicates such information is not available. If the user is unable to provide certain information due to the nature of the incident or current constraints, make reasonable assumptions or plan potential possibilities.
       CRITICAL: If the user has already provided a negative answer (e.g., 'no', 'none', 'I don't know', 'haven't finished') to a specific detail in the Conversation History, DO NOT list it as missing info. Accept the negative state as a known fact, record it in the findings, and proceed on that basis.
    
    Provide professional, detailed, and holistic output.
    """
    structured_llm = llm.with_structured_output(MedicalAnalysis, method="function_calling")
    resp: MedicalAnalysis = structured_llm.invoke([SystemMessage(content=prompt)] + state.get('messages', []))
    
    new_findings = [f"[Medical Findings]\n{resp.findings}"]
    if resp.missing_info:
        missing_str = "\n".join(f"- {q}" for q in resp.missing_info)
        new_findings.append(f"[Medical Missing Info Needed]\n{missing_str}")
        
    return {"findings": new_findings, "missing_info": resp.missing_info}

def cost_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: cost analysis...")
    prompt = """
    You are an expert Medical Cost Analyst. Your task is to perform a cost review of the medical treatments.

    Instructions:
    1. Based on the medical findings and potential treatment pathways, estimate the potential costs by item.
    2. Base it on different facilities, such as public hospital, private hospital, specialist clinic, different ward classes, etc.
    3. List any missing information critical for a thorough claims evaluation as far as the user can provide, unless the user explicitly indicates such information is not available yet.
       CRITICAL: If the user has already provided a negative answer to a specific detail in the history, DO NOT list it as missing info.
    
    You do not need to add new findings to the findings list. Provide professional, detailed, and holistic cost analysis.
    """
    structured_llm = llm.with_structured_output(MedicalAnalysis, method="function_calling")
    resp: MedicalAnalysis = structured_llm.invoke([SystemMessage(content=prompt)] + state.get('messages', []))
    
    cost_items = [f"[Cost Analysis]\n{resp.findings}"] + resp.potential_costs
        
    return {"potential_costs": cost_items, "missing_info": resp.missing_info}

def summarizer_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: summarizing information...")
    prompt = """
    You are the Summarizer. Look at the findings and the conversation.
    Synthesize the situation, concluding incurred costs and potential costs.
    Output the final explicit claim scenario and structured details.
    
    Findings:
    {findings}
    
    Potential Costs Estimated:
    {costs}
    """
    findings_str = "\n".join([f"- {f}" for f in state.get('findings', [])])
    costs_str = "\n".join([f"- {c}" for c in state.get('potential_costs', [])])
    formatted = prompt.format(findings=findings_str, costs=costs_str)
    
    structured_llm = llm.with_structured_output(IncidentAnalysisResult, method="function_calling")
    resp: IncidentAnalysisResult = structured_llm.invoke([SystemMessage(content=formatted)] + state['messages'])
    
    parsed_details = {d.key: d.value for d in resp.claim_details}
    
    return {
        "claim_scenario": resp.claim_scenario,
        "claim_details": parsed_details,
        "missing_info": []
    }

class ReviewDecision(BaseModel):
    is_passed: bool = Field(description="True if the summary captures everything perfectly, inferences are reasonable, and no information is missing. False if there are gaps.")
    feedback: str = Field(description="If is_passed is False, explain what is missing or wrong.")

def reviewer_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: reviewing summary...")
    prompt = """
    You are the Reviewer in a Claim Incident Analysis team. Review the conversation history and the Summarizer's output below.
    Make sure all the information about costs are captured.
    Identify if all information provided by the user that is  relating to costs is properly captured, if the inferences and assumptions are reasonable, and if there could be potential missing information we need from the user.
    If the information is not related to costs or has no implications on costs, you can ignore it.
    The user's insurance coverage should not be listed as a missing information.

    Summarizer Scenario: {scenario}
    Summarizer Details: {details}
    """
    formatted = prompt.format(
        scenario=state.get("claim_scenario", ""),
        details=state.get("claim_details", {})
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
    builder.add_node("summarizer", partial(summarizer_node, llm=llm))
    builder.add_node("reviewer", partial(reviewer_node, llm=llm))
    
    builder.add_edge(START, "planner")
    # Route appropriately
    builder.add_conditional_edges("planner", route_planner, {
        "medical": "medical",
        "cost": "cost",
        "summarizer": "summarizer",
        END: END
    })
    builder.add_edge("medical", "planner")
    builder.add_edge("cost", "planner")
    builder.add_edge("summarizer", "reviewer")
    builder.add_conditional_edges("reviewer", route_reviewer, {
        "planner": "planner",
        END: END
    })
    
    return builder.compile()

def incident_analysis(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent] Running incident_analysis (Planner/Executor)...")
    
    subgraph = build_incident_graph(llm)
    
    # Initialize inner state
    inner_state = {
        "messages": state["messages"],
        "findings": [],
        "potential_costs": [],
        "next_action": "",
        "clarification_question": "",
        "claim_scenario": "",
        "claim_details": {},
        "missing_info": [],
        "review_passed": False,
        "review_count": 0
    }
    
    final_inner = subgraph.invoke(inner_state, {"recursion_limit": 100})
    
    new_messages = []
    if len(final_inner.get("missing_info", [])) > 0 and final_inner.get("clarification_question"):
        new_messages.append({"role": "assistant", "content": final_inner["clarification_question"]})
        
    return {
        "claim_scenario": final_inner.get("claim_scenario", ""),
        "claim_details": final_inner.get("claim_details", {}),
        "potential_costs": final_inner.get("potential_costs", []),
        "missing_info": final_inner.get("missing_info", []),
        "messages": new_messages
    }
