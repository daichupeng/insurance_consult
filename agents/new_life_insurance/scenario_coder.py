"""
Scenario coder agent.

Generates a self-contained Python file per policy that exposes a uniform
contract for the frontend simulator:

    INPUT_SCHEMA  : list[dict]   # field key/label/type/default/options/description
    OUTPUT_SCHEMA : list[dict]
    def simulate(inputs: dict) -> dict:
        ...

Generated files are saved to ``new_insurance_codebank/<policy>.py`` and reused on
subsequent runs. The agent also gets a ``read_policy_section`` tool to surface
lookup tables / clauses that aren't already in the structured ``key_info``.

The validator compiles the file, imports it in a subprocess, and probes the
contract; if anything fails the LLM is given the error message and asked to
fix it (bounded by ``max_iters``).

Execution of generated code happens in a child process so a runaway file
cannot deadlock the API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from schema.models import Policy
from tools.RAG import rag_search as _rag_search

logger = logging.getLogger(__name__)
load_dotenv()

_llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CODEBANK_DIR = _PROJECT_ROOT / "new_insurance_codebank"
_POLICIES_DIR = _PROJECT_ROOT / "raw_policies"
_CODEBANK_DIR.mkdir(exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _safe_filename(policy_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", policy_name or "").strip("_")
    return cleaned or "policy"


def codebank_path(policy_name: str) -> Path:
    return _CODEBANK_DIR / f"{_safe_filename(policy_name)}.py"


def _strip_code_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:python)?\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    return s.strip()


# ── Agent tool ─────────────────────────────────────────────────────────────────

def _resolve_policy_stem(policy_name: str) -> Optional[str]:
    """Map a free-form policy name to the `.md` file stem RAG indexed it under."""
    if not _POLICIES_DIR.exists() or not policy_name:
        return None
    target = _normalise(policy_name)
    for md in _POLICIES_DIR.rglob("*.md"):
        if _normalise(md.stem) == target:
            return md.stem
    return None


@tool
def read_policy_section(policy_name: str, query: str) -> str:
    """Semantic search over the policy's product summary, scoped to *policy_name*.

    Backed by the Qdrant RAG index of `raw_policies/**/*.md` (chunked by markdown
    section, with tables kept atomic). Returns the top relevant chunks with their
    heading path. Use this for lookup tables, surrender schedules, bonus rates,
    or clauses not already in the key_info JSON. Phrase queries as the concept
    you're looking for (e.g. "surrender value table", "guaranteed yearly income").
    """
    stem = _resolve_policy_stem(policy_name)
    if stem is None:
        return f"Error: policy markdown not found for '{policy_name}'"
    if not (query or "").strip():
        return "Error: query is empty"

    try:
        result = _rag_search.invoke({"query": query, "policy_name": stem, "top_k": 4})
    except Exception as e:
        return f"RAG error: {e}"
    return (result or "")[:6000]


# ── Prompt ─────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a financial-modelling code generator for life-insurance policies.

You will be given a policy's structured key_info JSON. The full product summary
is NOT in your context — to look up anything not in the key_info JSON, call the
`read_policy_section(policy_name, query)` tool. It runs semantic search over the
policy's product summary (chunked by markdown section, with tables kept intact)
and returns the top matching chunks with their heading path.

Use it freely — it is the only way to see content beyond the key_info JSON.
Call it multiple times with different queries when one search isn't enough
(e.g. one call for "surrender value table", another for "guaranteed yearly
income amounts"). Phrase queries as the *concept* you're looking for, not as
keywords to grep.

Produce a SINGLE Python file (no markdown fences, no commentary — code only)
that conforms to this contract:

    INPUT_SCHEMA : list[dict]
        Each dict: {
            "key": str,
            "label": str,
            "type": "number" | "integer" | "boolean" | "text" | "select",
            "default": Any,           # required
            "options": [ {"value": ..., "label": ...} ],   # only for type=="select"
            "description": str,       # optional
            "event_scope": ["claim"|"surrender"|"withdrawal"|"maturity"|"income"|...]
                                      # optional. If present, the field only applies
                                      # when `event` is in this list. Omit for fields
                                      # that always apply (e.g. sum_assured).
        }

    OUTPUT_SCHEMA : list[dict]
        Each dict: {"key": str, "label": str, "type": "number"|"text", "description": str}

    def simulate(inputs: dict) -> dict:
        # Return one entry per OUTPUT_SCHEMA key. Never raise — apply defaults
        # for missing/invalid inputs instead.

    if __name__ == "__main__":
        import json, sys
        print(json.dumps(simulate(json.loads(sys.stdin.read()))))

DESIGN RULES — read carefully, this is the most important part.

The INPUT_SCHEMA and OUTPUT_SCHEMA MUST be tailored to the actual policy.
Do NOT include fields the policy does not support. Do NOT omit policy-specific
concepts. Examples of policy-specific shaping:

  - An income / annuity-style policy with an accumulation phase MUST include
    inputs like `accumulation_year` (or `income_start_age`) and an event
    option like `"income"`. It MUST NOT include `withdrawal_amount` /
    `withdrawal_year` unless the policy actually offers ad-hoc withdrawals.
  - A pure term policy MUST NOT include `surrender_year` / surrender outputs.
  - A whole-life policy with no maturity benefit MUST NOT list `"maturity"`
    in the event options and MUST NOT output a maturity value.
  - If the policy has no multiplier rule, OMIT `multiplier_factor`.
  - If the policy has no critical illness / TPD / TI cover, OMIT those
    options from `claim_type` (or omit `claim_type` entirely).

For every event-specific input, set `event_scope` to the list of events it
applies to:
  - `claim_year`        → event_scope: ["claim"]
  - `claim_type`        → event_scope: ["claim"]
  - `surrender_year`    → event_scope: ["surrender"]
  - `accumulation_year` → event_scope: ["surrender", "claim", "income"]  (or wherever it matters)
Fields without an `event_scope` apply to every event (e.g. sum_assured,
entry_age, gender).

`event` (select): the option list MUST contain ONLY events the policy
actually supports. Common values: "claim", "surrender", "withdrawal",
"maturity", "income". Pick what fits.

OUTPUT_SCHEMA: list only outputs that the policy actually produces. Suggested
keys (omit any that don't apply):
  surrender_value, withdrawal_value, income_payout, death_benefit,
  cash_bonus, additional_cash_bonus, terminal_bonus,
  guaranteed_value, non_guaranteed_value, total_payout, notes (text).

DESCRIPTIONS — STRICT GROUNDING.

For every INPUT_SCHEMA and OUTPUT_SCHEMA field, the `description` (if present)
MUST be a 1-2 sentence explanation summarized FROM THE POLICY DOCUMENT. To
find it:

  1. Call `read_policy_section(policy_name, "<the field term, e.g. 'sum assured'>")`.
  2. Read the returned excerpt.
  3. Summarize the policy's definition / calculation rule in your own concise words.

Hard rules for descriptions:
  - DO NOT invent. If the document does not define the field, OMIT the
    `description` key entirely. An absent description is better than a
    fabricated one.
  - DO NOT restate the label (e.g. "Sum Assured: the sum assured" is banned).
  - DO NOT write generic / textbook definitions ("the amount paid on
    death") unless the document explicitly says that.
  - DO use product-specific phrasing the document uses (e.g. "Accumulation
    period: the years from policy inception to the income start date, during
    which premiums are paid and bonuses accrue.").
  - Keep each description ≤ 220 characters.
  - Use the SAME grounding rule for policy-specific concepts the agent
    invents (e.g. accumulation_year). If you can't ground it, drop the
    description but keep the field.

Hard implementation rules:
- Use ONLY Python stdlib. No numpy / pandas / requests / anything external.
- All constants, schedules, and lookup tables must be inlined as plain Python data.
- `simulate({})` must succeed and return a dict (use sensible defaults for every input).
- `simulate` must read inputs defensively (`inputs.get(...)` with defaults).
- Inside `simulate`, branch on `event` and only compute values relevant to
  that event; set unrelated outputs to 0.
- Keep the file under ~400 lines.
"""


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(path: Path) -> Optional[str]:
    """Return None on success, an error message otherwise."""
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Could not read file: {e}"

    try:
        compile(src, str(path), "exec")
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    probe = (
        "import importlib.util, json, sys;"
        f"spec=importlib.util.spec_from_file_location('m', r'{path}');"
        "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
        "out=m.simulate({});"
        "print(json.dumps({'inp': list(m.INPUT_SCHEMA),"
        " 'out': list(m.OUTPUT_SCHEMA),"
        " 'sample': out}, default=str))"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return "Probe timed out (>15s)"

    if proc.returncode != 0:
        return f"Runtime error: {(proc.stderr or '').strip()[:600]}"

    try:
        payload = json.loads(proc.stdout.strip().split("\n")[-1])
    except Exception as e:
        return f"Probe output not JSON: {e}; stdout={proc.stdout[:200]}"

    if not isinstance(payload.get("inp"), list) or not payload["inp"]:
        return "INPUT_SCHEMA must be a non-empty list"
    if not isinstance(payload.get("out"), list) or not payload["out"]:
        return "OUTPUT_SCHEMA must be a non-empty list"
    if not isinstance(payload.get("sample"), dict):
        return "simulate() must return a dict"

    out_keys = {o.get("key") for o in payload["out"] if isinstance(o, dict)}
    missing = out_keys - set(payload["sample"].keys())
    if missing:
        return f"simulate() missing OUTPUT_SCHEMA keys: {sorted(missing)}"

    return None


# ── Main agent ─────────────────────────────────────────────────────────────────

class ScenarioCoder:
    """Generates and caches per-policy simulator scripts."""

    def __init__(self, max_iters: int = 3, max_tool_turns: int = 8):
        self.max_iters = max_iters
        self.max_tool_turns = max_tool_turns

    def generate(self, policy: Policy, force: bool = False) -> Path:
        target = codebank_path(policy.policy_name)
        if target.exists() and not force:
            logger.info("[ScenarioCoder] cached: %s", target.name)
            return target

        key_info = policy.key_info or {}
        agent = _llm.bind_tools([read_policy_section])

        user_msg = (
            f"Policy: {policy.policy_name}\n\n"
            f"Key info (JSON):\n{json.dumps(key_info, indent=2, default=str)}\n\n"
            "Now write the simulator file. Use the read_policy_section tool whenever "
            "the key_info doesn't tell you the exact rule (e.g. surrender value tables, "
            "cash bonus rates). When done, respond with only the Python source — no fences."
        )

        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_msg)]
        resp = None

        for _ in range(self.max_tool_turns):
            resp = agent.invoke(messages)
            messages.append(resp)
            tool_calls = getattr(resp, "tool_calls", None) or []
            if not tool_calls:
                break
            for tc in tool_calls:
                try:
                    out = read_policy_section.invoke(tc.get("args", {}))
                except Exception as e:
                    out = f"Tool error: {e}"
                messages.append(ToolMessage(content=str(out)[:4000], tool_call_id=tc["id"]))

        code = _strip_code_fence(getattr(resp, "content", "") or "")
        if not code:
            raise RuntimeError(f"[ScenarioCoder] empty code for {policy.policy_name}")
        target.write_text(code, encoding="utf-8")

        # Validate + repair
        for attempt in range(self.max_iters):
            err = _validate(target)
            if err is None:
                logger.info("[ScenarioCoder] validated %s on attempt %d", target.name, attempt)
                return target
            logger.warning(
                "[ScenarioCoder] %s validation failed (attempt %d): %s",
                target.name, attempt, err,
            )
            messages.append(HumanMessage(content=(
                f"Validation failed:\n{err}\n\n"
                "Respond with the FULL corrected Python source only — no markdown fences."
            )))
            resp = _llm.invoke(messages)
            messages.append(resp)
            code = _strip_code_fence(getattr(resp, "content", "") or "")
            if code:
                target.write_text(code, encoding="utf-8")

        final_err = _validate(target)
        if final_err is not None:
            logger.error("[ScenarioCoder] giving up on %s: %s", policy.policy_name, final_err)
        return target


