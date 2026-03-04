from langchain_core.tools import tool

@tool
def ask_user_for_clarification(question: str) -> str:
    """Ask the user a specific question to clarify their life insurance needs or gather missing profile details. Wait for their response."""
    print(f"\n[Agent Consultant]: {question}")
    return input("[User]: ")
    
