import os
from typing import List, Dict
from langchain_core.documents import Document
from mlx_embedder import MLXQwenEmbeddings


class PolicyIndexer:
    def __init__(self, vector_store, parser):
        self.vector_store = vector_store
        self.parser = parser # e.g., DoclingParserWrapper

    def process_pdfs(self, pdf_directory: str):
        """Main pipeline: Parse -> Hierarchical Chunk (Tables intact) -> Embed -> Store"""
        print(f"Processing PDFs in {pdf_directory}")
        print(f"Listing files: {os.listdir(pdf_directory)}")
        for filename in os.listdir(pdf_directory):
            if filename.endswith(".pdf"):
                print(f"Processing file: {filename}")
                filepath = os.path.join(pdf_directory, filename)
                
                # 1. Parse PDF and Chunk hierarchically (preserves tables)
                docling_chunks = self.parser.load_and_chunk(filepath)
                
                # 2. Extract Document-level Metadata
                base_metadata = self._extract_base_metadata(filename)
                
                # 3. Convert to LangChain Documents
                lc_docs = []
                for chunk in docling_chunks:
                    # chunk.text contains the content (Markdown table, text block, etc.)
                    # chunk.meta contains Docling structural metadata
                    
                    if not chunk.text.strip():
                        continue
                        
                    metadata = base_metadata.copy()
                    
                    # Add structural hierarchy if available
                    if hasattr(chunk.meta, 'headings') and chunk.meta.headings:
                        headings_str = " > ".join(chunk.meta.headings)
                        metadata['headings'] = headings_str
                        enriched_text = f"Context: {headings_str}\n\n{chunk.text}"
                    else:
                        enriched_text = chunk.text
                        
                    lc_docs.append(Document(page_content=enriched_text, metadata=metadata))
                    
                print(f"Parsed {filename} into {len(lc_docs)} structural chunks.")
                
                # 4. Ingest to Vector DB
                self.vector_store.add_documents(lc_docs)
                print(f"Indexed {filename} with {len(lc_docs)} chunks.")

    def _extract_base_metadata(self, filename: str) -> Dict:
        """Derive metadata from filename."""
        parts = filename.replace(".pdf", "").split("_")
        return {
            "source": f"../raw_policies/aia/{filename}",
            "company": parts[0],
            "policy_name": filename[:-4],
        }


