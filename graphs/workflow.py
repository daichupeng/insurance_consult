from langgraph.graph import StateGraph, START, END
from graphs.state import AgentState
from schema.models import ScoringCriteria

# Import nodes (agents)
from agents.profile_analyzer import ProfileAnalyzer
from agents.criteria_generator import CriteriaGenerator
from agents.policy_scorer import PolicyScorer
from agents.scoring_reviewer import ScoringReviewer
from agents.report_writer import ReportWriter
from agents.graph_rag_retriever import GraphRAGRetriever

import logging

logger = logging.getLogger(__name__)

# Initialize components
profile_analyzer = ProfileAnalyzer()
criteria_generator = CriteriaGenerator()
retriever = GraphRAGRetriever()
policy_scorer = PolicyScorer()
scoring_reviewer = ScoringReviewer()
report_writer = ReportWriter()

# Node Functions
def profile_analyzer_node(state: AgentState) -> dict:
    # Use the most recent message as user input
    messages = state.get("messages", [])
    if not messages:
        user_input = ""
    else:
        # Assuming LangChain format Dict message handling, taking the last HumanMessage content
        user_input = messages[-1].get("content", "") if isinstance(messages[-1], dict) else getattr(messages[-1], "content", "")
    
    
    existing_profile = state.get("user_requirements")
    extracted_profile, messages = profile_analyzer.analyze_profile(user_input, existing_profile=existing_profile)
    
    return {
        "user_requirements": extracted_profile,
        "messages": messages
    }

def criteria_generator_node(state: AgentState) -> dict:
    profile = state.get("user_requirements")
    if not profile:
        # Failsafe if we somehow entered without a profile
        return {"criteria": ScoringCriteria(criteria=[], filters=[])}
        
    criteria = criteria_generator.generate_criteria(profile)
    return {"criteria": criteria}

def retriever_node(state: AgentState) -> dict:
    criteria = state['criteria']
    if not criteria.criteria and not criteria.filters:
        return {"policies": []}
        
    retrieved_policies = retriever.retrieve(criteria)
    return {"policies": retrieved_policies}

def policy_scorer_node(state: AgentState) -> dict:
    policies = state.get('policies', [])
    criteria = state.get('criteria')
    
    if not policies or not criteria:
        return {"policies": policies}
        
    evaluated_policies = policy_scorer.score_policies(policies, criteria)
    return {"policies": evaluated_policies}


def main():

    workflow = StateGraph(AgentState)
    workflow.add_node("profile_analyzer", profile_analyzer_node)
    workflow.add_node("criteria_generator", criteria_generator_node)
    workflow.add_node("retriever_node", retriever_node)
    workflow.add_node("policy_scorer_node", policy_scorer_node)

    workflow.add_edge(START, "profile_analyzer")
    workflow.add_edge("profile_analyzer", "criteria_generator")
    workflow.add_edge("criteria_generator", "retriever_node")
    workflow.add_edge("retriever_node", "policy_scorer_node")
    workflow.add_edge("policy_scorer_node", END)

    app = workflow.compile()

    state = AgentState(messages=messages)

    state = app.invoke(state)


if __name__ == "__main__":
    main()