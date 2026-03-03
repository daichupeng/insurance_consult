from docling.document_converter import DocumentConverter

class DoclingParserWrapper:
    def __init__(self):
        # Initializes the Docling models (layout analysis, table recognition)
        self.converter = DocumentConverter()

    def load_data(self, filepath: str) -> str:
        """Converts the PDF and returns the raw Markdown string."""
        conv_result = self.converter.convert(filepath)
        return conv_result.document.export_to_markdown()