from pydantic import BaseModel, Field
from typing import TypeVar, Generic, Optional, Literal, Union, List, Dict, Annotated, TypedDict, Tuple
import operator

T = TypeVar('T')
# User Profile to be optimized later. Maybe more dynamic

class AttributeValue(BaseModel, Generic[T]):
    value: T
    source: Literal["User input", "Recommended", "Default", "System calculated"]
    reasoning: Optional[str] = Field(None, description="If the value is inferred or system calculated, provide the details here.")
    confirmed_by_user: bool = Field(False, description="Whether the value is confirmed by the user.")


class UserRequirements(BaseModel):
    age: int = Field(description="Age of the user")
    gender: str = Field(description="Gender of the user")
    occupation: str = Field(description="Occupation of the user")
    is_smoker: bool = Field(description="Whether the user is a smoker")
    annual_income: int = Field(description="Annual income of the user in SGD")
    dependents: AttributeValue[int] = Field(description="Number of financial dependents")
    health_status: AttributeValue[str] = Field(description="General health status or specific pre-existing conditions")
    existing_coverage: int = Field(description="Existing life insurance coverage amount in SGD")
    primary_goal: str = Field(description="Primary goal for seeking life insurance (e.g., family protection, investment, estate planning, debt coverage)")
    coverage_amount: AttributeValue[float] = Field(description="Desired coverage amount in SGD")
    budget: AttributeValue[float] = Field(description="Annual budget for insurance premiums in SGD")
    policy_type: AttributeValue[str] = Field(description="Type of insurance policy (e.g., term life, whole life, universal life)")
    policy_duration: AttributeValue[int] = Field(description="Duration of the insurance policy in years")

class ProfileAnalysisResult(BaseModel):
    sufficient_info: bool = Field(description="Whether the user has provided enough information to make a reasonable life insurance recommendation.")
    clarification_questions: str = Field(description="Questions to ask the user if sufficient_info is False, to gather missing necessary details.")

class ScoringItem(BaseModel):
    item: str=Field(description="Scoring item")
    description: str=Field(description="Describe the relevant information needed for this scoring item.")
    scoring_rules: str=Field(description="How the item should be scored on a scale of 1 to 5.")
    weight: int=Field(description="Weightage of each scoring item. Sum up to 100.")

class ScoringCriteria(BaseModel):
    criteria: List[ScoringItem] = Field(description="List of criteria used to score life insurance policies for this user.")
    filters: List[str]=Field(description="Hard filters for the policy. Certain policies should be excluded based on these filters.")

class Policy(BaseModel):
    policy_name: str = Field(description="Name of the policy")
    fulfil_filters: Tuple[bool, str] = Field(description='Whether the policy fulfills the filters. If not, why not?')
    scoring: List[Tuple[int, ScoringItem, str]] = Field(description = 'Score for each item, the item itself, and reasoning')
    retrieved_context: Dict[str, List[str]] = Field(description = 'Relevant context found in the policy documents')

class RetrieverState(TypedDict):
    search_items: List[ScoringItem]
    current_item_index: int
    mode: str
    collected_context: Annotated[List[str], operator.add]
    messages: Annotated[List[dict], operator.add]


class InsurancePolicy(BaseModel):
    # Placeholder for insurance policy data
    pass


class PolicyScoring(BaseModel):
    # Placeholder for how a policy scores against criteria
    pass

class RecommendationReport(BaseModel):
    # Placeholder for the final report structure
    pass
