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

        reviewer_feedback = state.get("review_feedback", "")
        reviewer_text = ""
        if reviewer_feedback:
            reviewer_text = f"""
            Reviewer Feedback on the previously retrieved contexts: {reviewer_feedback}

            Make sure retrieve contexts to address the reviewer's feedback.
            """
        
        if md_file:
            doc_text = extract_text(md_file)
            prompt = f"""
            You are searching for relevant context in the {p['insurance_name']} insurance policy document for an incident. 
            
            Incident Scenario: {scenario}
            Details: {details}
            
            {reviewer_text}

            Based on the incident details and the reviewer's feedback if any, extract all relevant coverage clauses, claim procedures, wait periods, and exclusions from the document below.
            Make sure all relevant contexts are captured to maximize the user's claim possibility. 
            If nothing is relevant, say 'No relevant coverage found.'
            If there are relevant contexts but the user's case is explicitly excluded, also retrieve the context of the exclusion.  
            
            --- DOCUMENT ---
            {doc_text}
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
