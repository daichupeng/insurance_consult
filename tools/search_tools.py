from langchain_core.tools import tool
import os
from dotenv import load_dotenv
load_dotenv()
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

_llm = ChatOpenAI(model="gpt-4o", temperature=0)

@tool
def query_expansion(criterion: str, original_query: str = None, previous_response: str = None) -> str:
    """
    Generates semantic variations of a search term to improve database recall.
    e.g., "Total Permanent Disability" -> "TPD, Permanent disability, Presumed incapacity"
    """
    print(f"\n[Tool Execution]: Expanding query '{criterion}'")
    
    prompt_msg = (
        "You are an expert in life insurance policy reader. "
        "Generate 3 to 5 clear, concise variations of the query or extension of the query "
        "for the given search term to improve discovery. Return ONLY a comma-separated list of these variations."
    )
    
    if original_query or previous_response:
        prompt_msg += " Use the following context to understand what previously failed or was insufficient:\n"
        if original_query:
            prompt_msg += f"- Original Query: {original_query}\n"
        if previous_response:
            prompt_msg += f"- Previous Response: {previous_response}\n"
            
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_msg),
        ("human", "Search term: {criterion}")
    ])
    
    chain = prompt | _llm
    result = chain.invoke({"criterion": criterion})
    
    variations = result.content.strip()
    print(f"  -> Generated variations: {variations}")
    return variations

@tool
def remove_context(snippet: str) -> str:
    """
    Instructs the system to remove a specific irrelevant snippet from the collected context.
    Pass the exact snippet text or a unique substring of it to be removed.
    """
    print(f"\n[Tool Execution]: Removing context containing snippet: '{snippet[:30]}...'")
    return f"Context containing '{snippet}' has been flagged for removal."

@tool
def list_available_policies() -> str:
    """
    Retrieves a list of all available insurance policy names in the database.
    Use this to know exactly which policy names you can pass into the search tools.
    """
    print(f"\n[Tool Execution]: Listing available policies")
    
    policies_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'raw_policies', 'aia'))
    available_policies = []
    
    if os.path.exists(policies_dir):
        for filename in os.listdir(policies_dir):
            if filename.endswith(".pdf"):
                policy_name = filename[:-4] # Remove .pdf
                available_policies.append(policy_name)
                
    if not available_policies:
        return "No policies found in the database."
        
    return "Available Policies:\n" + "\n".join([f"- {name}" for name in available_policies])
