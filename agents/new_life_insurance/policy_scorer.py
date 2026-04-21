import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from schema.models import Policy, ScoringItem, ScoringCriteria
from typing import List, Tuple, Dict

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

class FilterEvaluation(BaseModel):
    fulfills: bool = Field(description="Whether the policy fulfills all the hard filters.")
    reasoning: str = Field(description="Explanation of why it fulfills or fails the filters.")

class PolicyCriterionScore(BaseModel):
    policy_index: int = Field(description="The index (1-based) of the evaluated policy.")
    score: int = Field(description="Score assigned to the policy for this criterion (1-5).")
    reasoning: str = Field(description="Explanation for the score based on the retrieved context, comparing to others if applicable.")

class HorizontalCriterionEvaluation(BaseModel):
    evaluations: List[PolicyCriterionScore] = Field(description="List of evaluations for all policies for the given criterion.")

class PolicyScorer:
    def __init__(self):
        self.filter_llm = llm.with_structured_output(FilterEvaluation)
        self.horizontal_scorer_llm = llm.with_structured_output(HorizontalCriterionEvaluation)
        
    @staticmethod
    def _basic_info_text(policy: Policy) -> str:
        info = policy.basic_info
        if not info or info == info.__class__():
            return ""
        return f"Basic Policy Facts (from comparefirst.sg):\n{info.to_text()}"

    def evaluate_filters(self, policy: Policy, filters: List[str]) -> Tuple[bool, str]:
        if not filters:
            return True, "No filters provided."

        # Combine the context summaries for all filters into one text
        context_parts = []
        for f in filters:
            summary = policy.context_summary.get(f, "No relevant context found.")
            context_parts.append(f"Filter: {f}\nSummary: {summary}\n")
            
        context = "\n".join(context_parts)
        filters_str = "\n".join([f"- {f}" for f in filters])
        basic = self._basic_info_text(policy)

        prompt = (
            f"You are evaluating whether a life insurance policy named '{policy.policy_name}' "
            f"meets all of the following hard filters:\n{filters_str}\n\n"
            f"{basic}\n"
            f"\nRetrieved Context Summaries:\n{context}\n\n"
            f"Determine if the policy meets all the constraints. If the context does not explicitly say it fails, "
            f"but lacks complete proof, use your best judgment. Strict failure only if explicitly contradicted or notably absent."
        )

        result = self.filter_llm.invoke([HumanMessage(content=prompt)])
        return result.fulfills, result.reasoning

    def evaluate_criterion_horizontally(self, policies: List[Policy], criterion: ScoringItem) -> Dict[int, Tuple[int, str]]:
        """
        Evaluates a single criterion across all policies simultaneously.
        Returns a dictionary mapping policy_index to (score, reasoning).
        """
        if not policies:
            return {}

        policies_text_parts = []
        for i, p in enumerate(policies):
            basic = self._basic_info_text(p)
            summary = p.context_summary.get(criterion.item, "No relevant context found.")
            policies_text_parts.append(
                f"--- Policy Index [{i+1}]: {p.policy_name} ---\n{basic}\nContext Summary: {summary}\n"
            )
            
        policies_context = "\n".join(policies_text_parts)

        prompt = (
            f"You are scoring multiple life insurance policies simultaneously on the following criterion:\n"
            f"Item: {criterion.item}\n"
            f"Description: {criterion.description}\n"
            f"Scoring Rules: {criterion.scoring_rules}\n\n"
            f"Here is the context and basic information for each policy:\n"
            f"{policies_context}\n\n"
            f"Evaluate all policies against this criterion. Compare them horizontally to ensure scoring is standardized. "
            f"Assign a score out of 5 and provide reasoning for each policy.\n"
            f"IMPORTANT: For `policy_index`, you MUST use the exact integer index (e.g. 1, 2, 3) provided in the headers above."
        )
        
        result = self.horizontal_scorer_llm.invoke([HumanMessage(content=prompt)])
        
        # Map back to a dictionary for easy assignment
        eval_dict = {}
        for eval in result.evaluations:
            eval_dict[eval.policy_index] = (eval.score, eval.reasoning)
            
        return eval_dict

    def score_policies(self, policies: List[Policy], criteria: ScoringCriteria) -> List[Policy]:
        """
        Evaluates a list of policies against the generated criteria and filters using the retrieved context.
        Updates the Policies in place and returns them.
        """
        # 1. Evaluate Filters (per-policy)
        for policy in policies:
            print(f"\n[PolicyScorer]: Evaluating filters for {policy.policy_name}")
            fulfills, filter_reasoning = self.evaluate_filters(policy, criteria.filters)
            policy.fulfil_filters = (fulfills, filter_reasoning)
            
            # Initialize scoring list to be populated below
            policy.scoring = []

        # 2. Evaluate Criteria (horizontally across all policies)
        if criteria.criteria:
            for criterion in criteria.criteria:
                print(f"\n[PolicyScorer]: Evaluating criterion '{criterion.item}' horizontally across {len(policies)} policies")
                horizontal_results = self.evaluate_criterion_horizontally(policies, criterion)
                
                # Assign the results back to the respective policies
                for i, policy in enumerate(policies):
                    score, reason = horizontal_results.get(i + 1, (0, "Failed to score this criterion."))
                    policy.scoring.append((score, criterion, reason))
            
        return policies
