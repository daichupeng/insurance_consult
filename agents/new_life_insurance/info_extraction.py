import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from schema.models import Policy
from tools.new_life_insurance.calculator import key_info_extractor

logger = logging.getLogger(__name__)

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"

# Mirror md_retriever's character cap so the prompt stays inside the model's window.
_MAX_MD_CHARS = 120_000


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find_policy_md(policy_name: str) -> Optional[Path]:
    """Locate the .md file under raw_policies/ matching *policy_name* (fuzzy stem)."""
    if not _POLICIES_DIR.exists() or not policy_name:
        return None
    target = _normalise(policy_name)
    for md in _POLICIES_DIR.rglob("*.md"):
        if _normalise(md.stem) == target:
            return md
    return None


def _resolve_policy_doc(policy: Policy) -> str:
    """Use the policy's bundled document if present, otherwise read it from disk."""
    if policy.policy_document and policy.policy_document.strip():
        return policy.policy_document[:_MAX_MD_CHARS]

    md_path = _find_policy_md(policy.policy_name)
    if md_path is None:
        return ""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        return text[:_MAX_MD_CHARS]
    except Exception as e:
        logger.warning("[InfoExtractor] could not read %s: %s", md_path, e)
        return ""


class InfoExtractor:
    """
    Extracts a structured `key_info` snapshot of each policy's economic terms
    (benefits, surrender values, bonuses, etc.) from its full markdown document.
    Resolves the document either from the Policy object or directly from
    raw_policies/ (since the MD retriever omits the full text from Policy
    for payload reasons). Runs per-policy LLM calls concurrently.
    """

    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers

    def extract(self, policies: List[Policy]) -> List[Policy]:
        if not policies:
            return policies

        def _extract(policy: Policy):
            doc = _resolve_policy_doc(policy)
            if not doc:
                logger.warning("[InfoExtractor] no document found for %s", policy.policy_name)
                policy.key_info = None
                return
            try:
                info = key_info_extractor(doc, llm)
                policy.key_info = info.model_dump()
            except Exception as e:
                logger.warning("[InfoExtractor] extraction failed for %s: %s", policy.policy_name, e)
                policy.key_info = None

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(policies))) as pool:
            list(pool.map(_extract, policies))

        return policies
