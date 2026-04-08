import hashlib
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

logger = logging.getLogger(__name__)
load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent
_DB_PATH = _PROJECT_ROOT / "tools" / "cache.db"
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"

class CacheManager:
    """
    High-efficiency caching tool for context retriever using a multi-layer approach.
    Layer A: Answer Cache (indexed by canonical key)
    Layer B: Fragment Cache (re-usable markdown snippets)
    Semantic Fallback: Cosine similarity fallback for historically matching queries.
    """

    def __init__(self, db_path: str = str(_DB_PATH)):
        self.db_path = db_path
        self._init_llm()
        self._lock = threading.Lock()

    def _init_llm(self):
        # Use gpt-4o-mini for canonical intent extraction (cheap & fast)
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        # Use text-embedding-3-small for semantic matching
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    # ── Canonical Intent Extractor ──────────────────────────────────────────

    def extract_canonical_key(self, query: str) -> Dict[str, str]:
        """
        Normalizes a raw user query into a structured Cache Key.
        Ensures consistent naming (e.g., Roman numerals to Arabic 1, 2, 3).
        """
        prompt = (
            "You are a helpful assistant that extracts intent from insurance policy queries.\n"
            "Normalize the user's query into a structured JSON object with these keys:\n"
            "- policy_id: The identifier/name of the policy. Normalize all numbers including Roman numerals to Arabic (e.g., III -> 3, IV -> 4). Use lowercase and underscores.\n"
            "- topic: The core topic of the query (e.g., 'death_benefit', 'waiting_period', 'exclusion'). Normalize to lowercase and underscores.\n"
            "- version: The version of the policy if mentioned, otherwise 'default'.\n\n"
            "QUERY: {query}\n\n"
            "Return ONLY the JSON object."
        )
        
        try:
            response = self.llm.invoke([
                SystemMessage(content="You extract structured intent from insurance queries. You always normalize policy names consistently (III -> 3, etc)."),
                HumanMessage(content=prompt.format(query=query))
            ])
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            data = json.loads(content)
            # Second pass normalization on the keys themselves just in case 
            return {k: str(v).lower().replace(" ", "_") for k, v in data.items()}
        except Exception as e:
            logger.error(f"Error in extract_canonical_key: {e}")
            return {"policy_id": "unknown", "topic": "unknown", "version": "default"}

    # ── Semantic Fallback ─────────────────────────────────────────────────────

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(a * a for a in vec2) ** 0.5
        if not magnitude1 or not magnitude2:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def find_semantic_match(self, query: str, threshold: float = 0.96) -> Optional[int]:
        """
        Searches for a historical query with high semantic similarity across ALL policies.
        Returns the canonical_id if found.
        """
        query_vec = self.embeddings.embed_query(query)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Search ALL historical queries for maximum fallback capability
            cursor.execute("SELECT id, embedding FROM canonical_queries")
            rows = cursor.fetchall()
            
            best_match_id = None
            best_score = 0.0
            
            for row_id, emb_blob in rows:
                emb_vec = json.loads(emb_blob.decode('utf-8'))
                score = self._cosine_similarity(query_vec, emb_vec)
                if score > threshold and score > best_score:
                    best_score = score
                    best_match_id = row_id
                    
            return best_match_id

    # ── Cache Layer Management ────────────────────────────────────────────────

    def get_answer(self, query: str) -> Optional[str]:
        """Layer A Check: Answer Cache lookup."""
        key = self.extract_canonical_key(query)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT answer FROM answer_cache ac "
                "JOIN canonical_queries cq ON ac.canonical_id = cq.id "
                "WHERE cq.policy_id = ? AND cq.topic = ? AND cq.version = ?",
                (key['policy_id'], key['topic'], key['version'])
            )
            row = cursor.fetchone()
            if row:
                return row[0]
            
            # Semantic Fallback
            match_id = self.find_semantic_match(query)
            if match_id:
                cursor.execute("SELECT answer FROM answer_cache WHERE canonical_id = ?", (match_id,))
                row = cursor.fetchone()
                if row:
                    return row[0]
                    
        return None

    def get_fragment(self, query: str) -> Optional[Tuple[int, str]]:
        """Layer B Check: Fragment Cache lookup."""
        key = self.extract_canonical_key(query)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT cq.id, fc.fragment_text FROM fragment_cache fc "
                "JOIN canonical_queries cq ON fc.canonical_id = cq.id "
                "WHERE cq.policy_id = ? AND cq.topic = ? AND cq.version = ?",
                (key['policy_id'], key['topic'], key['version'])
            )
            row = cursor.fetchone()
            if row:
                return row
                
            # Semantic Fallback
            match_id = self.find_semantic_match(query)
            if match_id:
                cursor.execute("SELECT fragment_text FROM fragment_cache WHERE canonical_id = ?", (match_id,))
                row = cursor.fetchone()
                if row:
                    return (match_id, row[0])
                    
        return None

    def store_cache(self, query: str, answer: Optional[str] = None, fragment: Optional[str] = None):
        """Populates Layer A and/or Layer B."""
        key = self.extract_canonical_key(query)
        query_vec = self.embeddings.embed_query(query)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 1. Ensure canonical query exists or update it
            cursor.execute(
                "INSERT INTO canonical_queries (policy_id, topic, version, raw_query, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                (key['policy_id'], key['topic'], key['version'], query, json.dumps(query_vec).encode('utf-8'))
            )
            canonical_id = cursor.lastrowid
            
            # 2. Store Layer A: Answer
            if answer:
                cursor.execute(
                    "INSERT OR REPLACE INTO answer_cache (canonical_id, answer) VALUES (?, ?)",
                    (canonical_id, answer)
                )
                
            # 3. Store Layer B: Fragment
            if fragment:
                cursor.execute(
                    "INSERT OR REPLACE INTO fragment_cache (canonical_id, fragment_text) VALUES (?, ?)",
                    (canonical_id, fragment)
                )
            
            conn.commit()

    # ── Cache Invalidation (MD5 Sync) ─────────────────────────────────────────

    def _compute_md5(self, file_path: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def sync_and_invalidate(self):
        """
        Computes MD5 hashes for each .md file. 
        If a hash changes, invalidates all entries associated with that policy_id.
        """
        invalidated_policies = []
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Iterate through all .md files in policies dir
            for md_file in _POLICIES_DIR.rglob("*.md"):
                # Use filename stem as a basic policy_id for sync purposes
                # This should ideally match the policy_id used in canonical extraction
                policy_id = md_file.stem 
                current_hash = self._compute_md5(md_file)
                
                cursor.execute("SELECT last_hash FROM policy_files WHERE policy_id = ?", (policy_id,))
                row = cursor.fetchone()
                
                if not row:
                    # New file
                    cursor.execute(
                        "INSERT INTO policy_files (policy_id, file_path, last_hash) VALUES (?, ?, ?)",
                        (policy_id, str(md_file), current_hash)
                    )
                elif row[0] != current_hash:
                    # File changed! Invalidate related cache entries
                    logger.info(f"Invalidating cache for {policy_id} due to file change.")
                    cursor.execute("UPDATE policy_files SET last_hash = ? WHERE policy_id = ?", (current_hash, policy_id))
                    
                    # Due to ON DELETE CASCADE, deleting from canonical_queries cleans up Layer A & B
                    cursor.execute("DELETE FROM canonical_queries WHERE policy_id = ?", (policy_id,))
                    invalidated_policies.append(policy_id)
            
            conn.commit()
            
        return invalidated_policies
