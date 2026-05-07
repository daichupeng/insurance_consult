from typing import Dict
from langchain_core.messages import SystemMessage

from graphs.claim_agent.state import ClaimAgentState
from agents.claim_agent.substates import TreatmentState
from tools.claim_agent.policy_tools import find_md_file, extract_text

def context_retriever(state: TreatmentState, llm) -> Dict:
    print("[ClaimAgent] Running context_retriever...")
    updated_policies = []
    diagnosis = state.get('diagnosis')
    symptoms = state.get('symptoms', [])
    tests_done = state.get('tests_done', [])
    procedures_conducted = state.get('procedures_conducted', [])
    consultations_needed = state.get('consultations_needed', [])
    tests_needed = state.get('tests_needed', [])
    procedures_needed = state.get('procedures_needed', [])
    prescriptions_needed = state.get('prescriptions_needed', [])
    
    for p in state.get("relevant_policies", []):
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
            
            Tests done: {tests_done}
            Procedures conducted: {procedures_conducted}

            Suggested treatment plan:
            Consultations needed: {consultations_needed}
            Tests needed: {tests_needed}
            Procedures needed: {procedures_needed}
            Prescriptions needed: {prescriptions_needed}
            
            {reviewer_text}

            Based on the incident details and the reviewer's feedback if any, extract all relevant coverage clauses, claim procedures, wait periods, and exclusions from the document below.
            Make sure all relevant contexts are captured to maximize the user's claim possibility. 
            Specify the conditions for the coverage. For example, cost is incurred within X days from a certain incident; coverage only for public hospital; etc.
            If there are relevant contexts but the user's case is explicitly excluded, also retrieve the context of the exclusion.  
            If nothing is relevant, say 'No relevant coverage found.'
            If there is a reviewer's feedback, focus on the feedback only.
            
            --- DOCUMENT ---
            {doc_text}
            --- END ---
            """
            res = llm.invoke([SystemMessage(content=prompt)])
            context_list.append(f"Relevant coverage terms of {p['insurance_name']}:\n{res.content}")
        else:
            context_list.append(f"Relevant coverage terms of {p['insurance_name']}:\nPolicy document not found locally.")
            
        p_copy = p.copy()
        p_copy["retrieved_contexts"] = context_list
        updated_policies.append(p_copy)
        
    return {"relevant_policies": updated_policies}
