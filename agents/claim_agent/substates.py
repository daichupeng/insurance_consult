import operator
from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from graphs.claim_agent.state import CostItem, Diagnosis


# Incident analyzer
class AnalyzerState(TypedDict):
    messages: Annotated[List[Any], operator.add]
    symptoms: List[str]
    tests_done: List[str]
    procedures_conducted: List[str]
    primary_diagnosis: Optional[str]
    incurred_cost_items: List[CostItem]
    missing_info: List[str]
    clarification_question: Optional[str]
    review_passed: bool
    review_count: int
    next_action: str


# Treatment and claim
class TreatmentState(TypedDict):
    diagnosis: Diagnosis
    
    symptoms: List[str]
    tests_done: List[str]
    procedures_conducted: List[str]

    consultations_needed: List[str]
    tests_needed: List[str]
    procedures_needed: List[str]
    prescriptions_needed: List[str]

    incurred_cost_items: List[CostItem]
    relevant_context: Annotated[List[str], operator.add]
    claim_strategy: str
    relevant_policies: List[Any]

    review_result: str
    review_passed: bool
    review_count: int
    context_to_search: str
    next_action: str