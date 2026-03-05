# This needs to be optimized into a dynamic planner / reflexion, using meta prompting. For now I keep it simple first.



from schema.models import UserRequirements, ScoringItem, ScoringCriteria
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing import List

import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

class CriteriaGenerator:
    def __init__(self):
        self.llm_structured = llm.with_structured_output(ScoringCriteria)
        
        system_prompt = (
            "You are an expert life insurance consultant. Based on the provided user profile, generate some key scoring criteria that should be used to evaluate and compare different life insurance policies for this specific user. The weights of the items should sum up to 100."
            "Also, generate a list of hard filters for the policy. Certain policies should be excluded based on these filters."
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "User Profile:\n{profile_details}")
        ])

    def generate_criteria(self, profile: UserRequirements) -> ScoringCriteria:
        """Generates comparison points (criteria) for insurance policies based on the user's profile and goals."""
        profile_dict = profile.model_dump(exclude_none=True)
        profile_details = "\n".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in profile_dict.items()])
        
        chain = self.prompt | self.llm_structured
        result: ScoringCriteria = chain.invoke({"profile_details": profile_details})
        
        return result