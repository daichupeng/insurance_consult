from docling.document_converter import DocumentConverter
from docling.chunking import HierarchicalChunker

class DoclingParserWrapper:
    def __init__(self):
        # Initializes the Docling models (layout analysis, table recognition)
        self.converter = DocumentConverter()
        self.chunker = HierarchicalChunker()

    def load_and_chunk(self, filepath: str):
        """Converts the PDF and returns structurally intelligent chunks (keeps tables intact)."""
        conv_result = self.converter.convert(filepath)
        chunks = self.chunker.chunk(conv_result.document)
        return list(chunks)