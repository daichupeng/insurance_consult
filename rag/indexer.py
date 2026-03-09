import os
from typing import List, Dict
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from mlx_embedder import MLXQwenEmbeddings


class PolicyIndexer:
    def __init__(self, vector_store, parser):
        self.vector_store = vector_store
        self.parser = parser # e.g., LlamaParse setup for Markdown output

    def process_pdfs(self, pdf_directory: str):
        """Main pipeline: Parse -> Chunk -> Embed -> Store"""
        print(f"Processing PDFs in {pdf_directory}")
        print(f"Listing files: {os.listdir(pdf_directory)}")
        for filename in os.listdir(pdf_directory):
            if filename.endswith(".pdf"):
                print(f"Processing file: {filename}")
                filepath = os.path.join(pdf_directory, filename)
                
                # 1. Parse PDF to Markdown
                raw_markdown = self.parser.load_data(filepath)
                
                # 2. Extract Document-level Metadata
                metadata = self._extract_base_metadata(filename)
                
                # 3. Chunking by Markdown Headers
                chunks = self._chunk_document(raw_markdown, metadata)
                print(f"Chunked {filename} into {len(chunks)} chunks.")
                
                # 4. Ingest to Vector DB
                self.vector_store.add_documents(chunks)
                print(f"Indexed {filename} with {len(chunks)} chunks.")

    def _extract_base_metadata(self, filename: str) -> Dict:
        """Derive metadata from filename."""
        parts = filename.replace(".pdf", "").split("_")
        return {
            "company": parts[0],
            "policy_name": " ".join(parts[1:]),
        }

    def _chunk_document(self, markdown_text: str, base_metadata: dict):
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        
        # 1. Initial split by headers
        header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        sections = header_splitter.split_text(markdown_text)
        
        # 2. Refine splits while keeping header context
        # This prevents the 'VectorStruct' error by ensuring text is never empty
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        
        final_chunks = []
        for section in sections:
            # Construct a breadcrumb (e.g., "Policy A > Section 2 > 2.1")
            # Prepend it to the content so the vector 'remembers' the context
            header_context = " > ".join([v for k, v in section.metadata.items() if "Header" in k])
            
            sub_chunks = text_splitter.split_text(section.page_content)
            for sub_text in sub_chunks:
                if not sub_text.strip(): continue # Skip empty strings to prevent Qdrant errors
                
                # Enrich the text with its structural context
                enriched_content = f"Context: {header_context}\n\n{sub_text}"
                
                section.page_content = enriched_content
                section.metadata.update(base_metadata)
                final_chunks.append(section)
                
        return final_chunks


