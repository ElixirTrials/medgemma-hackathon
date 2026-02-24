#!/usr/bin/env python3
"""Evaluate prompt optimization changes against test_snippets.json.

Renders each template with actual test snippet data, compares old (git HEAD~1)
vs new (working tree) token counts, and validates template rendering.

Usage:
    uv run python scripts/evaluate_prompt_changes.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, BaseLoader, TemplateSyntaxError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = (
    PROJECT_ROOT
    / "services"
    / "protocol-processor-service"
    / "src"
    / "protocol_processor"
    / "prompts"
)
SNIPPETS_PATH = PROJECT_ROOT / "tests" / "e2e" / "test_snippets.json"

JINJA_ENV = Environment(loader=BaseLoader(), undefined=__import__("jinja2").Undefined)

# Templates and the git-relative paths used for `git show`
TEMPLATE_FILES = {
    "grounding_system.jinja2": "services/protocol-processor-service/src/protocol_processor/prompts/grounding_system.jinja2",
    "grounding_evaluate.jinja2": "services/protocol-processor-service/src/protocol_processor/prompts/grounding_evaluate.jinja2",
    "grounding_reasoning.jinja2": "services/protocol-processor-service/src/protocol_processor/prompts/grounding_reasoning.jinja2",
    "entity_decompose.jinja2": "services/protocol-processor-service/src/protocol_processor/prompts/entity_decompose.jinja2",
    "system.jinja2": "services/protocol-processor-service/src/protocol_processor/prompts/system.jinja2",
    "user.jinja2": "services/protocol-processor-service/src/protocol_processor/prompts/user.jinja2",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def tok(text: str) -> int:
    """Approximate token count (words * 1.3)."""
    return int(len(text.split()) * 1.3)


def load_snippets() -> dict:
    if not SNIPPETS_PATH.exists():
        print(f"ERROR: {SNIPPETS_PATH} not found")
        sys.exit(1)
    return json.loads(SNIPPETS_PATH.read_text())


def git_show(git_path: str, ref: str = "HEAD~1") -> str | None:
    """Return file contents at a git ref, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{git_path}"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def render(template_str: str, ctx: dict) -> str:
    """Render a Jinja2 template string with the given context."""
    try:
        tmpl = JINJA_ENV.from_string(template_str)
        return tmpl.render(**ctx)
    except TemplateSyntaxError as exc:
        return f"[RENDER ERROR: {exc}]"


def make_candidate(entity: dict) -> dict:
    """Build a fake candidate dict that mirrors real API shape."""
    return {
        "source_api": entity.get("system", "UMLS"),
        "code": entity.get("code", "C0000000"),
        "preferred_term": entity.get("entity_name", ""),
        "semantic_type": "Clinical Finding",
        "score": 0.95,
    }


# ---------------------------------------------------------------------------
# Evaluation runners
# ---------------------------------------------------------------------------
def evaluate_entity_decompose(
    snippets: dict, old_src: str | None, new_src: str
) -> list[dict]:
    """Render entity_decompose for each extraction snippet."""
    rows = []
    for i, snip in enumerate(snippets["extraction_test_snippets"]):
        ctx = {"criterion_text": snip["snippet_text"], "category": None}
        new_rendered = render(new_src, ctx)
        old_rendered = render(old_src, ctx) if old_src else ""
        rows.append(
            {
                "snippet_idx": i,
                "input": snip["snippet_text"][:80],
                "expected_class": snip["classification"],
                "old_tokens": tok(old_rendered) if old_src else "N/A",
                "new_tokens": tok(new_rendered),
                "renders_ok": "[RENDER ERROR" not in new_rendered,
            }
        )
    return rows


