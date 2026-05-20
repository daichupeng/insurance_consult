from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from graphs.claim_agent.state import Diagnosis, ClaimAgentState

class DiagnosisList(BaseModel):
    diagnoses: List[Diagnosis] = Field(description="A list of possible diagnoses in order of probability.")

def diagnosis_node(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent]: diagnosis analysis...")
    system_prompt = """
    You are an expert medical diagnostician. You need to analyze the known symptoms, tests done, procedures conducted and preliminary diagnosis to determine the most likely diagnoses and their priority.

    Instructions:
    1. Identify all possible diagnoses based on the symptoms, tests done, procedures conducted and preliminary diagnosis. 
    2. List them all in order of probability. Set the most likely diagnosis as priority 1, the second most likely diagnosis as priority 2, and so on. 
    3. For each diagnosis, provide the reasoning behind it.
    4. Provide a summary of the incident for each diagnosis, including how the patient got injured/sick and how the symptoms have developed over time. For example: "The patient broke their collarbone after falling off a ladder, and they have been casted in the A&E." "The patient contracted dengue fever after a trip to Thailand." "An unknown reason resulted in the food poisoning for the patient, and they have recovered after treatment."
    
    Provide professional, detailed, and comprehensive output.
    """

    user_prompt = """
    Symptoms: {symptoms}
    Tests done: {tests_done}
    Procedures conducted: {procedures_conducted}
    Preliminary Diagnosis: {diagnosis_str}
    """

    formated_user_prompt = user_prompt.format(
        symptoms=state.get('symptoms'),
        tests_done=state.get('tests_done'),
        procedures_conducted=state.get('procedures_conducted'),
        diagnosis_str=state.get('primary_diagnosis')
        )

    structured_llm = llm.with_structured_output(DiagnosisList, method="function_calling")
    resp: DiagnosisList = structured_llm.invoke([SystemMessage(content=system_prompt),HumanMessage(content=formated_user_prompt)])
    
    return {"possible_diagnoses": resp.diagnoses[:2]}
