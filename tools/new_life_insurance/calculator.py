import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def roi_calculator(annual_premium: float, premium_term: int, payouts: dict) -> float:
    """
    Computes the return (equivalent to IRR) of a life insurance premium using a discounted cash flow model.
    """
    if not payouts:
        return -1.0

    max_payout_year = max(payouts.keys()) if payouts else 0
    max_year = max(premium_term, max_payout_year)

    cash_flows = [0.0] * (max_year + 1)

    # Outflows: premiums paid at the beginning of each year
    for year in range(premium_term):
        cash_flows[year] -= annual_premium

    # Inflows: payouts received at specified years
    for year, amount in payouts.items():
        if year <= max_year:
            cash_flows[year] += amount

    # Calculate IRR using Newton-Raphson method
    rate = 0.05  # initial guess 5%
    for _ in range(100):
        # Prevent division by zero if rate gets dangerously close to -1
        if rate <= -1.0:
            rate = -0.999

        npv = sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cash_flows))
        derivative = sum(-i * cf / ((1 + rate) ** (i + 1)) for i, cf in enumerate(cash_flows))

        if abs(derivative) < 1e-10:
            break

        new_rate = rate - (npv / derivative)
        if abs(new_rate - rate) < 1e-6:
            return new_rate

        rate = new_rate

    return rate


def life_insurance_roi(
    insurance_type: str,
    annual_premium: float,
    premium_term: int,
    age: int,
    gender: str,
    sum_assured: float,
    coverage_term: int = 99,
    payout_age: int = None,
) -> float:
    """
    Calculates the life insurance ROI based on life expectancy assumptions.
    Singaporean life expectancy: 81 for male, 85 for female.
    For whole life insurance, the payout age should be specified according to the sub information of the policy. If not, leave blank.
    For term life insurance, the payout age can be left blank.
    """
    life_expectancy = 81 if gender.lower() == 'male' else 85
    if not payout_age:
        payout_age = life_expectancy
    assumed_death_year = payout_age - age

    # If the person has already outlived life expectancy, assume payout is immediate or return early
    if assumed_death_year <= 0:
        assumed_death_year = 1

    payouts = {}

    if insurance_type.lower() in ('whole_life', 'whole'):
        payouts[assumed_death_year] = sum_assured
    elif insurance_type.lower() == 'term':
        if assumed_death_year <= coverage_term:
            payouts[assumed_death_year] = sum_assured

    # Adjust premium term if expected death is before the premium term is completed
    actual_premium_term = min(premium_term, assumed_death_year)

    return roi_calculator(annual_premium, actual_premium_term, payouts)


# ─── Key Info Extraction ─────────────────────────────────────────────────────
#
# Extracts a standardized, machine-readable summary of a policy's economic
# values (benefits, surrender values, bonuses, etc.) from its full markdown
# document. Used by the policy scorer to enrich each Policy with `key_info`
# for downstream display.

class _CalculationRules(BaseModel):
    input: Optional[str] = Field(default=None, description="Inputs needed for calculation")
    rules: Optional[str] = Field(default=None, description="Calculation formula or lookup table description")


class _PolicyIdentity(BaseModel):
    product_name: Optional[str] = None
    product_type: Optional[str] = Field(default=None, description="Whole Life | Term | Decreasing Term | Endowment")
    age_basis_type: Optional[str] = Field(default=None, description="Next Birthday | Nearest Birthday | Last Birthday")
    currency: Optional[str] = None


class _SurrenderValue(BaseModel):
    available: Optional[bool] = None
    conditions: Optional[str] = None
    value_components: Optional[str] = Field(default=None, description="e.g. Insured Value + Cash Bonus + Terminal Bonus")


class _BenefitInfo(BaseModel):
    covered: Optional[str] = Field(default=None, description="True | False | Optional")
    conditions: Optional[str] = Field(default=None, description="Definition / triggering conditions")
    value_components: Optional[str] = None
    additional_conditions: Optional[str] = Field(default=None, description="Rider, multiplier, accelerated, etc.")


class _MultiplierRule(BaseModel):
    available: Optional[bool] = None
    conditions: Optional[str] = None


class _WithdrawalInfo(BaseModel):
    available: Optional[bool] = None
    conditions: Optional[str] = None
    fund_pool: Optional[str] = None
    calculation_rules: Optional[_CalculationRules] = None


class _BonusInfo(BaseModel):
    available: Optional[bool] = None
    conditions: Optional[str] = None
    calculation_rules: Optional[_CalculationRules] = None
    calculation_assumptions: Optional[str] = None


class _PolicyOption(BaseModel):
    available: Optional[bool] = None
    conditions: Optional[str] = None
    policy: Optional[str] = None


class PolicyKeyInfo(BaseModel):
    """Universal schema describing the economic terms of a life policy."""
    policy_identity: _PolicyIdentity = Field(default_factory=_PolicyIdentity)
    surrender_value: _SurrenderValue = Field(default_factory=_SurrenderValue)
    death_benefit: _BenefitInfo = Field(default_factory=_BenefitInfo)
    disability_benefit: _BenefitInfo = Field(default_factory=_BenefitInfo)
    terminal_illness_benefit: _BenefitInfo = Field(default_factory=_BenefitInfo)
    multiplier_rule: _MultiplierRule = Field(default_factory=_MultiplierRule)
    continual_income_withdrawal_value: _WithdrawalInfo = Field(default_factory=_WithdrawalInfo)
    cash_bonus: _BonusInfo = Field(default_factory=_BonusInfo)
    additional_cash_bonus: _BonusInfo = Field(default_factory=_BonusInfo)
    terminal_bonus: _BonusInfo = Field(default_factory=_BonusInfo)
    renewal_policy: _PolicyOption = Field(default_factory=_PolicyOption)
    convert_policy: _PolicyOption = Field(default_factory=_PolicyOption)
    additional_perks: List[str] = Field(default_factory=list)


_KEY_INFO_SYSTEM_PROMPT = """You are an expert insurance underwriter and data extraction engine.

Read the provided markdown policy document and populate the structured schema with the policy's
key economic terms: payouts, surrender values, cashbacks, maturity values, death / critical illness /
disability / terminal illness benefits, multipliers, bonuses, withdrawal options, renewal and conversion.

Rules:
1. If a field is not mentioned in the document, leave it null. Do not invent.
2. Where a numerical value is not stated, briefly describe the calculation rule in text.
3. Resolve compound terms: e.g. if "Surrender Value = guaranteed cash + cash bonus + terminal bonus",
   split them into value_components.
4. Booleans (`available`, `covered`): prefer true / false; use null only when the document is silent.
5. If a benefit is accelerated (reduces death benefit), say so in additional_conditions.
6. Keep strings concise but preserve every numerical value and condition.
"""


def key_info_extractor(policy_doc: str, llm) -> PolicyKeyInfo:
    """
    Extract a standardized PolicyKeyInfo summary from a markdown policy document
    using a single structured-output LLM call.

    Returns an empty PolicyKeyInfo if the document is empty or the call fails.
    """
    print('Extracting key info')
    if not policy_doc or not policy_doc.strip():
        return PolicyKeyInfo()

    structured_llm = llm.with_structured_output(PolicyKeyInfo)
    user_prompt = f"Extract key insurance terms, definitions, and values from this policy document:\n\n{policy_doc}"

    try:
        return structured_llm.invoke([
            SystemMessage(content=_KEY_INFO_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
    except Exception as e:
        logger.warning("[key_info_extractor] Extraction failed: %s", e)
        return PolicyKeyInfo()
