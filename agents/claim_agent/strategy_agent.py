from typing import Dict
from langchain_core.messages import SystemMessage

from agents.claim_agent.substates import TreatmentState

def strategy_node(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent] Running planner...")
    diagnosis = state.get('diagnosis')
    symptoms = state.get('symptoms', [])
    tests_done = state.get('tests_done', [])
    procedures_conducted = state.get('procedures_conducted', [])
    consultations_needed = state.get('consultations_needed', [])
    tests_needed = state.get('tests_needed', [])
    procedures_needed = state.get('procedures_needed', [])
    prescriptions_needed = state.get('prescriptions_needed', [])
    policies_context = []
    for p in state.get("relevant_policies", []):
        if p.get('retrieved_contexts'):
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
    You are an expert insurance claim advisor. Draft a step-by-step claiming strategy based on the medical condition and treatment plan.

    Instructions:
    1. You need to draft a claim strategy for the already incurred costs, and also a claim strategy for the future treatment plan.
    2. For the future treatment plan, you should allow the user to take as much benefit from the insurance policies as possible. Devise the plan with medical quality as the highest priority, ensuring the user receives adequate treatment. 
    3. With adequate treatment ensured, the next priority is to make sure to minimize the out of pocket cost for the user. With minimum out of pocket cost, try to ensure the best and fast service such as from private hospitals.
    4. For already incurred cost, advise the user how to claim for them if they are claimable under the user's insurance policies. With future treatment plan, specify which facilities the user should go (private hospital, public hospital, private GP clinic, polyclinic, etc) for each procedure.
        
    Medical information:
    Diagnosis: {diagnosis}
    Symptoms: {symptoms}
    Tests done: {tests_done}
    Procedures conducted: {procedures_conducted}

    Suggested treatment plan:
    Consultations needed: {consultations_needed}
    Tests needed: {tests_needed}
    Procedures needed: {procedures_needed}
    Prescriptions needed: {prescriptions_needed}
    
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
