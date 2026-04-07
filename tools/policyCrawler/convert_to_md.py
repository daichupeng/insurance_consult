"""
convert_to_md.py — Batch-convert all policy PDFs under raw_policies/ to Markdown.

Uses docling to preserve:
  • Table structures (TableFormer ACCURATE mode)
  • Hierarchical headings / section nesting
  • List items and inline formatting

Usage (batch, from project root):
    uv run python tools/policyCrawler/convert_to_md.py

Programmatic (single file):
    from tools.policyCrawler.convert_to_md import convert_pdf_to_md
    convert_pdf_to_md(Path("raw_policies/aia/MyPolicy.pdf"))

The .md file is written next to the source PDF with the same stem.
Already-converted files are skipped (idempotent).
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"


# ── Lazy-load docling so that importing this module is always safe ─────────────

def _get_converter():
    """Build and return a docling DocumentConverter configured for insurance PDFs."""
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat

    pipeline_opts = PdfPipelineOptions()
    pipeline_opts.do_table_structure = True          # extract tables
    pipeline_opts.do_ocr = False                     # PDFs are digital; skip OCR for speed

    try:
        # TableFormer ACCURATE gives best table fidelity
        from docling.models.tableformer_model import TableFormerMode
        pipeline_opts.table_structure_options.mode = TableFormerMode.ACCURATE
    except (ImportError, AttributeError):
        logger.debug("TableFormerMode not available; using docling defaults.")

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
        }
    )
    return converter


# ── Public API ─────────────────────────────────────────────────────────────────

def convert_pdf_to_md(pdf_path: Path, force: bool = False) -> Path | None:
    """
    Convert a single PDF to Markdown and write it next to the source file.

    Parameters
    ----------
    pdf_path : Path
        Absolute (or relative) path to the PDF file.
    force : bool
        If True, overwrite an existing .md file.  Default: False (skip if exists).

    Returns
    -------
    Path | None
        Path of the written .md file, or None if skipped / failed.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.warning("[convert_to_md] PDF not found: %s", pdf_path)
        return None

    md_path = pdf_path.with_suffix(".md")
    if md_path.exists() and not force:
        logger.info("[convert_to_md] Already converted, skipping: %s", md_path.name)
        return md_path

    logger.info("[convert_to_md] Converting: %s", pdf_path.name)
    try:
        converter = _get_converter()
        result = converter.convert(str(pdf_path))
        md_text = result.document.export_to_markdown()

        md_path.write_text(md_text, encoding="utf-8")
        logger.info(
            "[convert_to_md] ✓ Written %s (%.1f KB)",
            md_path.name, md_path.stat().st_size / 1024,
        )
        return md_path
    except Exception as exc:
        logger.error("[convert_to_md] ✗ Failed to convert %s: %s", pdf_path.name, exc)
        return None


def batch_convert(policies_dir: Path = _POLICIES_DIR, force: bool = False) -> tuple[int, int]:
    """
    Recursively convert every PDF under *policies_dir* that lacks a sibling .md.

    Returns
    -------
    (successes, failures) counts.
    """
    pdfs = sorted(policies_dir.rglob("*.pdf"))
    if not pdfs:
        logger.warning("[convert_to_md] No PDFs found under %s", policies_dir)
        return 0, 0

    logger.info("[convert_to_md] Found %d PDFs to process …", len(pdfs))
    ok = fail = 0
    for pdf in pdfs:
        result = convert_pdf_to_md(pdf, force=force)
        if result is not None:
            ok += 1
        else:
            # count as failure only if the md doesn't exist (i.e., not skipped)
            if not pdf.with_suffix(".md").exists():
                fail += 1

    logger.info("[convert_to_md] Done — %d converted, %d failed.", ok, fail)
    return ok, fail


# ── CLI entry-point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Convert all policy PDFs under raw_policies/ to Markdown."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-convert even if a .md file already exists."
    )
    parser.add_argument(
        "--dir", type=Path, default=_POLICIES_DIR,
        help=f"Root directory to scan (default: {_POLICIES_DIR})"
    )
    args = parser.parse_args()

    ok, fail = batch_convert(policies_dir=args.dir, force=args.force)
    if fail:
        print(f"[convert_to_md] WARNING: {fail} PDF(s) failed to convert.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"[convert_to_md] All done — {ok} file(s) converted (or already up-to-date).")
