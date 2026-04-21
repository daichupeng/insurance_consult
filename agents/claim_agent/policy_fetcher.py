import sqlite3
from typing import Dict, List

from graphs.claim_agent.state import ClaimAgentState, PolicyContext
from api.db import DB_PATH

def policy_fetcher(state: ClaimAgentState) -> Dict:
    print("[ClaimAgent] Running policy_fetcher...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    policies = conn.execute("SELECT * FROM policies WHERE status = 'in_effect'").fetchall()
    conn.close()

    relevant_policies: List[PolicyContext] = []
    for p in policies:
        relevant_policies.append({
            "policy_id": p["id"],
            "insurance_name": p["insurance_name"],
            "category": p["category"],
            "medical_type": p["type"],
            "retrieved_contexts": []
        })

    return {"relevant_policies": relevant_policies}
