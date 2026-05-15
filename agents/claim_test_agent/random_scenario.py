from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from typing import List

class RandomScenario(BaseModel):
    patient_age: str = Field(description="Randomly generated patient age.")
    ground_truth: str = Field(description="A random medical condition or incident.")
    stage: str = Field(description="The stage of the incident, e.g. 'Pre-consultation', 'Finished consultation with GP and received a referral to a ophthalmologist.', 'X-ray results received','Post-surgery', 'Finished consultation with a nephrologist at private hospital', etc.")
    costs: str = Field(description="List of incurred costs so far, e.g. 'None', '$200 for private GP visit', '$5000 for public hospital stay', '$250 for endocrinologist consultation at private hospital', '$40 for panadol medication prescribed by GP', etc.")

def generate_random_scenario(llm):
    prompt = """
    You are a scenario generator for testing an insurance claim AI.
    Your task is to generate a realistic random patient scenario for a claim test.
    
    The scenario should include:
    1. Patient age.
    2. A ground truth medical condition or incident. You can be creative.
    3. The current stage of the process.
    4. List of costs incurred up to the current stage. It should align with the condition and the stage the patient is at. List all reasonably incurred costs up to the current stage. Be specific about the cost item, including the exact procedures, treatments, prescriptions, and the facilities at which it was incurred.
    
    Make the scenarios varied: some simple, some complex, some involving accidents, some involving illnesses.
    """
    
    structured_llm = llm.with_structured_output(RandomScenario, method="function_calling")
    resp = structured_llm.invoke([SystemMessage(content=prompt)])
    return resp