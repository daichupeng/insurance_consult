"""
RAG.py — Hierarchy-aware markdown chunker, embedder, and Qdrant-backed
retrieval tool for insurance policy `.md` files under `raw_policies/`.

Chunking
--------
- Splits by `##`-style heading sections; each chunk carries its heading path.
- Atomic blocks: paragraphs, tables, and lists are never split mid-block.
- Consecutive blocks under the same heading are packed up to `MAX_TOKENS`.
- A block that exceeds `MAX_TOKENS` on its own becomes a single oversize chunk
  (paragraph/table integrity wins over the size cap).

Index
-----
- Embeddings: OpenAI `text-embedding-3-large` (3072 dims).
- Store: Qdrant in local file mode at `databases/md_rag_qdrant/`.
- Collection: `policy_md_chunks`. Full rebuild on every `index_all()`.
- Note: Qdrant local file mode is single-process. Don't run `index_all()` while
  another process holds the client open (e.g. the API server using `rag_search`).

Agent tool
----------
- `rag_search(query, policy_name="", top_k=5)` — LangChain `@tool`.

CLI
---
    python -m tools.RAG        # full rebuild of the index
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

try:
    import tiktoken
    _ENCODER = tiktoken.get_encoding("o200k_base")
    def _count_tokens(text: str) -> int:
        return len(_ENCODER.encode(text))
except Exception:
    def _count_tokens(text: str) -> int:
        return max(1, len(text) // 4)

logger = logging.getLogger(__name__)
load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"
_QDRANT_PATH  = _PROJECT_ROOT / "databases" / "md_rag_qdrant"
_COLLECTION   = "policy_md_chunks"

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM   = 3072
MAX_TOKENS  = 800
EMBED_BATCH = 64

_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class MDBlock:
    kind: str       # "heading" | "paragraph" | "table" | "list"
    text: str
    level: int = 0  # heading depth (0 for non-heading)


@dataclass
class MDChunk:
    text: str
    heading_path: str
    policy_name: str
    file_path: str
    chunk_index: int
    preceding_context: str = ""   # text of the previous chunk in the same heading path ("" if first)
    following_context: str = ""   # text of the next chunk in the same heading path ("" if last)


# ── Parsing ──────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_IMAGE_MARKER_RE = re.compile(r"^<!--\s*image\s*-->$", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^(\s*[-*+]\s+|\s*\d+\.\s+)")


def _parse_md(text: str) -> list[MDBlock]:
    """Parse markdown into an ordered stream of headings, paragraphs, tables, and lists."""
    lines = text.replace("\r\n", "\n").split("\n")
    lines = [ln for ln in lines if not _IMAGE_MARKER_RE.match(ln.strip())]

    blocks: list[MDBlock] = []
    buf: list[str] = []
    buf_kind: str | None = None

    def flush():
        nonlocal buf, buf_kind
        if buf and buf_kind:
            joined = "\n".join(buf).strip()
            if joined:
                blocks.append(MDBlock(kind=buf_kind, text=joined))
        buf = []
        buf_kind = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        m = _HEADING_RE.match(stripped)
        if m:
            flush()
            blocks.append(MDBlock(kind="heading", text=m.group(2).strip(), level=len(m.group(1))))
            continue

        if not stripped:
            flush()
            continue

        if stripped.startswith("|"):
            if buf_kind == "table":
                buf.append(line)
            else:
                flush()
                buf_kind = "table"
                buf = [line]
            continue

        if _LIST_ITEM_RE.match(line):
            if buf_kind == "list":
                buf.append(line)
            else:
                flush()
                buf_kind = "list"
                buf = [line]
            continue

        # Plain text → paragraph (or continuation of one)
        if buf_kind == "paragraph" or buf_kind is None:
            buf_kind = "paragraph"
            buf.append(line)
        else:
            flush()
            buf_kind = "paragraph"
            buf = [line]

    flush()
    return blocks


# ── Chunking ─────────────────────────────────────────────────────────────────

def _heading_path_str(stack: list[tuple[int, str]]) -> str:
    return " > ".join(h for _, h in stack)


def chunk_blocks(blocks: list[MDBlock], max_tokens: int = MAX_TOKENS) -> list[tuple[str, str]]:
    """
    Pack blocks into chunks of up to `max_tokens`, preserving paragraph/table/list
    atomicity. Headings update the current heading path but never appear inside
    a chunk body.

    Returns: list of (heading_path, chunk_text) pairs.
    """
    chunks: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []
    cur_blocks: list[str] = []
    cur_tokens = 0
    cur_heading_path = ""

    def flush_chunk():
        nonlocal cur_blocks, cur_tokens
        if cur_blocks:
            chunks.append((cur_heading_path, "\n\n".join(cur_blocks).strip()))
        cur_blocks = []
        cur_tokens = 0

    for blk in blocks:
        if blk.kind == "heading":
            flush_chunk()
            while heading_stack and heading_stack[-1][0] >= blk.level:
                heading_stack.pop()
            heading_stack.append((blk.level, blk.text))
            cur_heading_path = _heading_path_str(heading_stack)
            continue

        blk_tokens = _count_tokens(blk.text)

        if blk_tokens > max_tokens:
            # Atomic block bigger than budget — flush and emit as-is.
            flush_chunk()
            chunks.append((cur_heading_path, blk.text))
            continue

        if cur_blocks and cur_tokens + blk_tokens > max_tokens:
            flush_chunk()

        cur_blocks.append(blk.text)
        cur_tokens += blk_tokens

    flush_chunk()
    return chunks


def chunk_md_file(path: Path) -> list[MDChunk]:
    """Parse and chunk one `.md` file. Returns chunks with metadata.

    Each chunk also carries its `preceding_context` / `following_context`: the
    text of the neighbouring chunk under the SAME heading path. These are empty
    at the first / last chunk of a heading path (i.e. neighbours under a
    different heading path are not borrowed).
    """
    text = path.read_text(encoding="utf-8")
    blocks = _parse_md(text)
    raw_chunks = chunk_blocks(blocks)

    policy_name = path.stem
    chunks = [
        MDChunk(
            text=chunk_text,
            heading_path=hpath,
            policy_name=policy_name,
            file_path=str(path),
            chunk_index=i,
        )
        for i, (hpath, chunk_text) in enumerate(raw_chunks)
    ]

    # Link preceding / following context within each heading path. A neighbour
    # only counts if it shares the same heading_path as the current chunk.
    for i, c in enumerate(chunks):
        if i > 0 and chunks[i - 1].heading_path == c.heading_path:
            c.preceding_context = chunks[i - 1].text
        if i + 1 < len(chunks) and chunks[i + 1].heading_path == c.heading_path:
            c.following_context = chunks[i + 1].text

    return chunks


# ── Embedding ────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed with OpenAI text-embedding-3-large."""
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = _openai.embeddings.create(model=EMBED_MODEL, input=batch)
        out.extend(d.embedding for d in resp.data)
    return out


