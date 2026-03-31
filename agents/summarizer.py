import os
import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from schema.models import Policy, ScoringCriteria
from typing import List, Dict

logger = logging.getLogger(__name__)
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

class SummaryResult(BaseModel):
    summary: str = Field(description="A concise summary of the retrieved context relevant to the given filter/criterion.")

class PolicySummarizer:
    def __init__(self):
        self.summary_llm = llm.with_structured_output(SummaryResult)
        
    def summarize_context(self, context_list: List[str], topic: str) -> str:
        if not context_list:
            return "No relevant context found."
            
        context_str = "\n\n".join(context_list)
        prompt = (
            f"You are given a set of retrieved text excerpts from a life insurance policy document.\n"
            f"Your task is to summarize these excerpts specifically regarding the topic: '{topic}'.\n"
            f"Keep it concise, factual, and strictly based on the provided text. Ignore irrelevant parts.\n"
            f"If there is no useful information regarding the topic, simply state that.\n\n"
            f"Excerpts:\n{context_str}"
        )
        
        try:
            result = self.summary_llm.invoke([HumanMessage(content=prompt)])
            return result.summary
        except Exception as e:
            logger.error(f"[PolicySummarizer] Error summarizing context for '{topic}': {e}")
            return "Failed to summarize context."

    def summarize_policies(self, policies: List[Policy], criteria: ScoringCriteria) -> List[Policy]:
        """
        Summarizes the retrieved context for each policy based on the filters and criteria.
        Updates the Policies in place and returns them.
        """
        if not policies:
            return policies
            
        # Collect all expected keys
        expected_keys = []
        for f in (criteria.filters or []):
            expected_keys.append(f)
        for c in (criteria.criteria or []):
            expected_keys.append(c.item)

        for policy in policies:
            logger.info(f"[PolicySummarizer]: Summarizing context for {policy.policy_name}")
            summary_dict = {}
            for key in expected_keys:
                contexts = policy.retrieved_context.get(key, [])
                summary = self.summarize_context(contexts, key)
                summary_dict[key] = summary
            policy.context_summary = summary_dict
            
        return policies
