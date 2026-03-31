from pydantic import BaseModel, Field
from typing import Any, TypeVar, Generic, Optional, Literal, Union, List, Dict, Annotated, TypedDict, Tuple
import operator

T = TypeVar('T')


class RequirementItem(BaseModel):
    """A single, self-contained requirement captured during the consultation."""
    key: str = Field(description="Unique snake_case identifier (e.g. 'beneficiary', 'monthly_budget', 'outstanding_mortgage')")
    label: str = Field(description="Human-readable label shown in the UI (e.g. 'Primary Beneficiary', 'Monthly Budget')")
    value: Any = Field(description="The captured value — string, number, list, or boolean")
    source: Literal["User input", "Recommended", "Inferred", "System calculated"] = Field(
        default="User input",
        description="How this value was obtained"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Why this was inferred or recommended, or any important nuance about the value"
    )
    confirmed_by_user: bool = Field(
        default=False,
        description="Whether the user explicitly confirmed this value"
    )


class UserRequirements(BaseModel):
    """
    Flexible, open-ended requirements profile built through conversation.
    Items are captured in the order they are discovered — not a fixed checklist.
    """
    items: List[RequirementItem] = Field(
        description="All requirements discovered during the consultation, in discovery order"
    )

    def to_text(self) -> str:
        """Serialise to human-readable text suitable for downstream agents."""
        lines = []
        for r in self.items:
            line = f"- {r.label}: {r.value}"
            if r.reasoning:
                line += f"  ({r.reasoning})"
            if r.source != "User input":
                line += f"  [source: {r.source}]"
            lines.append(line)
        return "\n".join(lines)

    def get(self, key: str) -> Optional[RequirementItem]:
        for item in self.items:
            if item.key == key:
                return item
        return None

class ScoringItem(BaseModel):
    item: str=Field(description="Scoring item")
    description: str=Field(description="Describe the relevant information needed for this scoring item.")
    scoring_rules: str=Field(description="How the item should be scored on a scale of 1 to 5.")
    weight: int=Field(description="Weightage of each scoring item. Sum up to 100.")

class ScoringCriteria(BaseModel):
    criteria: List[ScoringItem] = Field(description="List of criteria used to score life insurance policies for this user.")
    filters: List[str]=Field(description="Hard filters for the policy. Certain policies should be excluded based on these filters.")

class PolicyBasicInfo(BaseModel):
    """Basic policy facts fetched from comparefirst.sg by the policy_fetcher agent."""
    insurer: str              = Field(default="", description="Insurer company name")
    annual_premium: str       = Field(default="N/A", description="Annual premium, e.g. 'S$ 266'")
    coverage_term_years: str  = Field(default="N/A", description="Coverage term, e.g. '20' or 'Whole Life'")
    premium_term_years: str   = Field(default="N/A", description="Premium payment term, e.g. '20'")
    total_premium: str        = Field(default="N/A", description="Total premium payable")
    distribution_cost: str    = Field(default="N/A", description="Distribution cost")
    credit_rating: str        = Field(default="N/A", description="Credit rating, e.g. 'A2 (Moody\\'s)'")
    guaranteed_maturity_benefit: str = Field(default="N/A", description="Guaranteed maturity benefit (endowment only)")
    product_summary_url: str  = Field(default="", description="URL to product summary PDF")
    brochure_url: str         = Field(default="", description="URL to brochure PDF")

    def to_text(self) -> str:
        lines = [f"- Annual Premium: {self.annual_premium}"]
        if self.coverage_term_years != "N/A":
            lines.append(f"- Coverage Term: {self.coverage_term_years} years")
        if self.premium_term_years != "N/A":
            lines.append(f"- Premium Payment Term: {self.premium_term_years} years")
        if self.total_premium != "N/A":
            lines.append(f"- Total Premium Payable: {self.total_premium}")
        if self.distribution_cost != "N/A":
            lines.append(f"- Distribution Cost: {self.distribution_cost}")
        if self.credit_rating != "N/A":
            lines.append(f"- Credit Rating: {self.credit_rating}")
        if self.guaranteed_maturity_benefit != "N/A":
            lines.append(f"- Guaranteed Maturity Benefit: {self.guaranteed_maturity_benefit}")
        return "\n".join(lines)


class Policy(BaseModel):
    policy_name: str = Field(description="Name of the policy")
    basic_info: PolicyBasicInfo = Field(
        default_factory=PolicyBasicInfo,
        description="Basic policy facts from comparefirst.sg (premiums, terms, credit rating, URLs)"
    )
    fulfil_filters: Tuple[bool, str] = Field(description='Whether the policy fulfills the filters. If not, why not?')
    scoring: List[Tuple[int, ScoringItem, str]] = Field(description = 'Score for each item, the item itself, and reasoning')
    retrieved_context: Dict[str, List[str]] = Field(description = 'Relevant context found in the policy documents')

class RetrieverState(TypedDict):
    search_items: List[ScoringItem]
    current_item_index: int
    mode: str
    collected_context: List[str]
    messages: Annotated[List[dict], operator.add]
    iterations: int

class InsurancePolicy(BaseModel):
    # Placeholder for insurance policy data
    pass


class PolicyScoring(BaseModel):
    # Placeholder for how a policy scores against criteria
    pass

class RecommendationReport(BaseModel):
    # Placeholder for the final report structure
    pass
