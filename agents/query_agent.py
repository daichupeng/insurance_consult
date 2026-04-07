import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.graphrag_tools import (
    graphrag_local_search,
    graphrag_global_search,
    list_available_policies,
    remove_context,
    query_expansion
)

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

class QueryAgent:
    def __init__(self):
        tools = [
            graphrag_local_search,
            graphrag_global_search,
            list_available_policies,
            remove_context,
            query_expansion
        ]
        
        system_prompt = (
            "You are a helpful and professional life insurance assistant. "
            "You are tasked with answering user questions after they have completed "
            "an insurance comparison analysis.\n"
            "Use the provided context (user requirements, scoring criteria, and evaluated policies) "
            "to give highly relevant and tailored answers.\n"
            "If the information is not present in the context, please use your GraphRAG tools "
            "(e.g., graphrag_local_search, graphrag_global_search) to search the available policy documents "
            "and find the correct details before answering.\n"
            "Keep your explanations clear, concise, and easy to understand."
        )
        
        self.agent_executor = create_react_agent(llm, tools)
        self.messages = [SystemMessage(content=system_prompt)]
        self.has_injected_context = False

    def _format_context(self, requirements: dict, criteria: dict, policies: list) -> str:
        # Simplify requirements text
        req_text = str(requirements) if requirements else "None"
        
        # Simplify criteria
        crit_text = ""
        if criteria and "criteria" in criteria:
            crit_text = "\n".join(
                [f"- {c['item']} (Weight: {c['weight']}%): {c.get('description', '')}" 
                 for c in criteria["criteria"]]
            )
        
        # Simplify policies (just names and scores to keep context window manageable)
        pol_text = ""
        if policies:
            top_policies = sorted(
                policies, 
                key=lambda p: sum(item[0] * (item[1]['weight'] / 100) for item in p.get('scoring', [])),
                reverse=True
            )[:3] # Just top 3
            
            for p in top_policies:
                score = sum(item[0] * (item[1]['weight'] / 100) for item in p.get('scoring', []))
                pol_text += f"- Policy: {p.get('policy_name', 'Unknown')} (Score: {score:.1f}/5)\n"
        
        return (
            f"--- SESSION CONTEXT ---\n"
            f"User Requirements: {req_text}\n\n"
            f"Scoring Criteria:\n{crit_text}\n\n"
            f"Top Evaluated Policies:\n{pol_text}\n"
            f"-----------------------\n"
        )

    def answer_query(self, query: str, requirements: dict, criteria: dict, policies: list) -> str:
        print(f"\n[QueryAgent] Processing query: {query}")
        
        if not self.has_injected_context:
            context_str = self._format_context(requirements, criteria, policies)
            self.messages.append(SystemMessage(content=context_str))
            self.has_injected_context = True
            
        self.messages.append(HumanMessage(content=query))
        
        # Invoke agent
        response = self.agent_executor.invoke({"messages": self.messages})
        
        # Update messages array with new returned messages to keep chat history
        self.messages = response["messages"]
        
        # Return the content of the last AI message
        return self.messages[-1].content
