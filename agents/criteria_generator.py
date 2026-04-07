# This needs to be optimized into a dynamic planner / reflexion, using meta prompting. For now I keep it simple first.



from schema.models import UserRequirements, ScoringItem, ScoringCriteria
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing import List, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)


class CriteriaReflection(BaseModel):
    is_perfect: bool = Field(description="True if the criteria exactly matches requirements and weights sum to 100.")
    feedback: str = Field(description="Constructive feedback on how to improve. Blank if perfect.")


class GeneratorState(TypedDict):
    profile_details: str
    criteria: ScoringCriteria
    feedback: str
    iterations: int


class CriteriaGenerator:
    def __init__(self):
        self.llm_structured = llm.with_structured_output(ScoringCriteria)
        self.reflector_llm = llm.with_structured_output(CriteriaReflection)
        
        system_prompt = (
            "You are a Senior Wealth Strategist specializing in insurance. Your task is to design a decision framework for a life insurance acquisition based on the user requirements and the feedbacks given to your previous framework."
            "Logical Directives: "
            "- Constraint vs. Optimization: Do not score parameters that are binary requirements. Scoring should be reserved for 'differentiators'."
            "- MECE Framework: Ensure criteria are Mutually Exclusive and Collectively Exhaustive. There should be zero overlapping."
            "- Focus on the non-monetary factors. Do not consider the premium cost and payouts."
            "Output Requirements:"
            "- Hard Filters: Essential 'must-haves' that disqualify a policy immediately. The hard filters should not include the basic search conditions: coverage sum, smoker status, age, gender, insurance type, critical illness option."
            "- Scoring Criteria: 2-4 most important variables with weights totaling exactly 100."
            "- Explanation: Briefly describe the criterion and justification."
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "User Profile:\n{profile_details}\n\nPrevious Framework (if any):\n{previous_framework}\n\nFeedback:\n{feedback}")
        ])

        reflector_system_prompt = (
            "You are a Chief Risk Officer auditing an insurance procurement framework for a user. Your role is to identify logical fallacies, redundancies, and strategic misalignments."
            "Audit the framework against these Principles of Excellence:"
            "Optimization Clarity: Are the scoring criteria focused on variables (things that change) rather than constants (things required by the filter)? Scoring a requirement is a logical failure."
            "Conciseness: The framework should be concise and to the point. Avoid redundant criteria; combine or remove trivial and overlapping criteria."
            "Functional MECE: Are the scoring categories and filters truly distinct and cover all important aspects? Identify any 'hidden correlations' where two criteria are essentially measuring the same thing, and consider missing criteria."
            "Requirements Matching: Do the filters and scoring criteria align with the user's requirements and background? Do the weights reflect the user's priorities?"
            "Quantifiability: The scoring criteria should be quantifiable and objective. Avoid subjective judgments and vague criteria as much as possible."
            "The framework focuses purely on non-monetary factors. Do not consider the premium cost and payouts."
            "Action:"
            "If the framework has flaws and needs to be improved, set is_perfect to False and explain the professional reasoning behind the critique. Otherwise, set is_perfect to True."
        )

        self.reflector_prompt = ChatPromptTemplate.from_messages([
            ("system", reflector_system_prompt),
            ("human", "User Profile:\n{profile_details}\n\nSuggested Criteria and Filters:\n{criteria_json}")
        ])

        # Build Reflexion Graph
        builder = StateGraph(GeneratorState)
        builder.add_node("generate", self.node_generate)
        builder.add_node("reflect", self.node_reflect)

        builder.add_edge(START, "generate")
        builder.add_edge("generate", "reflect")
        builder.add_conditional_edges(
            "reflect",
            self.route_after_reflect,
            {"generate": "generate", "__end__": END}
        )
        self.graph = builder.compile()

    def node_generate(self, state: GeneratorState):
        chain = self.prompt | self.llm_structured
        print(f"\n[CriteriaGenerator] Generation Iteration {state.get('iterations', 0) + 1}...")
        
        feedback = state.get("feedback", "")
        feedback_text = feedback if feedback else "None"
        previous_framework = state["criteria"].model_dump_json(indent=2) if state['criteria'] is not None else "None"
        result: ScoringCriteria = chain.invoke({
            "profile_details": state["profile_details"],
            "previous_framework": previous_framework,
            "feedback": feedback_text
        })
        
        return {
            "criteria": result,
            "iterations": state.get("iterations", 0) + 1
        }

    def node_reflect(self, state: GeneratorState):
        print("\n[CriteriaGenerator] Reflecting on generated criteria...")
        chain = self.reflector_prompt | self.reflector_llm
        criteria_json = state["criteria"].model_dump_json(indent=2)
        
        try:
            reflection: CriteriaReflection = chain.invoke({
                "profile_details": state["profile_details"],
                "criteria_json": criteria_json
            })
        except Exception as e:
            # Fallback if parsing fails
            print(f"  -> Reflection failed to parse: {e}")
            reflection = CriteriaReflection(is_perfect=False, feedback="Failed to parse reflection. Please resubmit.")
        
        # Hard check for weights
        weights_sum = sum(item.weight for item in state["criteria"].criteria)
        if weights_sum != 100:
            reflection.is_perfect = False
            reflection.feedback += f" (Critical: Weights sum up to {weights_sum}, but they MUST sum to exactly 100. Please fix.)"

        if reflection.is_perfect:
            print("  -> Perfect! Criteria accepted.")
            return {"feedback": "OK"}
        else:
            print(f"  -> Needs improvement: {reflection.feedback}")
            return {"feedback": reflection.feedback}

    def route_after_reflect(self, state: GeneratorState):
        if state["feedback"] == "OK" or state.get("iterations", 0) >= 3:
            return "__end__"
        return "generate"

    def generate_criteria(self, profile: UserRequirements) -> ScoringCriteria:
        """Generates and perfects comparison points (criteria) for insurance policies based on the user's profile and goals."""
        profile_details = profile.to_text()
        
        initial_state = {
            "profile_details": profile_details,
            "criteria": None,
            "feedback": "",
            "iterations": 0
        }
        
        result_state = self.graph.invoke(initial_state)
        result = result_state["criteria"]
        
        print("\n[CriteriaGenerator]: Final Perfected Criteria:")
        for idx, crit in enumerate(result.criteria, 1):
            print(f"  {idx}. {crit.item} (Weight: {crit.weight}) - {crit.description}")
            
        print("\n[CriteriaGenerator]: Final Hard Filters:")
        if result.filters:
            for idx, filter_txt in enumerate(result.filters, 1):
                print(f"  {idx}. {filter_txt}")
        else:
            print("  None")
        print("\n")
        
        return result