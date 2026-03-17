from langchain_core.tools import tool
from typing import Dict, Any, List
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, MatchValue, Filter

import sys
import os

# Ensure rag/ modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'rag')))
from mlx_embedder import MLXQwenEmbeddings

from dotenv import load_dotenv
load_dotenv()
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

_llm = ChatOpenAI(model="gpt-4o", temperature=0)

# Initialize Qdrant Client globally for tools
_client = QdrantClient(url="http://localhost:6333")
_collection_name = "life_insurance_policies"
_qwen_embeddings = MLXQwenEmbeddings(model_id="mlx-community/all-MiniLM-L6-v2-4bit")

vector_store = QdrantVectorStore(
    client=_client,
    collection_name=_collection_name,
    embedding=_qwen_embeddings
)


@tool
def search_policy_docs(query: str, policy_name: str = None) -> str:
    """
    Performs a vector search in Qdrant database of life insurance documents.
    Use this to pull specific clauses, numbers, or definitions for policy comparison.
    
    Args:
        query: The semantic search query (e.g., "What is the premium for a 30 year old male?")
        policy_name: (Optional) The specific policy name to filter by. (e.g., 'AIA Guaranteed Protect Plus (III)')
    """
    print(f"\n[Tool Execution]: Searching for '{query}'" + (f" in '{policy_name}'" if policy_name else ""))
    

    docs = vector_store.similarity_search(
        query=query,
        k=5,
    )
    
    if not docs:
        return "No relevant information found."
        
    formatted_results = "\n\n---\n\n".join([f"Source: {doc.metadata.get('source', 'Unknown')}\n\n{doc.page_content}" for doc in docs])
    return formatted_results

@tool
def get_policy_summary(policy_name: str) -> str:
    """
    Retrieves a high-level summary and basic metadata for a specific insurance policy.
    Use this to quickly understand what type of policy it is before doing deep semantic searches.
    """
    print(f"\n[Tool Execution]: Fetching summary for '{policy_name}'")
    
    # We can do a broad search for the policy name to get general context
    docs = vector_store.similarity_search(
        query="Policy overview summary and benefits",
        k=3,
        filter=Filter(must=[
            FieldCondition(
                key="metadata.source", 
                match=MatchValue(value=f"../raw_policies/aia/{policy_name}.pdf") 
            )
        ])
    )
    
    if not docs:
         return f"Could not find summary for {policy_name}."
         
    return "\n\n".join([doc.page_content for doc in docs])

@tool
def query_expansion(criterion: str) -> str:
    """
    Generates semantic variations of a search term to improve vector database recall.
    e.g., "Total Permanent Disability" -> "TPD, Permanent disability, Presumed incapacity"
    """
    print(f"\n[Tool Execution]: Expanding query '{criterion}'")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert in life insurance terminology. Generate 3 to 5 clear, concise semantic variations, synonyms, or related terms for the given search term to improve vector database recall. Return ONLY a comma-separated list of these variations."),
        ("human", "Search term: {criterion}")
    ])
    
    chain = prompt | _llm
    result = chain.invoke({"criterion": criterion})
    
    # Return the generated comma-separated variations
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
