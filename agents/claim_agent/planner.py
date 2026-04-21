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
    
    prompt = f"""
    You are an expert insurance claim advisor. Draft a step-by-step claiming strategy.
    
    Incident: {scenario}
    Details: {details}
    
    Available Policies and Context:
    {ctx_str}
    
    Draft a comprehensive claim strategy. Outline steps, explain reasoning, and highlight any gaps.
    """
    
    res = llm.invoke([SystemMessage(content=prompt)])
    return {"claim_strategy": res.content}
