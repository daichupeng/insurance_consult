from typing import List
from langchain_core.embeddings import Embeddings
import mlx.core as mx
from mlx_embeddings.utils import load

class MLXQwenEmbeddings(Embeddings):
    def __init__(self, model_id: str = "Qwen/Qwen3-Embedding-8B"):
        """Loads the model and tokenizer into unified memory."""
        self.model, self.tokenizer = load(model_id)
        
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Used by the indexer to embed chunks in batches."""
        # Tokenize the batch
        inputs = self.tokenizer.batch_encode_plus(
            texts, 
            return_tensors="mlx", 
            padding=True, 
            truncation=True, 
            max_length=4096  # Qwen handles larger contexts; adjust based on your chunk size
        )
        
        # Execute the forward pass on the M4 GPU
        outputs = self.model(
            inputs["input_ids"], 
            attention_mask=inputs["attention_mask"]
        )
        
        # outputs.text_embeds returns the mean-pooled and normalized embeddings
        embeddings = outputs.text_embeds
        
        # Convert the MLX array to a standard Python list of floats for Qdrant
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """Used by the evaluator node to embed the single user query."""
        return self.embed_documents([text])[0]