import logging
from typing import Dict, List
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from graphs.claim_agent.state import ClaimAgentState

logger = logging.getLogger(__name__)

class ClaimDetailParameter(BaseModel):
    key: str = Field(description="Name of the detail, e.g. 'incident_date', 'claim_amount'")
    value: str = Field(description="Value of the detail.")

class IncidentAnalysisResult(BaseModel):
    claim_scenario: str = Field(description="High-level description of what happened.")
    claim_details: List[ClaimDetailParameter] = Field(description="List of extracted details of the incident.")
    missing_info: bool = Field(description="True if critical information is missing to evaluate a claim. False if sufficient.")
    clarification_question: str = Field(description="If missing_info is True, the exact question to ask the user to clarify.")

def incident_analysis(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent] Running incident_analysis...")
    prompt = """
    Analyze the conversation history and extract the current claim incident details.
    Decide if we have enough information to form a strategy. (At minimum, we need to know what happened, when, and roughly the cost/severity).
    """

    structured_llm = llm.with_structured_output(IncidentAnalysisResult, method="function_calling")
    resp: IncidentAnalysisResult = structured_llm.invoke([
        SystemMessage(content=prompt),
        *state['messages']
    ])

    new_messages = []
    if resp.missing_info and resp.clarification_question:
        new_messages.append({"role": "assistant", "content": resp.clarification_question})

    parsed_details = {d.key: d.value for d in resp.claim_details}

    return {
        "claim_scenario": resp.claim_scenario,
        "claim_details": parsed_details,
        "missing_info": resp.missing_info,
        "messages": new_messages
    }
