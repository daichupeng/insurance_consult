from typing import List, Dict, Any
from qdrant_client.http import models

class PolicyRetriever:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def retrieve(self, query: str, metadata_filters: Dict[str, Any] = None, top_k: int = 5) -> List[str]:
        """Executes similarity search with optional metadata pre-filtering."""
        qdrant_filter = None
        
        # Translate standard Python dict to Qdrant's exact match payload filters
        if metadata_filters:
            conditions = [
                models.FieldCondition(
                    # LangChain nests all injected metadata under the 'metadata' key in Qdrant payloads
                    key=f"metadata.{key}", 
                    match=models.MatchValue(value=value)
                ) for key, value in metadata_filters.items()
            ]
            qdrant_filter = models.Filter(must=conditions)

        # Execute HNSW approximate nearest neighbor search
        docs = self.vector_store.similarity_search(
            query=query,
            k=top_k,
            filter=qdrant_filter
        )
        
        # Return pure string context for the LLM
        return [doc.page_content for doc in docs]