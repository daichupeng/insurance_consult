# GraphRAG Optimization & Improvement Strategies

Optimizing GraphRAG for complex domains like insurance policies requires balancing cost, speed, and retrieval accuracy. This document outlines the key tuning levers across the two primary phases: **Indexing** (building the knowledge graph) and **Retrieval** (searching the graph).

## Phase 1: Indexing Strategy
*Goal: Ensure the LLM extracts the highest quality entities (rules, exclusions, benefits) and builds correct relationships before questions are asked.*

### 1. Structural Chunking Strategy
- **File to Tune:** `graphrag/prepare_input.py` (and `docling_parser.py`)
- **Optimization:** Instead of relying purely on naive token chunking (e.g., your recent change to `size: 500` in `settings.yaml`), implement **Hierarchical or Semantic Chunking** using the Docling library. 
- **Impact:** Ensures chunks end naturally at paragraph, section, or table boundaries. This prevents critical information (like a "Critical Illness Exclusion List") from being sliced in half, which would otherwise result in "orphan" facts detached from their parent policy.

### 2. Domain-Specific Prompts
- **Files to Tune:** `graphrag/prompts/extract_graph.txt` & `graphrag/prompts/extract_claims.txt`
- **Optimization:** Replace generic instructions with domain-specific rules. Explicitly instruct the LLM: *"You are an insurance underwriter. Extract 'Entities' only if they are Policies, Riders, Waiting Periods, Surrender Values, or Exclusions."* Provide few-shot examples of complex insurance clauses.
- **Impact:** Forces the graph to "speak" insurance. Avoids useless generic entities (e.g., "Singapore", "The Company") and creates a dense, precise graph (e.g., `[AIA Pro Lifetime Protector] --HAS_RIDER--> [Early Critical Illness]`).

### 3. Extracting Claims & Gleanings
- **File to Tune:** `graphrag/settings.yaml`
- **Optimization:** 
  - Ensure `extract_claims: enabled: true`.
  - Increase `max_gleanings` (e.g., to `2` or higher) under the `extract_graph` block if details are being missed.
- **Impact:** Enabling claims forces the extraction of strict, verifiable facts (e.g., *"Suicide within 1 year is excluded"*). Increasing `max_gleanings` forces the LLM to take multiple passes over complex text blocks to find entities missed on the first read, producing a much richer graph (at the tradeoff of increased time and cost).

### 4. Cost and Speed Management (Model Routing)
- **File to Tune:** `graphrag/settings.yaml` (under `completion_models`)
- **Optimization:** Use a powerful model like `gpt-4o` for complex entity extraction (`extract_graph`), but route simpler summarization tasks (`summarize_descriptions`, `community_reports`) to a faster, cheaper model like `gpt-4o-mini`.
- **Impact:** Significantly reduces token cost and API wait times during large bulk document indexing runs.

---

## Phase 2: Retrieval Strategy
*Goal: Manipulate the context window and search algorithm to fetch the right answers for the user.*

### 1. Dynamic Search Routing (`local` vs `global`)
- **File to Tune:** `agents/retriever.py` (or your core retrieval logic)
- **Optimization:** Route incoming user questions to the appropriate search mode programmatically depending on the user's intent:
  - **Local Search:** Use for specific factual questions (e.g., *"What is the waiting period for AIA Guaranteed Protect Plus?"*).
  - **Global Search:** Use for broad, dataset-wide questions (e.g., *"Summarize the common exclusions across all term life policies."*).
- **Impact:** Guarantees that specific queries aren't answered with vague summaries, and broad queries aren't answered with narrow, isolated data points.

### 2. Tuning the Local Context Window
- **File to Tune:** `graphrag/prompts/local_search_system_prompt.txt`
- **Optimization:** Adjust the LLM instructions on how to weigh retrieved facts (e.g., *"If you see an exclusion in the provided data, prioritize mentioning it immediately to limit liability"*). 
- **Impact:** Ensures the LLM correctly interprets the context around a retrieved node (e.g., knowing whether a `Waiting Period` applies to the base policy or just an attached rider from the surrounding graph edges).

### 3. Reframing Community Reports
- **Files to Tune:** `graphrag/prompts/community_report_graph.txt` and `graphrag/prompts/community_report_text.txt`
- **Optimization:** Rewrite the default templates (which are geared toward generalized security/incident analysis) to frame summaries around insurance priorities: *"Focus the summary on the breadth of coverage, severity of exclusions, and overall affordability."*
- **Impact:** Because `global_search` relies entirely on these pre-written reports, shaping how they are generated during the indexing phase drastically improves the quality and relevance of broad retrieval answers later on.
