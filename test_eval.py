import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents.orchestrator import Orchestrator
import time

print("Initializing Orchestrator...")
t0 = time.time()
orc = Orchestrator()
print(f"Initialized in {time.time()-t0:.2f}s")

user_message = "Wait, what is a deductible?"
print(f"Evaluating for: {user_message}")
t0 = time.time()
res = orc.evaluate_input(user_message, "new_life_insurance", "profile")
print(f"Finished in {time.time()-t0:.2f}s: {res}")
