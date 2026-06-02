INPUT_SCHEMA = [
    {"key": "event", "label": "Event", "type": "select", "default": "claim", "options": [
        {"value": "claim", "label": "Claim"},
        {"value": "surrender", "label": "Surrender"},
        {"value": "maturity", "label": "Maturity"},
        {"value": "income", "label": "Income"}
    ]},
    {"key": "sum_assured", "label": "Sum Assured", "type": "number", "default": 100000},
    {"key": "entry_age", "label": "Entry Age", "type": "integer", "default": 30},
    {"key": "gender", "label": "Gender", "type": "select", "default": "male", "options": [
        {"value": "male", "label": "Male"},
        {"value": "female", "label": "Female"}
    ]},
    {"key": "claim_year", "label": "Claim Year", "type": "integer", "default": 10, "event_scope": ["claim"]},
    {"key": "surrender_year", "label": "Surrender Year", "type": "integer", "default": 10, "event_scope": ["surrender"]},
    {"key": "accumulation_year", "label": "Accumulation Year", "type": "integer", "default": 5, "event_scope": ["surrender", "claim", "income"]},
]

OUTPUT_SCHEMA = [
    {"key": "surrender_value", "label": "Surrender Value", "type": "number", "description": "The amount payable upon surrender of the policy."},
    {"key": "income_payout", "label": "Income Payout", "type": "number", "description": "The amount of income paid out during the income phase."},
    {"key": "death_benefit", "label": "Death Benefit", "type": "number", "description": "The amount payable upon the death of the insured."},
    {"key": "total_payout", "label": "Total Payout", "type": "number", "description": "The total amount payable for the selected event."},
    {"key": "notes", "label": "Notes", "type": "text", "description": "Additional information regarding the payout."}
]

def simulate(inputs):
    event = inputs.get("event", "claim")
    sum_assured = inputs.get("sum_assured", 100000)
    entry_age = inputs.get("entry_age", 30)
    gender = inputs.get("gender", "male")
    claim_year = inputs.get("claim_year", 10)
    surrender_year = inputs.get("surrender_year", 10)
    accumulation_year = inputs.get("accumulation_year", 5)

    result = {
        "surrender_value": 0,
        "income_payout": 0,
        "death_benefit": 0,
        "total_payout": 0,
        "notes": ""
    }

    if event == "claim":
        result["death_benefit"] = sum_assured
        result["total_payout"] = result["death_benefit"]
        result["notes"] = "Death benefit paid out."

    elif event == "surrender":
        result["surrender_value"] = sum_assured * 0.5  # Example calculation
        result["total_payout"] = result["surrender_value"]
        result["notes"] = "Surrender value calculated."

    elif event == "maturity":
        result["total_payout"] = sum_assured
        result["notes"] = "Maturity benefit paid out."

    elif event == "income":
        result["income_payout"] = sum_assured * 0.1  # Example calculation
        result["total_payout"] = result["income_payout"]
        result["notes"] = "Income payout calculated."

    return result

if __name__ == "__main__":
    import json, sys
    print(json.dumps(simulate(json.loads(sys.stdin.read()))))