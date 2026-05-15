import logging
import operator
from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from graphs.claim_agent.state import ClaimAgentState, AdvisorTask, TreatmentStrategy

from agents.claim_agent.substates import TreatmentState
from agents.claim_agent.treatment_agent import treatment_node
from agents.claim_agent.context_retriever import context_retriever
from agents.claim_agent.policy_fetcher import policy_fetcher
from agents.claim_agent.strategy_agent import strategy_node
from agents.claim_agent.treatment_cost_agent import treatment_cost_node

logger = logging.getLogger(__name__)

class PlannerDecision(BaseModel):
    next_node: Literal["fetcher","strategy","reviewer"] = Field(
        description="The next agent to route to. 'fetcher' for retrieving relevant contexts from insurance policy. 'strategy' for claiming strategy generation. 'reviewer' if a claiming strategy is generated."
    )
    reasoning: str = Field(description="Why this decision was made.")
    context_to_search: str = Field(description="Only populate if next_node='fetcher'. Specify the medical conditions or treatment items to focus on when retrieving policy contexts. This will guide the context_retriever.", default="")

def planner_node(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent]: Running planner")
    prompt = """
    You are the Planner in a Claim Incident Analysis team.
    Our goal: with the treatments for the user's medical condition, devise the best strategy to claim the cost under insurance policy.
    
    Diagnosis: {diagnosis}
    Symptoms: {symptoms}
    Tests done: {tests_done}
    Procedures conducted: {procedures_conducted}

    Suggested treatment plan:
    Consultations needed: {consultations_needed}
    Tests needed: {tests_needed}
    Procedures needed: {procedures_needed}
    Prescriptions needed: {prescriptions_needed}
    Estimated future costs: {estimated_future_costs}

    Relevant insurance policy contexts:
    {contexts}

    Current claiming strategy:
    {strategy}
    
    Review of the previous analysis:
    {review}
 
    Address the review of the findings if there is any. Only route to 'reviewer' if you think the comments in the review have been addressed.
 
    Decide the next step:
    1. 'fetcher': Use this to fetch and retrieve relevant contexts in the insurance policy documents.
    2. 'strategy': Generate the claiming strategy based on the retrieved contexts and the medical information.
    3. 'reviewer': When the strategy agent has generated the claiming strategy, route to 'reviewer' to review the claiming strategy.
    """
    
    diagnosis = state.get('diagnosis')
    symptoms = state.get('symptoms', [])
    tests_done = state.get('tests_done', [])
    procedures_conducted = state.get('procedures_conducted', [])
    consultations_needed = state.get('consultations_needed', [])
    tests_needed = state.get('tests_needed', [])
    procedures_needed = state.get('procedures_needed', [])
    prescriptions_needed = state.get('prescriptions_needed', [])
    estimated_future_costs = state.get('estimated_future_costs', [])
    estimated_future_costs = "\n".join([f"{c.item_name}: {c.item_cost}" for c in estimated_future_costs])
    strategy = state.get('claim_strategy', '')
    policies_context = []
    for p in state.get("relevant_policies", []):
        if p.get('retrieved_contexts'):
            policies_context.append(f"Policy: {p['insurance_name']}\nContext: {p['retrieved_contexts'][-1]}")
    contexts = "\n\n".join(policies_context) if policies_context else "Not retrieved yet."
    review_str = "\n".join([f"- {f}" for f in state.get("review", [])])

    if not review_str: 
        review_str = "None."
    
    formatted_prompt = prompt.format(diagnosis=diagnosis, symptoms=symptoms, tests_done=tests_done, procedures_conducted=procedures_conducted, consultations_needed=consultations_needed, tests_needed=tests_needed, procedures_needed=procedures_needed, prescriptions_needed=prescriptions_needed, estimated_future_costs=estimated_future_costs, strategy=strategy, review=review_str, contexts=contexts)
    structured_llm = llm.with_structured_output(PlannerDecision, method="function_calling")
    resp: PlannerDecision = structured_llm.invoke([SystemMessage(content=formatted_prompt)])
    
    return {
        "next_action": resp.next_node,
        "context_to_search": resp.context_to_search
    }


class ReviewDecision(BaseModel):
    is_passed: bool = Field(description="True if .")
    feedback: str = Field(description="If is_passed is False, explain what is missing or wrong.")

