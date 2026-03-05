from langchain_core.tools import tool

@tool
def confirm_requirements(question: str) -> str:
    """Chat with the user to clarify their requirements or confirm recommended requirements. Answer the user's questions if they can't make a clear decision.
    If the user is not able to provide a clear requirement or not sure how to make a decision, ask relevant questions, explain decision factors, and recommend a requirement for the user. The recommended requirements must be confirmed by the user.
    If some user inputs seem unreasonable, explain your doubts, clarify further and confirm with the user.
    """
    print(f"\n[Agent Consultant]: {question}")
    return input("[User]: ")
    
