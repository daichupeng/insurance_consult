from functools import partial
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from graphs.claim_agent.state import ClaimAgentState
from agents.claim_agent.incident_analyzer import incident_analysis
from agents.claim_agent.policy_fetcher import policy_fetcher
from agents.claim_agent.context_retriever import context_retriever
from agents.claim_agent.planner import planner
from agents.claim_agent.reviewer import reviewer
import os

from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)


def check_incident_analysis(state: ClaimAgentState):
    if state["missing_info"]:
        return "clarifying"
    return "fetch_policies"

def check_review_status(state: ClaimAgentState):
    status = state["review_status"].lower().strip()
    # Return the keys that map to the path dictionary down below
    if status == "pass":
        return "pass"
    elif status == "need_info":
        return "need_info"
    else: 
        return "rewrite"

graph_builder = StateGraph(ClaimAgentState)

graph_builder.add_node("incident_analysis", partial(incident_analysis, llm=llm))
graph_builder.add_node("policy_fetcher", policy_fetcher)
graph_builder.add_node("context_retriever", partial(context_retriever, llm=llm))
graph_builder.add_node("planner", partial(planner, llm=llm))
graph_builder.add_node("reviewer", partial(reviewer, llm=llm))

graph_builder.set_entry_point("incident_analysis")

graph_builder.add_conditional_edges(
    "incident_analysis",
    check_incident_analysis,
    {
        "clarifying": END,
        "fetch_policies": "policy_fetcher"
    }
)

graph_builder.add_edge("policy_fetcher", "context_retriever")
graph_builder.add_edge("context_retriever", "planner")
graph_builder.add_edge("planner", "reviewer")

graph_builder.add_conditional_edges(
    "reviewer",
    check_review_status,
    {
        "pass": END,
        "need_info": "context_retriever",
        "rewrite": "planner"
    }
)

claim_agent_workflow = graph_builder.compile()
