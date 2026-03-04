from typing import List, TypedDict, Annotated, Optional
import operator
from schema.models import UserProfile, ScoringItem, PolicyScoring, RecommendationReport

class AgentState(TypedDict):
    """
    State defining the data passed between nodes in the LangGraph workflow.
    """
    user_profile: Optional[UserProfile]
    criteria: List[ScoringItem]
    retrieved_context: List[str]
    gradings: List[PolicyScoring]
    is_good_recommendation: bool
    final_report: Optional[RecommendationReport]
    # To prevent infinite reflection loops
    iterations: int             
    messages: Annotated[List[dict], operator.add] # Chat history