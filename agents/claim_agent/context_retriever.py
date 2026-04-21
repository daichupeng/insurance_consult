from typing import Dict
from langchain_core.messages import SystemMessage

from graphs.claim_agent.state import ClaimAgentState
from tools.claim_agent.policy_tools import find_md_file, extract_text

def context_retriever(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent] Running context_retriever...")
    updated_policies = []
    scenario = state.get("claim_scenario", "")
    details = state.get("claim_details", {})
    
    for p in state["relevant_policies"]:
        md_file = find_md_file(p["insurance_name"])
        context_list = p["retrieved_contexts"][:]
        
        if md_file:
            doc_text = extract_text(md_file)
            prompt = f"""
            You are searching an insurance policy document for: {p['insurance_name']}
            
            Incident Scenario: {scenario}
            Details: {details}
            
            Based on the incident, extract all relevant coverage clauses, claim procedures, wait periods, and exclusions from the document below.
            If nothing is relevant, say 'No relevant coverage found.'
            
            --- DOCUMENT ---
            {doc_text[:100000]}
            --- END ---
            """
            res = llm.invoke([SystemMessage(content=prompt)])
            context_list.append(res.content)
        else:
            context_list.append("Policy document not found locally.")
            
        p_copy = p.copy()
        p_copy["retrieved_contexts"] = context_list
        updated_policies.append(p_copy)
        
    return {"relevant_policies": updated_policies}
