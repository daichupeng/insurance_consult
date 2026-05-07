from functools import partial
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from graphs.claim_agent.state import ClaimAgentState
from agents.claim_agent.incident_analyzer import incident_analysis
from agents.claim_agent.diagnosis_agent import diagnosis_node
from agents.claim_agent.advisor import advisor_node
import os

from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)


def route_to_advisors(state: ClaimAgentState):
    """
    Creates a 'Send' for every diagnosis in the list.
    """
    # Logic: For every diagnosis, spawn an advisor_node with a specific payload
    return [
        Send("advisor_node", {
            "diagnosis": d,
            "symptoms": state.get("symptoms", []),
            "tests_done": state.get("tests_done", []),
            "procedures_conducted": state.get("procedures_conducted", []),
            "incurred_cost_items": state.get("incurred_cost_items", [])
        }) for d in state.get("possible_diagnoses", [])
    ]

def route_after_incident(state: ClaimAgentState):
    if len(state.get("missing_info", [])) > 0:
        return END
    return "diagnosis_node"



graph_builder = StateGraph(ClaimAgentState)

graph_builder.add_node("incident_analysis", partial(incident_analysis, llm=llm))
graph_builder.add_node("diagnosis_node", partial(diagnosis_node, llm=llm))
graph_builder.add_node("advisor_node", partial(advisor_node, llm=llm))

graph_builder.set_entry_point("incident_analysis")

graph_builder.add_conditional_edges("incident_analysis", route_after_incident)
graph_builder.add_conditional_edges("diagnosis_node", route_to_advisors)
graph_builder.add_edge("advisor_node", END)

claim_agent_workflow = graph_builder.compile()
