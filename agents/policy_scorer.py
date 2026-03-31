import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from schema.models import Policy, ScoringItem, ScoringCriteria
from typing import List, Tuple

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

class FilterEvaluation(BaseModel):
    fulfills: bool = Field(description="Whether the policy fulfills all the hard filters.")
    reasoning: str = Field(description="Explanation of why it fulfills or fails the filters.")

class CriterionEvaluation(BaseModel):
    score: int = Field(description="Score assigned to the policy for this criterion (1-5).")
    reasoning: str = Field(description="Explanation for the score based on the retrieved context.")

class PolicyScorer:
    def __init__(self):
        self.filter_llm = llm.with_structured_output(FilterEvaluation)
        self.scorer_llm = llm.with_structured_output(CriterionEvaluation)
        
    @staticmethod
    def _basic_info_text(policy: Policy) -> str:
        info = policy.basic_info
        if not info or info == info.__class__():
            return ""
        return f"\nBasic Policy Facts (from comparefirst.sg):\n{info.to_text()}\n"

    def evaluate_filters(self, policy: Policy, filters: List[str]) -> Tuple[bool, str]:
        if not filters:
            return True, "No filters provided."

        context = "\n".join(policy.retrieved_context.get("filters", []))
        filters_str = "\n".join([f"- {f}" for f in filters])
        basic = self._basic_info_text(policy)

        prompt = (
            f"You are evaluating whether a life insurance policy named '{policy.policy_name}' "
            f"meets all of the following hard filters:\n{filters_str}\n"
            f"{basic}"
            f"\nRetrieved Context from Policy Documents:\n{context}\n\n"
            f"Determine if the policy meets all the constraints. If the context does not explicitly say it fails, "
            f"but lacks complete proof, use your best judgment. Strict failure only if explicitly contradicted or notably absent."
        )

        result = self.filter_llm.invoke([HumanMessage(content=prompt)])
        return result.fulfills, result.reasoning

    def evaluate_criterion(self, policy: Policy, criterion: ScoringItem) -> Tuple[int, str]:
        context = "\n".join(policy.retrieved_context.get("criteria", []))
        basic = self._basic_info_text(policy)

        prompt = (
            f"You are scoring a life insurance policy named '{policy.policy_name}' on the following criterion:\n"
            f"Item: {criterion.item}\n"
            f"Description: {criterion.description}\n"
            f"Scoring Rules: {criterion.scoring_rules}\n"
            f"{basic}"
            f"\nRetrieved Context from Policy Documents:\n{context}\n\n"
            f"Evaluate the policy against this criterion based on the context and the basic policy facts above. "
            f"Assign a score out of 5 and provide reasoning."
        )
        
        result = self.scorer_llm.invoke([HumanMessage(content=prompt)])
        return result.score, result.reasoning

    def score_policies(self, policies: List[Policy], criteria: ScoringCriteria) -> List[Policy]:
        """
        Evaluates a list of policies against the generated criteria and filters using the retrieved context.
        Updates the Policies in place and returns them.
        """
        evaluated_policies = []
        for policy in policies:
            print(f"\n[PolicyScorer]: Evaluating {policy.policy_name}")
            
            # Evaluate Filters
            fulfills, filter_reasoning = self.evaluate_filters(policy, criteria.filters)
            policy.fulfil_filters = (fulfills, filter_reasoning)
            
            # Evaluate Criteria
            scored_items = []
            if criteria.criteria:
                for criterion in criteria.criteria:
                    score, reason = self.evaluate_criterion(policy, criterion)
                    scored_items.append((score, criterion, reason))
                
            policy.scoring = scored_items
            evaluated_policies.append(policy)
            
        return evaluated_policies
