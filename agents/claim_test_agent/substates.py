import operator
from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

class TestPatientState(TypedDict):
    patient_age: int
    ground_truth: str
    stage: str
    costs: str
    scenario_output: str  # This will store the final JSON