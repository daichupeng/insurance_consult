from typing import Dict
from langchain_core.messages import SystemMessage

from agents.claim_agent.substates import TreatmentState

def strategy_node(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent]: Drafting a claim strategy...")
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
    Estimated costs: {estimated_future_costs}
    
    Available Policies and Context:
    {ctx_str}
    
    {reviewer_text}
    Draft a comprehensive claim strategy, including the following information:
    1. For already incurred costs:
        - Which policy or policies should cover the cost
        - How much each policy should cover and how much the user has to pay out of pocket. Try to combine policy coverages where possible, to minimize out-of-pocket costs.
        - Claim steps. If the user has multiple policies, suggest the order in which to claim from them.
    2. For future treatment plan:
        - What treatment / test / procedures / consultation to do, in order. Specify whether to go to public or private hospitals / clinics.
        - Which policy or policies should cover the cost and what should the user expect to pay out-of-pocket. Try to minimize out-of-pocket costs, while ensuring medical quality as the highest priority. 
        - Claim procedure, pay and reimburse or use insurance card for direct payment
        - Try to combine policy coverages where possible, to minimize out-of-pocket costs.
        - For example:
            - Step 1: Go to private GP for fast diagnosis and referral, since the patient has outpatient coverage at private GP clinics. The user has to pay $10 out of pocket as copayment, under policy A. The patient can use the policy card to pay for the balance directly.
            - Step 2: Arrange an appointment at public hospital for blood test and X-ray, since the condition is likely not urgent, and the coverage for public hospital is higher. The consultation will likely cost $200, the blood test will cost $80. The patient can pay first and then claim all the costs under policy B.
            - Step 3: Get prescriptions from public hospital. The medication X will cost around $30. The patient can pay the bills first and then claim from policy B.
            

    Explain the reasoning of the plan.
    """
    
    res = llm.invoke([SystemMessage(content=prompt)])
    return {"claim_strategy": res.content}
