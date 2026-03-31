from typing import List, TypedDict, Annotated, Optional, Dict
import operator
from schema.models import UserRequirements, ScoringItem, PolicyScoring, RecommendationReport, ScoringCriteria, Policy

class AgentState(TypedDict):
    """
    State defining the data passed between nodes in the LangGraph workflow.
    """
    user_requirements: Optional[UserRequirements]
    criteria: ScoringCriteria
    is_good_recommendation: bool
    final_report: Optional[RecommendationReport]
    policies: List[Policy]
    crawled_policies: List[dict]   # Raw results from comparefirst.sg crawler
    # To prevent infinite reflection loops
    iterations: int
    messages: Annotated[List[dict], operator.add] # Chat history