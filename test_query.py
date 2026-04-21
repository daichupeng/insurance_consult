import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents.query_agent import QueryAgent
import time

print("Initializing QueryAgent...")
t0 = time.time()
agent = QueryAgent()
print(f"Initialized in {time.time()-t0:.2f}s")

user_message = "Wait, what is a deductible?"
print(f"Invoking for: {user_message}")
t0 = time.time()
response = agent.agent_executor.invoke({"messages": [("user", user_message)]})
print(f"Finished in {time.time()-t0:.2f}s")
print(response["messages"][-1].content)
