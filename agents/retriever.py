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
            if state['current_criterion_index'] + 1 >= len(state['criteria']): return "end"
            return "next"
            
        def increment(state):
            # To clear history for the next criterion, we might need a custom approach or just let it build up.
            return {"current_criterion_index": state['current_criterion_index'] + 1}
            
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
        criterion = state['criteria'][state['current_criterion_index']]
        
        system_prompt = SystemMessage(content=(
            f"You are a Query Planner for a life insurance database. Your current goal is to find information about:\n"
            f"Item: {criterion.item}\n"
            f"Description: {criterion.description}\n\n"
            f"Hard filters to consider: {state['filters']}\n\n"
            f"Use the provided tools to search the document database. Break down the criterion into specific sub-queries if necessary. "
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

    def retrieve(self, criteria: ScoringCriteria) -> List[str]:
        """Executes intelligent multi-step planning retrieval based on the parsed criteria."""
        
        initial_state = RetrieverState(
            criteria=criteria.criteria,
            filters=criteria.filters,
            current_criterion_index=0,
            collected_context=[],
            messages=[]
        )
        
        final_state = self.app.invoke(initial_state)
        return final_state["collected_context"]