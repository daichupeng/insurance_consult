"""
Helpers for checking and fetching policy PDFs from comparefirst.sg.

check_policy_exists   — returns True if a PDF with a matching stem already
                        lives anywhere under raw_policies/.
download_policy_pdf   — downloads the product-summary PDF to raw_policies/<insurer>/
                        and re-runs `graphrag index` so the new document is
                        searchable via the knowledge graph.
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_PROJECT_ROOT  = Path(__file__).parent.parent
_POLICIES_DIR  = _PROJECT_ROOT / "raw_policies"
_GRAPHRAG_ROOT = _PROJECT_ROOT / "graphrag"


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalise(name: str) -> str:
    """Lower-case and strip non-alphanumeric chars for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find_existing_pdf(policy_name: str) -> Path | None:
    """Return the path of an existing PDF whose stem fuzzy-matches policy_name."""
    target = _normalise(policy_name)
    if not _POLICIES_DIR.exists():
        return None
    for pdf in _POLICIES_DIR.rglob("*.pdf"):
        if _normalise(pdf.stem) == target:
            return pdf
    return None


# ── LangChain tools ───────────────────────────────────────────────────────────

@tool
def check_policy_exists(policy_name: str) -> bool:
    """
    Check whether a policy PDF already exists in the local raw_policies directory.

    Performs a fuzzy (case-insensitive, punctuation-insensitive) stem match
    against every PDF found recursively under raw_policies/.

    Args:
        policy_name: The policy name as returned by the crawler
                     (e.g. "AIA Guaranteed Protect Plus III").

    Returns:
        True  — a matching PDF is already present (and indexed in GraphRAG).
        False — no matching PDF found; the policy needs to be downloaded.
    """
    found = _find_existing_pdf(policy_name) is not None
    logger.info("[policy_tools] check_policy_exists(%r) → %s", policy_name, found)
    return found


@tool
def download_policy_pdf(policy_name: str, product_summary_url: str, insurer: str = "unknown") -> str:
    """
    Download a policy's Product Summary PDF and ingest it into the GraphRAG index.

    Steps:
      1. Skip download if the PDF already exists.
      2. Download the PDF from product_summary_url to raw_policies/<insurer>/.
      3. Re-run `graphrag index` so the new document becomes searchable.

    Args:
        policy_name:         Human-readable policy name used as the filename stem.
        product_summary_url: Direct URL to the PDF (from the crawler output).
        insurer:             Sub-folder name under raw_policies/ (e.g. "aia", "income").
                             Defaults to "unknown".

    Returns:
        A one-line status string describing what happened.
    """
    # 1. Check already exists
    existing = _find_existing_pdf(policy_name)
    if existing:
        return f"Already exists: {existing.relative_to(_PROJECT_ROOT)}"

    # 2. Download
    safe_name = re.sub(r"[^\w\- ]", "_", policy_name).strip()
    dest_dir  = _POLICIES_DIR / insurer
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{safe_name}.pdf"

    logger.info("[policy_tools] Downloading %s → %s", product_summary_url, dest_path)
    try:
        resp = requests.get(product_summary_url, timeout=60, stream=True)
        resp.raise_for_status()
        with dest_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
    except Exception as exc:
        logger.error("[policy_tools] Download failed: %s", exc)
        return f"Download failed: {exc}"

    logger.info("[policy_tools] Saved %s (%.1f KB)", dest_path.name, dest_path.stat().st_size / 1024)

    # Convert the new PDF to Markdown for the MD retriever
    try:
        from tools.policyCrawler.convert_to_md import convert_pdf_to_md
        convert_pdf_to_md(dest_path)
    except Exception as md_exc:
        logger.warning("[policy_tools] MD conversion failed for %s: %s", dest_path.name, md_exc)

    # 3. Re-index GraphRAG (keeps both backends in sync)
    status = _reindex_graphrag()
    return f"Downloaded {dest_path.name}. {status}"


def _reindex_graphrag() -> str:
    """Run `graphrag index --root <graphrag_root>` as a subprocess."""
    logger.info("[policy_tools] Running graphrag index …")
    env = os.environ.copy()
    if not env.get("GRAPHRAG_API_KEY"):
        env["GRAPHRAG_API_KEY"] = env.get("OPENAI_API_KEY", "")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "graphrag", "index", "--root", str(_GRAPHRAG_ROOT)],
            cwd=str(_PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min ceiling
        )
        if result.returncode == 0:
            logger.info("[policy_tools] graphrag index completed successfully.")
            return "GraphRAG index updated."
        else:
            logger.error("[policy_tools] graphrag index failed:\n%s", result.stderr[-2000:])
            return f"Indexed (with warnings): {result.stderr[-200:]}"
    except subprocess.TimeoutExpired:
        return "Indexing timed out — PDF saved but not yet indexed."
    except Exception as exc:
        return f"Indexing error: {exc}"