def evaluate_grounding_chain(
    snippets: dict,
    old_sys: str | None,
    new_sys: str,
    old_eval: str | None,
    new_eval: str,
    old_reason: str | None,
    new_reason: str,
) -> list[dict]:
    """Render grounding chain for each grounding snippet."""
    rows = []
    for i, snip in enumerate(snippets["grounding_test_snippets"]):
        for ent in snip["entities"]:
            # -- system prompt (static) --
            sys_new_tok = tok(new_sys)
            sys_old_tok = tok(old_sys) if old_sys else sys_new_tok

            # -- evaluate prompt --
            eval_ctx = {
                "entity_text": ent["entity_name"],
                "entity_type": "Condition",  # most common
                "criterion_context": snip["snippet_text"],
                "candidates": [make_candidate(ent)],
            }
            eval_new = render(new_eval, eval_ctx)
            eval_old = render(old_eval, eval_ctx) if old_eval else ""

            # -- reasoning prompt --
            reason_ctx = {
                "entity_text": ent["entity_name"],
                "entity_type": "Condition",
                "criterion_context": snip["snippet_text"],
                "previous_query": None,
                "attempt": 1,
            }
            reason_new = render(new_reason, reason_ctx)
            reason_old = render(old_reason, reason_ctx) if old_reason else ""

            total_old = sys_old_tok + tok(eval_old) + tok(reason_old) if old_sys else 0
            total_new = sys_new_tok + tok(eval_new) + tok(reason_new)

            rows.append(
                {
                    "snippet_idx": i,
                    "entity": ent["entity_name"][:40],
                    "code": ent["code"],
                    "relation": ent["relation"],
                    "old_chain_tokens": total_old if total_old else "N/A",
                    "new_chain_tokens": total_new,
                    "eval_renders_ok": "[RENDER ERROR" not in eval_new,
                    "reason_renders_ok": "[RENDER ERROR" not in reason_new,
                }
            )
    return rows


def evaluate_extraction(
    snippets: dict,
    old_sys: str | None,
    new_sys: str,
    old_user: str | None,
    new_user: str,
) -> list[dict]:
    """Render extraction system+user for a sample protocol title."""
    ctx = {"title": "Sample Protocol NCT00000001"}
    sys_new = render(new_sys, {})  # system has no variables
    sys_old = render(old_sys, {}) if old_sys else ""
    user_new = render(new_user, ctx)
    user_old = render(old_user, ctx) if old_user else ""
    return [
        {
            "old_system_tokens": tok(sys_old) if old_sys else "N/A",
            "new_system_tokens": tok(sys_new),
            "old_user_tokens": tok(user_old) if old_user else "N/A",
            "new_user_tokens": tok(user_new),
            "system_renders_ok": "[RENDER ERROR" not in sys_new,
            "user_renders_ok": "[RENDER ERROR" not in user_new,
        }
    ]


