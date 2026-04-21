import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_POLICIES_UPLOADED_DIR = _PROJECT_ROOT / "raw_policies" / "uploaded"
_POLICIES_CRAWLED_DIR = _PROJECT_ROOT / "raw_policies" / "crawled"


def _normalise(name: str) -> str:
    """Lower-case and strip non-alphanumeric chars for fuzzy file matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_md_file(policy_name: str) -> Path | None:
    """Locate the .md file for policy_name under raw_policies directories."""
    target = _normalise(policy_name)
    dirs = [_POLICIES_UPLOADED_DIR, _POLICIES_CRAWLED_DIR]
    for d in dirs:
        if d.exists():
            for md in d.rglob("*.md"):
                if _normalise(md.stem) == target:
                    return md
    return None


def extract_text(md_path: Path) -> str:
    """Extract text from markdown, capping at 120,000 characters."""
    try:
        text = md_path.read_text(encoding="utf-8")
        if len(text) > 120_000:
            return text[:120_000]
        return text
    except Exception as e:
        logger.error(f"Failed to read {md_path}: {e}")
        return ""
