import os
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

from agents.claim_agent.incident_analyzer import incident_analysis
from langchain_core.messages import HumanMessage

state = {
    "messages": [HumanMessage(content="I broke my arm and went to the hospital.")],
    "symptoms": [],
    "tests_done": [],
    "procedures_conducted": [],
    "primary_diagnosis": None,
    "incurred_cost_items": [],
    "missing_info": [],
    "clarification_question": "",
    "review_passed": False,
    "review_count": 0,
    "next_action": ""
}

try:
    print("Running...")
    res = incident_analysis(state, llm)
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
