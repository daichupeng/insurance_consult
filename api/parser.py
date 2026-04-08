import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from api.db import get_user_policies # though not directly used for file deduplication, good to have

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"

# Lazy-load docling to avoid heavy imports on startup
def _get_docling_converter():
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        
        pipeline_opts = PdfPipelineOptions()
        pipeline_opts.do_table_structure = True
        pipeline_opts.do_ocr = False # digital PDFs are common
        
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
            }
        )
    except ImportError:
        logger.error("Docling not installed properly.")
        return None

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract markdown text from a PDF using docling."""
    converter = _get_docling_converter()
    if not converter:
        return ""
    
    try:
        result = converter.convert(str(pdf_path))
        return result.document.export_to_markdown()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return ""

def parse_policy_with_llm(md_text: str) -> Dict[str, Any]:
    """Use GPT-4o-mini to extract structured policy details from markdown text."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert insurance document parser. 
Extract the following information from the provided policy document text and return it as a JSON object.
Fields to extract:
- insurer: The company name (e.g., AIA, Prudential, Singlife).
- insurance_name: Full name of the policy.
- starting_year: Current year (2026) as placeholder, unless specifically mentioned as 'inception' or 'starting date' in the text.
- payment_years: The number of years the user pays premiums (e.g., 20, 10, or 'Whole Life'). If numerical, return integer.
- coverage_years: The number of years the policy covers (e.g., up to age 99, 30 years). If numerical, return integer.
- annual_premium: The yearly cost in SGD. Return as float if possible. Use '0' if not found.
- coverage_amount: The sum assured or total benefit amount in SGD. Return as float if possible. Use '0' if not found.

Return ONLY the JSON object. Do not include markdown code blocks."""),
        ("user", "{text}")
    ])
    
    chain = prompt | llm
    try:
        response = chain.invoke({"text": md_text[:12000]}) # Limit text for token efficiency
        content = response.content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"LLM parsing failed: {e}")
        return {}

def save_policy_files(temp_pdf_path: Path, insurer: str, policy_name: str, md_text: str) -> Optional[str]:
    """
    Saves the PDF and its MD version to the correct folder under raw_policies.
    Returns the relative path to the saved PDF or None if duplicate.
    """
    # Normalise insurer for folder, but use human-readable name for file
    safe_insurer = re.sub(r"[^\w\- ]", "_", insurer).strip().lower()
    safe_filename = re.sub(r"[^\w\- ().] ", "_", policy_name).strip()
    
    target_dir = _POLICIES_DIR / safe_insurer
    pdf_filename = f"{safe_filename}.pdf"
    md_filename = f"{safe_filename}.md"
    
    target_pdf_path = target_dir / pdf_filename
    target_md_path = target_dir / md_filename
    
    # Check for duplicates (at least by path/name)
    if target_pdf_path.exists():
        logger.info(f"Policy already exists at {target_pdf_path}. Skipping save.")
        return str(target_pdf_path.relative_to(_PROJECT_ROOT))
    
    # Create directory and save
    target_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Move the uploaded PDF
        import shutil
        shutil.copy2(temp_pdf_path, target_pdf_path)
        
        # Save the MD text
        target_md_path.write_text(md_text, encoding="utf-8")
        
        logger.info(f"Saved policy files to {target_dir}")
        return str(target_pdf_path.relative_to(_PROJECT_ROOT))
    except Exception as e:
        logger.error(f"Failed to save policy files: {e}")
        return None