# ── Public helpers used by the API layer ──────────────────────────────────────

def load_schemas(policy_name: str) -> Dict[str, Any]:
    """Return {input_schema, output_schema} for a cached simulator, or {error}."""
    path = codebank_path(policy_name)
    if not path.exists():
        return {"error": f"No simulator for '{policy_name}'."}

    probe = (
        "import importlib.util, json, sys;"
        f"spec=importlib.util.spec_from_file_location('m', r'{path}');"
        "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
        "print(json.dumps({'input_schema': list(m.INPUT_SCHEMA),"
        " 'output_schema': list(m.OUTPUT_SCHEMA)}, default=str))"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"error": "Schema probe timed out"}

    if proc.returncode != 0:
        return {"error": (proc.stderr or "").strip()[:600]}
    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except Exception as e:
        return {"error": f"Schema parse failed: {e}"}


def run_simulator(policy_name: str, inputs: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    """Execute a cached simulator in a subprocess with the given inputs."""
    path = codebank_path(policy_name)
    if not path.exists():
        return {"error": f"No simulator for '{policy_name}'. Generate it first."}
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            input=json.dumps(inputs or {}),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": "Simulator timed out"}

    if proc.returncode != 0:
        return {"error": (proc.stderr or "").strip()[:1000]}
    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except Exception as e:
        return {"error": f"Output parse failed: {e}; stdout={proc.stdout[:200]}"}
