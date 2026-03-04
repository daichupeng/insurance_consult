from pydantic import BaseModel, Field
from typing import List, Optional, Dict

# User Profile to be optimized later. Maybe more dynamic

class UserProfile(BaseModel):
    age: Optional[int] = Field(None, description="Age of the user")
    gender: Optional[str] = Field(None, description="Gender of the user")
    occupation: Optional[str] = Field(None, description="Occupation of the user")
    annual_income: Optional[float] = Field(None, description="Annual income of the user in SGD")
    dependents: Optional[int] = Field(None, description="Number of financial dependents")
    health_status: Optional[str] = Field(None, description="General health status or specific pre-existing conditions")
    existing_coverage: Optional[float] = Field(None, description="Existing life insurance coverage amount in SGD")
    primary_goal: Optional[str] = Field(None, description="Primary goal for seeking life insurance (e.g., family protection, investment, estate planning, debt coverage)")
    annual_budget: Optional[float] = Field(None, description="Annual budget for insurance premiums in SGD")

class ProfileAnalysisResult(BaseModel):
    sufficient_info: bool = Field(description="Whether the user has provided enough information to make a reasonable life insurance recommendation.")
    clarification_questions: str = Field(description="Questions to ask the user if sufficient_info is False, to gather missing necessary details.")

class InsurancePolicy(BaseModel):
    # Placeholder for insurance policy data
    pass

class ScoringItem(BaseModel):
    item: str=Field(description="Scoring item")
    description: str=Field(description="Describe the relevant information needed for this scoring item.")
    scoring_rules: str=Field(description="How the item should be scored on a scale of 1 to 5.")
    weight: int=Field(description="Weightage of each scoring item. Sum up to 100.")

class ScoringCriteria(BaseModel):
    criteria: List[ScoringItem] = Field(description="List of criteria used to score life insurance policies for this user.")

class PolicyScoring(BaseModel):
    # Placeholder for how a policy scores against criteria
    pass

class RecommendationReport(BaseModel):
    # Placeholder for the final report structure
    pass
