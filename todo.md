# Project To-Do List

## How to Build / Rebuild the GraphRAG Database

The GraphRAG database is a knowledge graph extracted from insurance policy documents.
It stores entities (policies, benefits, exclusions, premiums, riders, conditions, terms),
relationships between them, and community-level summaries — all indexed for local and
global semantic search.

### Prerequisites
- Policy PDFs placed in `raw_policies/aia/` (and `raw_policies/income/` when available)
- `.env` at the project root with `OPENAI_API_KEY=sk-...`
- Project venv active: `source .venv/bin/activate` (or prefix all commands with `uv run`)

### Two-step build process

**Step 1 — Convert PDFs to plain text**

GraphRAG cannot parse raw PDF bytes. This step uses the Docling library (already installed)
to convert each policy PDF to Markdown-formatted plain text and writes the result to
`graphrag/input/`. Docling preserves table structure so benefit schedules are readable.

```bash
# From project root
uv run python graphrag/prepare_input.py
```

Use `--force` to re-convert already-existing files, or `--clear-output` to wipe the
stale graph output so the next index run starts completely fresh:

```bash
uv run python graphrag/prepare_input.py --clear-output   # fresh start
uv run python graphrag/prepare_input.py --force          # re-convert all PDFs
```

**Step 2 — Build the knowledge graph**

This step sends each text chunk to GPT-4o for entity and relationship extraction, then
clusters entities into communities and generates community reports. It uses the OpenAI
API and takes roughly 5–15 minutes depending on document count and chunk size.

```bash
uv run python graphrag/run_index.py
```

The output lands in `graphrag/output/` as Parquet files and a LanceDB vector store:

| File | Contents |
|------|----------|
| `entities.parquet` | Extracted entities (policy, benefit, exclusion, premium, …) |
| `relationships.parquet` | Weighted edges between entities |
| `communities.parquet` | Hierarchical entity clusters |
| `community_reports.parquet` | LLM-generated summaries per cluster |
| `text_units.parquet` | Source text chunks with embeddings |
| `lancedb/` | Vector store for semantic retrieval |

### Add new policy PDFs

1. Copy the PDF into `raw_policies/aia/` (or `raw_policies/income/` for Income policies)
2. Run `prepare_input.py` (converts only new files, skips existing ones)
3. Run `run_index.py` (incremental update — unchanged chunks hit the LLM cache)

### Current database status ✓

Built and ready. Indexed from:
- `AIA Guaranteed Protect Plus (III).pdf`
- `AIA Pro Lifetime Protector (II).pdf`

Stats: **317 entities · 327 relationships · 45 communities · 37 text units**

---

## Follow-up To-Do List

### 🔴 High Priority

- [x] **Enable claims extraction**
  In `graphrag/settings.yaml`, set `extract_claims: enabled: true`.
  Claims are factual assertions extracted directly from policy text
  (e.g. "covers up to SGD 1,000,000 under TPD", "30-day waiting period for CI").
  They are the single most precise signal for policy comparison and are
  currently disabled. After enabling, rebuild the index.

- [ ] **Customise the entity extraction prompt**
  Edit `graphrag/prompts/extract_graph.txt`.
  Add domain-specific instructions so the LLM extracts:
  - Exact benefit amounts and coverage limits as entity attributes
  - Premium figures and payment frequencies
  - Waiting periods and deferment periods
  - Exclusion conditions with reference to specific clauses
  This directly enriches the knowledge graph and improves retriever quality.

- [ ] **Customise community report prompts**
  Edit `graphrag/prompts/community_report_graph.txt` and
  `graphrag/prompts/community_report_text.txt`.
  The defaults use generic financial-risk framing ("impact severity",
  "vulnerabilities"). Reframe around insurance suitability:
  coverage breadth, affordability, exclusion severity, rider flexibility.
  Community reports are used by `global_search` in `GraphRAGRetriever`.

- [ ] **Index Income policies**
  `raw_policies/income/` exists but no PDFs are in it yet.
  Once added: run `prepare_input.py` then `run_index.py`.

### 🟡 Medium Priority

- [ ] **Unify vector stores**
  The project currently runs two incompatible vector stores:
  - Qdrant + MLX/MiniLM embeddings (used by the old `Retriever`)
  - LanceDB + OpenAI `text-embedding-3-large` (used by `GraphRAGRetriever`)
  Since `GraphRAGRetriever` is now the primary retriever in the workflow,
  the Qdrant store in `tools/search_tools.py` is no longer used.
  Options:
  - (Recommended) Remove Qdrant dependency and the old `Retriever` class
  - Keep both and document their distinct roles explicitly

- [ ] **Tune chunking for insurance documents**
  Current setting: 1200 tokens / 100 overlap (token-based, in `settings.yaml`).
  Insurance PDFs have self-contained sections (benefit schedule tables, exclusion
  lists, definitions) that should not split mid-clause.
  Consider: use Docling's `HierarchicalChunker` (already in `rag/docling_parser.py`)
  to generate section-aware chunks during `prepare_input.py`, preserving clause
  boundaries before handoff to GraphRAG.

- [ ] **Handle `asyncio.run()` from inside a running event loop**
  `agents/graph_rag_retriever.py` uses `asyncio.run()` which works correctly from
  the background thread in `api/session_manager.py`. If the retriever is ever called
  from an async context (e.g. a future async FastAPI endpoint), it will raise
  `RuntimeError: This event loop is already running`.
  Fix: add `nest_asyncio` as a fallback, or refactor `retrieve()` to `async def`.

- [ ] **Improve per-policy scoping in GraphRAG queries**
  All policy documents are indexed into one shared graph. The current workaround
  is to embed the policy name in every query string. A more robust solution is to
  tag entities with their source document during indexing (via claims or custom
  metadata) and filter at retrieval time. Requires custom prompt engineering.

### 🟢 Low Priority

- [ ] **Automate the prepare + index pipeline**
  Wire `prepare_input.py` and `run_index.py` into a single convenience command:
  ```bash
  uv run python graphrag/rebuild_index.py          # prepare + index
  uv run python graphrag/rebuild_index.py --fresh  # clear + prepare + index
  ```
  Useful when adding new policies regularly.

- [ ] **Add smoke tests for `GraphRAGRetriever`**
  `agents/graph_rag_retriever.py` has no automated tests.
  A lightweight test that loads the parquet files and issues one `local_search`
  call (can be mocked at the API level) would catch config regressions early.

- [ ] **Complete `ScoringReviewer` and `ReportWriter`**
  Both agents in `agents/scoring_reviewer.py` and `agents/report_writer.py` are
  stubs with no implementation. The workflow skips them today.
  `ReportWriter` should generate a structured final report (Markdown or PDF)
  ranking policies by weighted score with supporting evidence.

- [ ] **Expose `GraphRAGRetriever` progress to the frontend**
  Retrieval is the slowest step (many LLM API calls). The frontend currently shows
  a single "Retrieving relevant policy documents…" status message.
  Add finer-grained updates: "Querying AIA GPP III — filter 1/3", etc.
  Requires passing a progress callback into `GraphRAGRetriever.retrieve()`.

- [ ] **Run indexing from the frontend (admin panel)**
  Add an `/admin` route to the FastAPI app with a "Rebuild Index" button that
  runs `prepare_input.py` + `run_index.py` in a background thread and streams
  log output to the browser via WebSocket.
