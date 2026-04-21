from typing import Dict
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from graphs.claim_agent.state import ClaimAgentState

from typing import Literal

class ReviewResult(BaseModel):
    decision: Literal['pass', 'need_info', 'rewrite'] = Field(description="Decision on the strategy. Must be 'pass', 'need_info', or 'rewrite'")
    feedback: str = Field(description="Why this decision was made. If rewrite or need_info, specific instructions.")

def reviewer(state: ClaimAgentState, llm) -> Dict:
    print("[ClaimAgent] Running reviewer...")
    prompt = f"""
    You are a reviewer for an insurance claim strategy.
    
    Incident: {state['claim_scenario']}
    Drafted Strategy:
    {state['claim_strategy']}
    
    Evaluate if the strategy strictly aligns with standard insurance logic.
    Decide between: 'pass', 'need_info', or 'rewrite'.
    """
    
    structured_llm = llm.with_structured_output(ReviewResult, method="function_calling")
    res: ReviewResult = structured_llm.invoke([SystemMessage(content=prompt)])
    
    return {"review_status": res.decision}