# ── Qdrant store ─────────────────────────────────────────────────────────────

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _QDRANT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=str(_QDRANT_PATH))
    return _client


def _recreate_collection() -> None:
    client = _get_client()
    if client.collection_exists(_COLLECTION):
        client.delete_collection(_COLLECTION)
    client.create_collection(
        collection_name=_COLLECTION,
        vectors_config=qmodels.VectorParams(size=EMBED_DIM, distance=qmodels.Distance.COSINE),
    )


def index_all(policies_dir: Path = _POLICIES_DIR) -> dict:
    """
    Full rebuild. Walks every `.md` under `policies_dir`, chunks + embeds them,
    and upserts into the Qdrant collection (dropped and re-created first).
    """
    md_files = sorted(policies_dir.rglob("*.md"))
    logger.info("Found %d .md files under %s", len(md_files), policies_dir)

    all_chunks: list[MDChunk] = []
    for f in md_files:
        all_chunks.extend(chunk_md_file(f))
    logger.info("Produced %d chunks", len(all_chunks))

    if not all_chunks:
        return {"files": 0, "chunks": 0}

    _recreate_collection()
    client = _get_client()

    BATCH = 128
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i : i + BATCH]
        # Prepend heading path so embeddings carry section context.
        texts_for_embed = [
            f"{c.heading_path}\n\n{c.text}" if c.heading_path else c.text
            for c in batch
        ]
        vectors = embed_texts(texts_for_embed)
        points = [
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "text": c.text,
                    "heading_path": c.heading_path,
                    "policy_name": c.policy_name,
                    "file_path": c.file_path,
                    "chunk_index": c.chunk_index,
                    "preceding_context": c.preceding_context,
                    "following_context": c.following_context,
                },
            )
            for c, vec in zip(batch, vectors)
        ]
        client.upsert(collection_name=_COLLECTION, points=points)
        logger.info("Upserted %d/%d", min(i + BATCH, len(all_chunks)), len(all_chunks))

    return {"files": len(md_files), "chunks": len(all_chunks)}


# ── Agent tool ───────────────────────────────────────────────────────────────


def rag_search(query: str, policy_name: str = "", top_k: int = 5) -> str:
    """
    Semantic search over chunked insurance-policy markdown documents.

    Args:
        query: Question or topic to search for.
        policy_name: Optional EXACT policy name (matches the `.md` file stem) to
            scope the search to one document. Leave empty to search across all policies.
        top_k: Number of top-matching chunks to return (default 5).

    Returns: a formatted string listing matching chunks. Each result carries its
    source policy and heading path plus the chunk's preceding/following context
    (the neighbouring chunks under the same heading path, "(none)" at a path
    boundary). If the index has not been built yet, instructs the caller to run
    the indexer.
    """
    client = _get_client()
    if not client.collection_exists(_COLLECTION):
        return (
            "[RAG index not built] Run `python -m tools.RAG` or call "
            "`tools.RAG.index_all()` to build the index first."
        )

    [q_vec] = embed_texts([query])

    flt = None
    if policy_name:
        flt = qmodels.Filter(
            must=[qmodels.FieldCondition(key="policy_name", match=qmodels.MatchValue(value=policy_name))]
        )

    hits = client.query_points(
        collection_name=_COLLECTION,
        query=q_vec,
        limit=top_k,
        query_filter=flt,
    ).points

    if not hits:
        return "No matching chunks found."

    parts = []
    for i, h in enumerate(hits, 1):
        p = h.payload or {}
        preceding = p.get("preceding_context") or ""
        following = p.get("following_context") or ""
        block = (
            f"--- Result {i} (score={h.score:.3f}) ---\n"
            f"Policy: {p.get('policy_name')}\n"
            f"Section: {p.get('heading_path') or '(no heading)'}\n\n"
            f"Preceding context: {preceding or '(none)'}\n\n"
            f"Text: {p.get('text', '')}\n\n"
            f"Following context: {following or '(none)'}"
        )
        parts.append(block)
    return "\n\n".join(parts)


# ── CLI entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = index_all()
    print(f"Indexed {stats['chunks']} chunks from {stats['files']} files into '{_COLLECTION}'.")
