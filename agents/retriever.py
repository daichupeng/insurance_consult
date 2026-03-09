from typing import List, Dict, Any, Literal, Annotated
import operator
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from schema.models import ScoringItem, ScoringCriteria, RetrieverState

import os
from dotenv import load_dotenv

from tools.search_tools import search_policy_docs, get_policy_summary, query_expansion, list_available_policies

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)


# Define the sub-graph nodes within the class
class Retriever:
    def __init__(self, vector_store=None):
        self.vector_store = vector_store
        
        # Proper routing for the loop
        retriever_workflow = StateGraph(RetrieverState)
        retriever_workflow.add_node("query_planner", self.query_planner_node)
        retriever_workflow.add_node("tool_executor", self.tool_executor_node)
        
        def route_tools(state):
            last_msg = state['messages'][-1]
            if getattr(last_msg, "tool_calls", None): return "tools"
            if state['current_item_index'] + 1 >= len(state['search_items']): return "end"
            return "next"
            
        def increment(state):
            # To clear history for the next criterion, we might need a custom approach or just let it build up.
            return {"current_item_index": state['current_item_index'] + 1}
            
        retriever_workflow.add_node("increment", increment)
        
        retriever_workflow.add_edge(START, "query_planner")
        retriever_workflow.add_conditional_edges("query_planner", route_tools, {
            "tools": "tool_executor",
            "next": "increment",
            "end": END
        })
        retriever_workflow.add_edge("tool_executor", "query_planner")
        retriever_workflow.add_edge("increment", "query_planner")
        
        self.app = retriever_workflow.compile()

    def query_planner_node(self, state: RetrieverState) -> dict:
        item = state['search_items'][state['current_item_index']]
        
        if state.get('mode') == 'filter':
            goal_text = f"Your current goal is to find information regarding this hard filter constraint:\nFilter: {item.description}\n\n"
        else:
            goal_text = f"Your current goal is to find information about:\nItem: {item.item}\nDescription: {item.description}\n\n"
            
        system_prompt = SystemMessage(content=(
            f"You are a Query Planner for a life insurance database. {goal_text}"
            f"Use the provided tools to search the document database. Break down the objective into specific sub-queries if necessary. "
            f"Execute searches, process the results, and when you are satisfied you have gathered enough context, just say 'DONE'."
        ))
        
        messages = [system_prompt] + state['messages']
        llm_with_tools = llm.bind_tools([search_policy_docs, get_policy_summary, query_expansion, list_available_policies])
        
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def tool_executor_node(self, state: RetrieverState) -> dict:
        last_message = state['messages'][-1]
        tool_messages = []
        collected = []
        
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "search_policy_docs":
                res = search_policy_docs.invoke(tool_call["args"])
                collected.append(f"Result for '{tool_call['args'].get('query')}':\n{res}")
            elif tool_call["name"] == "get_policy_summary":
                res = get_policy_summary.invoke(tool_call["args"])
                collected.append(f"Summary:\n{res}")
            elif tool_call["name"] == "query_expansion":
                res = query_expansion.invoke(tool_call["args"])
                # Format list back into string for tool response
                res = ", ".join(res)
            elif tool_call["name"] == "list_available_policies":
                res = list_available_policies.invoke(tool_call["args"])
                collected.append(f"{res}")
                
            tool_messages.append(ToolMessage(content=str(res), tool_call_id=tool_call["id"]))
            
        return {
            "messages": tool_messages,
            "collected_context": collected
        }

    def retrieve(self, criteria: ScoringCriteria) -> List['schema.models.Policy']:
        """Executes intelligent multi-step planning retrieval for all policies."""
        from schema.models import Policy, ScoringItem

        # Get the list of all available policies
        policies_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'raw_policies', 'aia'))
        available_policies = []
        if os.path.exists(policies_dir):
            for filename in os.listdir(policies_dir):
                if filename.endswith(".pdf"):
                    available_policies.append(filename[:-4])

        all_policies = []

        for policy_name in available_policies:
            print(f"\n[Retriever]: Processing {policy_name}")
            
            # 1. Retrieve for Filters
            print('Checking filters')
            filters_context = []
            if criteria.filters:
                filter_items = [ScoringItem(item="Hard Filter Requirement", description=f, scoring_rules="N/A", weight=0) for f in criteria.filters]
                filter_state = RetrieverState(
                    search_items=filter_items,
                    mode="filter",
                    current_item_index=0,
                    collected_context=[],
                    messages=[SystemMessage(content=f"Focus solely on the policy named: {policy_name}")]
                )
                filters_context = self.app.invoke(filter_state)["collected_context"]

            # 2. Retrieve for Criteria
            print('Checking criteria')
            criteria_context = []
            if criteria.criteria:
                criteria_state = RetrieverState(
                    search_items=criteria.criteria,
                    mode="criterion",
                    current_item_index=0,
                    collected_context=[],
                    messages=[SystemMessage(content=f"Focus solely on the policy named: {policy_name}")]
                )
                criteria_context = self.app.invoke(criteria_state)["collected_context"]

            # 3. Create Policy Object
            policy_obj = Policy(
                policy_name=policy_name,
                fulfil_filters=(False, "Pending evaluation by Policy Scorer"),
                scoring=[(0, ScoringItem(item="Pending", description="", scoring_rules="", weight=0),"Pending evaluation by Policy Scorer")],
                retrieved_context={
                    "filters": filters_context,
                    "criteria": criteria_context
                }
            )
            all_policies.append(policy_obj)


        return all_policies