def reviewer_node(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent]: reviewing strategy...")
    prompt = """
    You are the Reviewer in a Claim Incident Analysis team. Review the condition, relevant insurance contexts, and the claiming strategy for this user.

    Make sure the claiming strategy is consistent with the insurance policy contexts and the medical information. And make sure the claiming strategy is optimized to help the user maximize the claimable amount under the insurance policy.
    If the claiming strategy is not consistent with the insurance policy contexts or the medical information, you should point it out and suggest improvements.

    Diagnosis: {diagnosis}
    Symptoms: {symptoms}
    Tests done: {tests_done}
    Procedures conducted: {procedures_conducted}

    Suggested treatment plan:
    Consultations needed: {consultations_needed}
    Tests needed: {tests_needed}
    Procedures needed: {procedures_needed}
    Prescriptions needed: {prescriptions_needed}
    Estimated costs: {estimated_future_costs}

    Relevant insurance policy contexts:
    {contexts}

    Current claiming strategy:
    {strategy}

    """
    diagnosis = state.get('diagnosis')
    symptoms = state.get('symptoms', [])
    tests_done = state.get('tests_done', [])
    procedures_conducted = state.get('procedures_conducted', [])
    consultations_needed = state.get('consultations_needed', [])
    tests_needed = state.get('tests_needed', [])
    procedures_needed = state.get('procedures_needed', [])
    prescriptions_needed = state.get('prescriptions_needed', [])
    strategy = state.get('claim_strategy', '')
    policies_context = []
    for p in state.get("relevant_policies", []):
        if p.get('retrieved_contexts'):
            policies_context.append(f"Policy: {p['insurance_name']}\nContext: {p['retrieved_contexts'][-1]}")
    contexts = "\n\n".join(policies_context) if policies_context else "None."
    estimated_future_costs = state.get('estimated_future_costs', [])
    estimated_future_costs = "\n".join([f"{c.item_name}: {c.item_cost}" for c in estimated_future_costs])
    
    formatted = prompt.format(
        diagnosis=diagnosis,
        symptoms=symptoms,
        tests_done=tests_done,
        procedures_conducted=procedures_conducted,
        consultations_needed=consultations_needed,
        tests_needed=tests_needed,
        procedures_needed=procedures_needed,
        prescriptions_needed=prescriptions_needed,
        estimated_future_costs=estimated_future_costs,
        contexts=contexts,
        strategy=strategy
    )
    
    structured_llm = llm.with_structured_output(ReviewDecision, method="function_calling")
    resp: ReviewDecision = structured_llm.invoke([SystemMessage(content=formatted)] + state.get('messages', []))
    
    if resp.is_passed:
        return {"review_passed": True, "review_count": state.get("review_count", 0) + 1}
    else:
        # Route back to planner with feedback
        return {"review_passed": False, "review": [f"[Reviewer Feedback] {resp.feedback}"], "review_count": state.get("review_count", 0) + 1}

def route_reviewer(state: TreatmentState) -> str:
    if state.get("review_passed") or state.get("review_count", 0) >= 2:
        return END
    return "planner"

def route_planner(state: TreatmentState) -> str:
    act = state["next_action"]
    if act == "ask_user":
        return END
    return act

# Define the Sub-Graph
def build_advisor_graph(llm):
    from functools import partial
    
    builder = StateGraph(TreatmentState)
    builder.add_node("treatment", partial(treatment_node, llm=llm))
    builder.add_node("planner", partial(planner_node, llm=llm))
    builder.add_node("retriever", partial(context_retriever, llm=llm))
    builder.add_node("fetcher", policy_fetcher)
    builder.add_node("strategy", partial(strategy_node, llm=llm))
    builder.add_node("reviewer", partial(reviewer_node, llm=llm))
    builder.add_node("treatment_cost", partial(treatment_cost_node, llm=llm))
    
    builder.add_edge(START, "treatment")
    builder.add_edge("treatment","treatment_cost")
    builder.add_edge("treatment_cost", "planner")
    builder.add_conditional_edges("planner", route_planner, {
        "fetcher": "fetcher",
        "strategy": "strategy",
        "reviewer": "reviewer",
        END: END
    })
    builder.add_edge("fetcher", "retriever")
    builder.add_edge("retriever", "planner")
    builder.add_edge("strategy", "planner")
    builder.add_conditional_edges("reviewer", route_reviewer, {
        "planner": "planner",
        END: END
    })
    
    return builder.compile()

def advisor_node(state: AdvisorTask, llm,) -> Dict:
    print("[ClaimAgent] Running advisor_graph...")
    
    subgraph = build_advisor_graph(llm)
    
    # Initialize inner state from persistent state or defaults
    inner_state = {
        "diagnosis": state['diagnosis'],
        "symptoms": state['symptoms'],
        "tests_done": state['tests_done'],
        "procedures_conducted": state['procedures_conducted'],
        "incurred_cost_items": state['incurred_cost_items'],
    }
    
    final_inner = subgraph.invoke(inner_state, {"recursion_limit": 100})
    
    treatment = TreatmentStrategy(
        diagnosis=state['diagnosis'],
        consultations_needed=final_inner.get("consultations_needed"),
        tests_needed=final_inner.get("tests_needed"),
        procedures_needed=final_inner.get("procedures_needed"),
        prescriptions_needed=final_inner.get("prescriptions_needed"),
        relevant_context=final_inner.get("relevant_context"),
        estimated_future_costs=final_inner.get("estimated_future_costs", []),
        claim_strategy=final_inner.get("claim_strategy"),
    )
        
    return {
        "treatment_strategies": [treatment]
    }
