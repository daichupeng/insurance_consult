from schema.models import UserProfile, ScoringItem, ScoringCriteria
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
            "You are an expert life insurance consultant. Based on the provided user profile, generate 3 to 5 key scoring criteria that should be used to evaluate and compare different life insurance policies for this specific user. Each criterion should include an item name, a description, clear scoring rules (1-5 scale), and a weight. The weights of the items should sum up to 100."
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "User Profile:\n{profile_details}")
        ])

    def generate_criteria(self, profile: UserProfile) -> List[ScoringItem]:
        """Generates comparison points (criteria) for insurance policies based on the user's profile and goals."""
        profile_dict = profile.model_dump(exclude_none=True)
        profile_details = "\n".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in profile_dict.items()])
        
        chain = self.prompt | self.llm_structured
        result: ScoringCriteria = chain.invoke({"profile_details": profile_details})
        
        return result.criteria