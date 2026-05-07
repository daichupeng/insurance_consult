from typing import Dict, List, Literal, Annotated, Any, Optional, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from agents.claim_agent.substates import AnalyzerState
from graphs.claim_agent.state import CostItem 


class InitialCostAnalysis(BaseModel):
    cost_items: List[CostItem]
    missing_info: List[str] = Field(description="Further information needed for a comprehensive analysis.")

def cost_node(state: AnalyzerState, llm) -> Dict:
    print("[ClaimAgent]: cost analysis...")
    prompt = """
    You are an expert Medical Insurance Analyst. Your task is to identify the already incurred costs of an incident and suggest the options the costs could be claimed under.

    Instructions:
    1. Identify what costs the user has already incurred relating to the medical incident. 
    2. For each of the cost items, suggest what the cost could be claimed as. For example, accident, in-patient, out-patient at specialist, day surgery etc.
    3. It is possible that one cost item could have multiple categorizations. Describe all the possible categorizations and the underlying assumptions. For example, an X-ray test might be claimed under out-patient; however if there is a surgery after the test, it could be claimed as pre-surgery in-patient cost.
    4. Try to get a comprehensive understanding of the already incurred costs. If you think the user can provide more information, add to the field "missing info"
    5. If the user explicitly says they do not have certain information, or responded that a certain cost item is not incurred, do not ask the same questions repetitively.
    
    Provide professional, detailed, and holistic cost analysis.
    """

    user_prompt = """
    Information from the user so far:
    Tests done: {tests_done}
    Procedures conducted: {procedures_conducted}
    Costs captured: {cost_str}
    """

    cost_str = ' | '.join(f'Item: {c.item_name}. Cost: {c.item_cost}. Relevant insurance: {c.relevant_insurance_type}' for c in state.get('incurred_cost_items'))

    formated_user_prompt = user_prompt.format(tests_done=state.get('tests_done'),procedures_conducted=state.get('procedures_conducted'),cost_str=cost_str) 

    structured_llm = llm.with_structured_output(InitialCostAnalysis, method="function_calling")
    resp: InitialCostAnalysis = structured_llm.invoke([SystemMessage(content=prompt), HumanMessage(content=formated_user_prompt)] + state.get('messages', []))
    
        
    return {"incurred_cost_items": resp.cost_items, "missing_info": resp.missing_info}