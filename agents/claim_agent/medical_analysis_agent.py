from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from agents.claim_agent.substates import AnalyzerState
from graphs.claim_agent.state import CostItem


class MedicalAnalysis(BaseModel):
    symptoms: List[str] = Field(description="List of clinical symptoms identified.")
    tests_done: List[str] = Field(description="Test results that are already known")
    procedures_conducted: List[str] = Field(description="Medical tests or treatments already performed.")
    primary_diagnosis: Optional[str] = Field(description="The confirmed or suspected medical condition. Be specific about the certainty. For example,Confirmed appendicitis; suspected viral infection or pneumonia; not sure yet.")
    questions_for_patient: List[str] = Field(description="Questions for the user to gather more information as much as the patient can provide at the time being. Do not ask questions that they are not able to provide answers to.")

def medical_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: medical analysis...")
    prompt = """
    You are an expert Medical Claims Analyst. Your task is to collect medical information for futher diagnosis.
    
    Instructions:
    1. Holistically record the medical incident, detailing the exact nature of the injury or illness.
    2. Identify all known symptoms, test results, and treatments procedures already done. If the user has already received treatments, ask whether there has been a confirmed diagnosis. If not, does the doctor suspect certain diagnosis but unsure?
    3. List any missing medical information critical for a thorough incident assessment, unless the user explicitly indicates such information is not available. If the user is unable to provide certain information due to the nature of the incident or current constraints, record as is.
    4. If the user has already provided a negative answer (e.g., 'no', 'none', 'I don't know', 'haven't done', 'not sure') to a specific question, DO NOT list it as missing info.
    5. If the user has already provided an answer to a certain question, regardless whether they provided a confirmed answer, or explicitly expressed thay are unable to provide any information, remove that question from the questions_for_patient list.
    6. Do not make any assumptions. Record only the confirmed information.
    
    Provide professional, detailed, and comprehensive output.
    """

    user_prompt = """
    Information from the user so far:
    Symptoms: {symptoms}
    Tests done: {tests_done}
    Procedures conducted: {procedures_conducted}
    Current suspected diagnosis: {diagnosis_str}
    """
    formated_user_prompt = user_prompt.format(
        symptoms=state.get('symptoms'),
        tests_done=state.get('tests_done'),
        procedures_conducted=state.get('procedures_conducted'),
        diagnosis_str=state.get('primary_diagnosis',"Unknown")
        )
    

    structured_llm = llm.with_structured_output(MedicalAnalysis, method="function_calling")
    resp: MedicalAnalysis = structured_llm.invoke([SystemMessage(content=prompt),HumanMessage(content=formated_user_prompt)] + state.get('messages', []))
    

    if not resp.primary_diagnosis:
        diagnosis_str = state.get('primary_diagnosis')
    else:
        diagnosis_str = resp.primary_diagnosis
        
    return {'symptoms': resp.symptoms,
    'tests_done': resp.tests_done,
    'procedures_conducted': resp.procedures_conducted,
    'primary_diagnosis': diagnosis_str,
    'missing_info':resp.questions_for_patient}