from pydantic import BaseModel, Field
from typing import Dict, List
from langchain_core.messages import SystemMessage

from agents.claim_agent.substates import TreatmentState
from graphs.claim_agent.state import CostItem


class TreatmentCost(BaseModel):
    costs: List[CostItem]

def treatment_cost_node(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent]: Estimating treatment costs...")
    diagnosis = state.get('diagnosis')

    consultations_needed = state.get('consultations_needed', [])
    tests_needed = state.get('tests_needed', [])
    procedures_needed = state.get('procedures_needed', [])
    prescriptions_needed = state.get('prescriptions_needed', [])

    prompt = f"""
    You are an expert medical cost planner. 

    Instructions: Based on the treatment items needed, estimate the cost for each item. Specify the cost under public hospitals / polyclinics / private hospitals / private clinics etc in Singapore.
    

    Medical information:
    Diagnosis: {diagnosis}

    Treatment plan:
    Consultations needed: {consultations_needed}
    Tests needed: {tests_needed}
    Procedures needed: {procedures_needed}
    Prescriptions needed: {prescriptions_needed}

    Output the estimated cost for each item done at different facilities. For example:
    item_name: Cardiologist consultation
    item_cost: $250 at private hospital; $50 at public hospital
    relevant_insurance_type: Outpatient policy
    """
    
    formatted_prompt = prompt.format(
        diagnosis=diagnosis,
        consultations_needed=consultations_needed,
        tests_needed=tests_needed,
        procedures_needed=procedures_needed,
        prescriptions_needed=prescriptions_needed
    )

    structured_llm = llm.with_structured_output(TreatmentCost, method="function_calling")
    resp: TreatmentCost = structured_llm.invoke([SystemMessage(content=formatted_prompt)])
    
    return {"estimated_future_costs": resp.costs}