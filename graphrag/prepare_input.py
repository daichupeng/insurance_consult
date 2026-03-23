"""
Convert all policy PDFs under raw_policies/ to plain text for GraphRAG indexing.

GraphRAG cannot parse raw PDF bytes — it expects pre-converted plain text.
This script uses Docling (already in the project) to convert each PDF to
markdown-formatted text and writes the result to graphrag/input/ as a .txt
file.  Markdown is preserved so that benefit tables and structured clauses
are captured as readable text rather than flattened or lost.

Usage (from project root):
    python graphrag/prepare_input.py

Options:
    --clear-output    Delete graphrag/output/ before writing new input files
                      so the next `python graphrag/run_index.py` starts fresh.
                      The LLM cache (graphrag/cache/) is NOT deleted so cached
                      API responses can be reused.
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT  = Path(__file__).parent.parent
POLICIES_DIR  = PROJECT_ROOT / "raw_policies"   # all subfolders scanned recursively
INPUT_DIR     = Path(__file__).parent / "input"
OUTPUT_DIR    = Path(__file__).parent / "output"


def convert_pdfs() -> int:
    """Convert all PDFs to .txt. Returns number of files written."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        logger.error("docling is not installed. Run: uv sync")
        sys.exit(1)

    converter = DocumentConverter()
    INPUT_DIR.mkdir(exist_ok=True)

    pdfs = sorted(POLICIES_DIR.rglob("*.pdf"))
    if not pdfs:
        logger.error("No PDFs found under %s", POLICIES_DIR)
        sys.exit(1)

    logger.info(
        "Converting %d PDF(s) from %s (all subfolders) → %s\n",
        len(pdfs), POLICIES_DIR, INPUT_DIR,
    )

    written = 0
    for pdf_path in pdfs:
        out_path = INPUT_DIR / (pdf_path.stem + ".txt")

        if out_path.exists():
            logger.info("  [skip]       %s  (already converted)", pdf_path.name)
            continue

        logger.info("  [converting] %s …", pdf_path.name)
        try:
            result  = converter.convert(str(pdf_path))
            text    = result.document.export_to_markdown()
            out_path.write_text(text, encoding="utf-8")
            logger.info(
                "  [done]       → %s  (%d chars, ~%d tokens)",
                out_path.name,
                len(text),
                len(text) // 4,  # rough token estimate
            )
            written += 1
        except Exception as exc:
            logger.error("  [error]      %s: %s", pdf_path.name, exc)

    return written


def clear_output() -> None:
    """Remove stale GraphRAG output (not cache) so the next index is fresh."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
        logger.info("Cleared stale output at %s", OUTPUT_DIR)
    else:
        logger.info("Output directory does not exist — nothing to clear.")


def main():
    parser = argparse.ArgumentParser(description="Prepare GraphRAG input from policy PDFs")
    parser.add_argument(
        "--clear-output",
        action="store_true",
        help="Delete graphrag/output/ so the next run_index.py starts fresh",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-convert even if .txt files already exist",
    )
    args = parser.parse_args()

    if args.force:
        for f in INPUT_DIR.glob("*.txt"):
            if f.name != "sample.txt":
                f.unlink()
        logger.info("Removed existing .txt files (--force)\n")

    written = convert_pdfs()

    if args.clear_output:
        clear_output()

    if written > 0:
        logger.info(
            "\n✓ %d file(s) written to %s", written, INPUT_DIR
        )
    else:
        logger.info("\n✓ All files already present in %s", INPUT_DIR)

    logger.info(
        "\nNext step: rebuild the GraphRAG index\n"
        "    python graphrag/run_index.py\n"
        "\nIf you want a completely fresh index (recommended after changing\n"
        "settings or entity types):\n"
        "    python graphrag/prepare_input.py --clear-output\n"
        "    python graphrag/run_index.py"
    )


if __name__ == "__main__":
    main()