# Also test the demographic context skip in grounding_evaluate
def evaluate_demographic_skip(new_eval: str) -> dict:
    """Verify Demographic entities skip criterion context."""
    ctx_demo = {
        "entity_text": "age",
        "entity_type": "Demographic",
        "criterion_context": "Age 18 to 65 years" * 20,  # long context
        "candidates": [
            {
                "source_api": "UMLS",
                "code": "C0001779",
                "preferred_term": "Age",
                "semantic_type": None,
                "score": 0.99,
            }
        ],
    }
    ctx_cond = {
        "entity_text": "hypertension",
        "entity_type": "Condition",
        "criterion_context": "History of uncontrolled hypertension",
        "candidates": [
            {
                "source_api": "UMLS",
                "code": "C0020538",
                "preferred_term": "Hypertensive disease",
                "semantic_type": None,
                "score": 0.95,
            }
        ],
    }
    demo_rendered = render(new_eval, ctx_demo)
    cond_rendered = render(new_eval, ctx_cond)
    return {
        "demographic_has_criterion_ctx": "From criterion:" in demo_rendered,
        "condition_has_criterion_ctx": "From criterion:" in cond_rendered,
        "demographic_tokens": tok(demo_rendered),
        "condition_tokens": tok(cond_rendered),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def main() -> None:
    snippets = load_snippets()

    # Load old (pre-optimization) and new (current) template sources
    old_templates: dict[str, str | None] = {}
    new_templates: dict[str, str] = {}
    for name, git_path in TEMPLATE_FILES.items():
        old_templates[name] = git_show(git_path)
        path = PROMPTS_DIR / name
        new_templates[name] = path.read_text() if path.exists() else ""

    print("=" * 78)
    print("  PROMPT OPTIMIZATION EVALUATION — rendered against test_snippets.json")
    print("=" * 78)

    # -----------------------------------------------------------------------
    # 1. Entity decompose × extraction snippets
    # -----------------------------------------------------------------------
    print("\n1. ENTITY DECOMPOSE (rendered per extraction snippet)")
    print("-" * 78)
    decompose_rows = evaluate_entity_decompose(
        snippets,
        old_templates["entity_decompose.jinja2"],
        new_templates["entity_decompose.jinja2"],
    )
    print(
        f"  {'#':<3} {'Expected':<10} {'Old Tok':>8} {'New Tok':>8} {'Saved':>7} {'OK':>4}  Input"
    )
    for r in decompose_rows:
        old = r["old_tokens"]
        new = r["new_tokens"]
        saved = f"{old - new:>+d}" if isinstance(old, int) else "—"
        ok = "Y" if r["renders_ok"] else "FAIL"
        print(
            f"  {r['snippet_idx']:<3} {r['expected_class']:<10} {old!s:>8} {new:>8} {saved:>7} {ok:>4}  {r['input'][:50]}..."
        )

    # -----------------------------------------------------------------------
    # 2. Grounding chain × grounding snippets
    # -----------------------------------------------------------------------
    print("\n2. GROUNDING CHAIN (system + evaluate + reasoning, per entity)")
    print("-" * 78)
    grounding_rows = evaluate_grounding_chain(
        snippets,
        old_templates["grounding_system.jinja2"],
        new_templates["grounding_system.jinja2"],
        old_templates["grounding_evaluate.jinja2"],
        new_templates["grounding_evaluate.jinja2"],
        old_templates["grounding_reasoning.jinja2"],
        new_templates["grounding_reasoning.jinja2"],
    )
    print(
        f"  {'#':<3} {'Entity':<35} {'Code':<10} {'Rel':>4} {'Old':>7} {'New':>7} {'Saved':>7} {'OK':>4}"
    )
    total_old_grounding = 0
    total_new_grounding = 0
    for r in grounding_rows:
        old = r["old_chain_tokens"]
        new = r["new_chain_tokens"]
        saved = f"{old - new:>+d}" if isinstance(old, int) else "—"
        if isinstance(old, int):
            total_old_grounding += old
        total_new_grounding += new
        ok = "Y" if (r["eval_renders_ok"] and r["reason_renders_ok"]) else "FAIL"
        print(
            f"  {r['snippet_idx']:<3} {r['entity']:<35} {r['code']:<10} {r['relation']:>4} {old!s:>7} {new:>7} {saved:>7} {ok:>4}"
        )

    if total_old_grounding:
        pct = (total_old_grounding - total_new_grounding) / total_old_grounding * 100
        print(
            f"\n  Grounding chain total: {total_old_grounding} → {total_new_grounding} tokens ({pct:.1f}% reduction)"
        )

    # -----------------------------------------------------------------------
    # 3. Extraction system + user
    # -----------------------------------------------------------------------
    print("\n3. EXTRACTION (system.jinja2 + user.jinja2)")
    print("-" * 78)
    ext_rows = evaluate_extraction(
        snippets,
        old_templates["system.jinja2"],
        new_templates["system.jinja2"],
        old_templates["user.jinja2"],
        new_templates["user.jinja2"],
    )
    for r in ext_rows:
        for label, old_key, new_key, ok_key in [
            (
                "system.jinja2",
                "old_system_tokens",
                "new_system_tokens",
                "system_renders_ok",
            ),
            ("user.jinja2", "old_user_tokens", "new_user_tokens", "user_renders_ok"),
        ]:
            old = r[old_key]
            new = r[new_key]
            saved = f"{old - new:>+d}" if isinstance(old, int) else "—"
            ok = "Y" if r[ok_key] else "FAIL"
            print(
                f"  {label:<30} Old: {old!s:>6}  New: {new:>6}  Saved: {saved:>6}  OK: {ok}"
            )

    # -----------------------------------------------------------------------
    # 4. Demographic context skip validation
    # -----------------------------------------------------------------------
    print("\n4. DEMOGRAPHIC CONTEXT SKIP (grounding_evaluate.jinja2)")
    print("-" * 78)
    demo = evaluate_demographic_skip(new_templates["grounding_evaluate.jinja2"])
    demo_skip = "PASS" if not demo["demographic_has_criterion_ctx"] else "FAIL"
    cond_keep = "PASS" if demo["condition_has_criterion_ctx"] else "FAIL"
    print(
        f"  Demographic skips context:  {demo_skip}  (tokens: {demo['demographic_tokens']})"
    )
    print(
        f"  Condition keeps context:    {cond_keep}  (tokens: {demo['condition_tokens']})"
    )

    # -----------------------------------------------------------------------
    # 5. Aggregate summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 78}")
    print("  AGGREGATE TEMPLATE TOKEN COMPARISON (raw template, not rendered)")
    print(f"{'=' * 78}")
    print(f"\n  {'Template':<32} {'Old':>7} {'New':>7} {'Saved':>7} {'%':>7}")
    print(f"  {'-' * 32} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 7}")
    grand_old = 0
    grand_new = 0
    for name in sorted(TEMPLATE_FILES.keys()):
        old_src = old_templates[name]
        new_src = new_templates[name]
        old_t = tok(old_src) if old_src else 0
        new_t = tok(new_src)
        template_saved = old_t - new_t
        template_pct = f"{template_saved / old_t * 100:.1f}%" if old_t else "—"
        grand_old += old_t
        grand_new += new_t
        print(
            f"  {name:<32} {old_t:>7} {new_t:>7} {template_saved:>+7} {template_pct:>7}"
        )
    grand_saved = grand_old - grand_new
    grand_pct = f"{grand_saved / grand_old * 100:.1f}%" if grand_old else "—"
    print(f"  {'-' * 32} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 7}")
    print(
        f"  {'TOTAL':<32} {grand_old:>7} {grand_new:>7} {grand_saved:>+7} {grand_pct:>7}"
    )

    # -----------------------------------------------------------------------
    # 6. Test snippet coverage
    # -----------------------------------------------------------------------
    n_ext = len(snippets.get("extraction_test_snippets", []))
    n_gnd = len(snippets.get("grounding_test_snippets", []))
    n_ent = sum(len(s["entities"]) for s in snippets.get("grounding_test_snippets", []))
    n_with_units = sum(
        1
        for s in snippets.get("grounding_test_snippets", [])
        for e in s["entities"]
        if e.get("unit")
    )
    print(
        f"\n  Snippets tested: {n_ext} extraction, {n_gnd} grounding ({n_ent} entities)"
    )
    print(f"  Entities with units: {n_with_units}/{n_ent}")

    # Check for any render failures
    all_ok = (
        all(r["renders_ok"] for r in decompose_rows)
        and all(r["eval_renders_ok"] and r["reason_renders_ok"] for r in grounding_rows)
        and all(r["system_renders_ok"] and r["user_renders_ok"] for r in ext_rows)
        and not demo["demographic_has_criterion_ctx"]
        and demo["condition_has_criterion_ctx"]
    )
    print(
        f"  All templates render OK: {'YES' if all_ok else 'NO — CHECK FAILURES ABOVE'}"
    )
    print()


if __name__ == "__main__":
    main()
