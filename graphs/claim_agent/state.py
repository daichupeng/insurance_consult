from typing import Dict, List, Any, TypedDict, Annotated, Optional
import operator
from pydantic import BaseModel, Field

class PolicyContext(TypedDict):
    policy_id: int
    insurance_name: str
    category: str
    medical_type: Optional[str]
    retrieved_contexts: List[str]

class ClaimAgentState(TypedDict):
    # Chat memory passed from SessionManager
    messages: Annotated[List[dict], operator.add]
    
    # Core variables requested by user
    claim_scenario: str
    claim_details: Dict[str, Any]
    relevant_policies: List[PolicyContext]
    claim_strategy: str

    # Control flags
    missing_info: List[str]
    review_status: str # 'pass', 'need_info', 'rewrite'
    review_feedback: str
