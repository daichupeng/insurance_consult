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
    payout_age: int = None
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
