-- Table to track policy files and their MD5 hashes
CREATE TABLE IF NOT EXISTS policy_files (
    policy_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    last_hash TEXT NOT NULL
);

-- Table to store canonicalized queries and their embeddings for semantic fallback
CREATE TABLE IF NOT EXISTS canonical_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    version TEXT NOT NULL,
    raw_query TEXT NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES policy_files(policy_id) ON DELETE CASCADE
);

-- Layer A: Answer Cache
CREATE TABLE IF NOT EXISTS answer_cache (
    canonical_id INTEGER PRIMARY KEY,
    answer TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canonical_id) REFERENCES canonical_queries(id) ON DELETE CASCADE
);

-- Layer B: Fragment Cache
CREATE TABLE IF NOT EXISTS fragment_cache (
    canonical_id INTEGER PRIMARY KEY,
    fragment_text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canonical_id) REFERENCES canonical_queries(id) ON DELETE CASCADE
);

-- Index for faster canonical lookup
CREATE INDEX IF NOT EXISTS idx_canonical_lookup ON canonical_queries (policy_id, topic, version);
