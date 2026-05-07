import os
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

from agents.claim_agent.advisor import advisor_node
from graphs.claim_agent.state import Diagnosis

state = {
    "diagnosis": Diagnosis(diagnosis="Broken Arm", diagnosis_reason="Fell", priority=1),
    "symptoms": ["pain"],
    "tests_done": ["xray"],
    "procedures_conducted": [],
    "incurred_cost_items": []
}

try:
    print("Running advisor...")
    res = advisor_node(state, llm)
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
