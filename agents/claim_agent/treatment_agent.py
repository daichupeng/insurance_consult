from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from agents.claim_agent.substates import TreatmentState
from graphs.claim_agent.state import Diagnosis

class TreatmentPlan(BaseModel):
    consultations_needed: List[str] = Field(description="List of consultations needed with their specialty, e.g. 'Consultation with orthopedic specialist'")
    tests_needed: List[str] = Field(description="List of tests needed, e.g. 'MRI of the knee'")
    procedures_needed: List[str] = Field(description="List of procedures needed, including surgeries, operations, physical therapies, hospitalisation, etc.")
    prescriptions_needed: List[str]


def treatment_node(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent]: treatment analysis...")
    system_prompt = """
    You are an expert medical doctor. A patient is suspected to have a condition. You need to propose a combination of tests, prescriptions, treatments, procedures and surgeries for the suspected condition. Do not repeat the tests that have already been done, the prescriptions and procedures that have already been conducted.
    If all reasonable procedures and surgeries / consultations / prescriptions have been done to treat the condition, explicitly say "no further treatments needed".
    """

    user_prompt = """
    Suspected condition: {diagnosis}

    Symptoms: {symptoms}
    Tests already done: {tests_done}
    Procedures already conducted: {procedures_conducted}
    """

    formated_user_prompt = user_prompt.format(
        symptoms=state.get('symptoms'),
        tests_done=state.get('tests_done'),
        procedures_conducted=state.get('procedures_conducted'),
        diagnosis=state.get('diagnosis').diagnosis
        )

    structured_llm = llm.with_structured_output(TreatmentPlan, method="function_calling")
    resp: TreatmentPlan = structured_llm.invoke([SystemMessage(content=system_prompt),HumanMessage(content=formated_user_prompt)])
    
    return {"consultations_needed": resp.consultations_needed,
    "tests_needed": resp.tests_needed,
    "procedures_needed": resp.procedures_needed,
    "prescriptions_needed": resp.prescriptions_needed}