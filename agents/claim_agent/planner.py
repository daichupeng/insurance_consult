from typing import Dict
from langchain_core.messages import SystemMessage

from graphs.claim_agent.state import ClaimAgentState

def planner(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent] Running planner...")
    scenario = state["claim_scenario"]
    details = state["claim_details"]
    policies_context = []
    for p in state["relevant_policies"]:
        policies_context.append(
            f"Policy: {p['insurance_name']} ({p['category']})\nContext: {p['retrieved_contexts'][-1]}"
        )
    
    ctx_str = "\n\n".join(policies_context)
    
    reviewer_feedback = state.get("review_feedback", "")
    previous_strategy = state.get("claim_strategy", "")
    reviewer_text = ""
    if reviewer_feedback:
        reviewer_text = f"""
        This is the previous claiming strategy that the reviewer rejected:
        Previous Strategy: {previous_strategy}
        Reviewer Feedback: {reviewer_feedback}

        Make sure your new claim strategy addresses the reviewer's feedback.
        """

    prompt = f"""
    You are an expert insurance claim advisor. Draft a step-by-step claiming strategy.
    
    Incident: {scenario}
    Details: {details}
    
    Available Policies and Context:
    {ctx_str}
    
    {reviewer_text}
    Draft a comprehensive claim strategy, including the following information:
    - Which policy or policies should cover the cost
    - How much each policy should cover and how much the user has to pay out of pocket
    - Payment method. Whether certain policy can be used to pay the bill directly or only reimburse the user after payment.
    - Claim steps. If the user has multiple policies, suggest the order in which to claim from them.

    Explain the reasoning of the plan.
    """
    
    res = llm.invoke([SystemMessage(content=prompt)])
    return {"claim_strategy": res.content}
