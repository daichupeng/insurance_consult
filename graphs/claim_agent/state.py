from typing import Dict, List, Any, TypedDict, Annotated, Optional
import operator
from pydantic import BaseModel, Field

class PolicyContext(TypedDict):
    policy_id: int
    insurance_name: str
    category: str
    medical_type: Optional[str]
    retrieved_contexts: List[str]

class Diagnosis(BaseModel):
    diagnosis: str
    diagnosis_reason: str
    priority: int

class CostItem(BaseModel):
    item_name: str=Field(description="Exact procedures, prescriptions, consultations that have been conducted. Specify the item and the facilities. For example, GP consultation at private clinic, X-ray test at polyclinic, Paracetamol Prescription by GP， Appendectomy at a private hospital.")
    item_cost: str
    relevant_insurance_type: str=Field(description="The type of insurance the item could be potentially claimed from. Specify the type of insurance and the claim item under the insurance if possible. For example, outpatient insurance consultations, inpatient insurance surgery cost, accident insurance. There could be multiple possibilities")

class TreatmentStrategy(BaseModel):
    diagnosis: Diagnosis
    consultations_needed: List[str]
    tests_needed: List[str]
    procedures_needed: List[str]
    prescriptions_needed: List[str]
    relevant_context: Annotated[List[str], operator.add]
    claim_strategy: str

class AdvisorTask(TypedDict):
    diagnosis: Diagnosis
    symptoms: List[str]
    tests_done: List[str]
    procedures_conducted: List[str]
    incurred_cost_items: List[CostItem]

class ClaimAgentState(TypedDict):
    # Chat memory passed from SessionManager
    messages: Annotated[List[dict], operator.add]
    
    # Core variables requested by user
    symptoms: Annotated[List[str], operator.add]
    tests_done: Annotated[List[str], operator.add]
    procedures_conducted: Annotated[List[str], operator.add]
    primary_diagnosis: Optional[str]
    incurred_cost_items: Annotated[List[CostItem], operator.add]

    possible_diagnoses: List[Diagnosis]
    treatment_strategies: Annotated[List[TreatmentStrategy], operator.add]

    # Persistent internal state for agents
    analyzer_state: Optional[Dict[str, Any]]

    # Control flags
    missing_info: List[str]
    review_status: str # 'pass', 'need_info', 'rewrite'
    review_feedback: str