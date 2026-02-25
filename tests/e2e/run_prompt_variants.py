#!/usr/bin/env python3
"""A/B testing harness for prompt variants on grounding failures.

Runs only the failing entities with multiple prompt variants and produces
a comparison report showing which variants fix which failures.

Strategy:
- Code mismatch tests: TerminologyRouter candidates cached once per entity,
  then MedGemma called per variant with patched _render_template.
- Relation mismatch tests: synthetic EntityGroundingResult built from golden
  data, then generate_field_mappings called per variant with patched
  create_structured_llm to inject extra rules.

API call budget: ~6 router + 24 MedGemma/Gemini + 6 field mapper = ~36 calls

Usage:
    set -a && source .env && set +a && uv run python tests/e2e/run_prompt_variants.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import TypedDict
from unittest.mock import patch

# ── sys.path setup (same pattern as run_grounding_snippets.py) ──────────────
_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root / "services" / "protocol-processor-service" / "src"))
sys.path.insert(0, str(_root / "services" / "api-service" / "src"))
sys.path.insert(0, str(_root / "libs" / "shared" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for prompt_variants

from prompt_variants import FIELD_MAPPER_VARIANTS, MEDGEMMA_VARIANTS  # noqa: E402

from protocol_processor.nodes.ground import _get_router  # noqa: E402
from protocol_processor.schemas.grounding import EntityGroundingResult  # noqa: E402
from protocol_processor.tools.field_mapper import generate_field_mappings  # noqa: E402
from protocol_processor.tools.medgemma_decider import (  # noqa: E402
    _render_template as _original_render_template,
    medgemma_decide,
)

SNIPPETS_PATH = Path(__file__).parent / "test_snippets.json"
RESULTS_DIR = Path(__file__).parent / "prompt_variant_results"

# ── Failing entities (hardcoded from test analysis) ─────────────────────────


class _CodeMismatchEntity(TypedDict):
    snippet_idx: int
    entity_idx: int
    entity_name: str
    expected_code: str


class _RelationMismatchEntity(TypedDict):
    snippet_idx: int
    entity_idx: int
    entity_name: str
    expected_relation: str
    golden_code: str
    golden_system: str
    golden_preferred_term: str


# Code mismatches: tested with MedGemma variants A-D
CODE_MISMATCH_ENTITIES: list[_CodeMismatchEntity] = [
    {
        "snippet_idx": 0,
        "entity_idx": 0,
        "entity_name": "Serum creatinine",
        "expected_code": "C0201976",
    },
    {
        "snippet_idx": 1,
        "entity_idx": 0,
        "entity_name": "Estimated Glomerular Filtration Rate",
        "expected_code": "C3811844",
    },
    {
        "snippet_idx": 3,
        "entity_idx": 0,
        "entity_name": "Ankylosing Spondylitis",
        "expected_code": "C0038013",
    },
    {
        "snippet_idx": 3,
        "entity_idx": 1,
        "entity_name": "Radiologic examination",
        "expected_code": "C0043299",
    },
    {
        "snippet_idx": 4,
        "entity_idx": 3,
        "entity_name": "GBA gene mutation",
        "expected_code": "C3888963",
    },
    {
        "snippet_idx": 8,
        "entity_idx": 0,
        "entity_name": "Pregnancy",
        "expected_code": "C0032961",
    },
]

# Relation mismatches: tested with field mapper variants A-B
RELATION_MISMATCH_ENTITIES: list[_RelationMismatchEntity] = [
    {
        "snippet_idx": 2,
        "entity_idx": 1,
        "entity_name": "Body Mass Index",
        "expected_relation": ">",
        "golden_code": "C1305855",
        "golden_system": "UMLS",
        "golden_preferred_term": "Body Mass Index",
    },
    {
        "snippet_idx": 5,
        "entity_idx": 0,
        "entity_name": "American Society of Anesthesiologists physical status classification",
        "expected_relation": "=",
        "golden_code": "C0450990",
        "golden_system": "UMLS",
        "golden_preferred_term": "ASA physical status classification",
    },
    {
        "snippet_idx": 8,
        "entity_idx": 0,
        "entity_name": "Pregnancy",
        "expected_relation": "!=",
        "golden_code": "C0032961",
        "golden_system": "SNOMED",
        "golden_preferred_term": "Pregnancy",
    },
]


# ── Patching helpers ────────────────────────────────────────────────────────


def _make_patched_render(variant: dict):
    """Create a patched _render_template for the given MedGemma variant.

    The wrapper calls the original _render_template, then appends variant-
    specific text to the rendered output for targeted template names.
    """

    def patched(template_name: str, **kwargs) -> str:
        rendered = _original_render_template(template_name, **kwargs)
        if template_name == "grounding_system.jinja2" and variant.get(
            "grounding_system"
        ):
            rendered += variant["grounding_system"]
        if template_name == "grounding_evaluate.jinja2" and variant.get(
            "grounding_evaluate"
        ):
            rendered += variant["grounding_evaluate"]
        return rendered

    return patched


class _PromptModifyingLLM:
    """Wrapper around a LangChain RunnableSequence that modifies prompts.

    LangChain's .with_structured_output() returns a RunnableSequence (Pydantic
    model) that doesn't allow attribute assignment. This wrapper delegates all
    calls to the real LLM but injects extra rules into the prompt.
    """

    def __init__(self, real_llm, extra_rules: str):
        self._real = real_llm
        self._extra = extra_rules

    async def ainvoke(self, prompt, *args, **kwargs):
        modified = prompt.replace("</rules>", self._extra + "\n</rules>")
        return await self._real.ainvoke(modified, *args, **kwargs)

    def invoke(self, prompt, *args, **kwargs):
        modified = prompt.replace("</rules>", self._extra + "\n</rules>")
        return self._real.invoke(modified, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _make_field_mapper_llm_wrapper(extra_rules: str):
    """Create a patched create_structured_llm that injects extra rules.

    Returns a drop-in replacement for create_structured_llm. The returned
    wrapper modifies prompts to insert extra rules before </rules>.
    """
    from protocol_processor.tools.gemini_utils import (
        create_structured_llm as _real_create,
    )

    def patched_create(output_schema):
        real_llm = _real_create(output_schema)
        if real_llm is None:
            return None
        return _PromptModifyingLLM(real_llm, extra_rules)

    return patched_create


# ── Code mismatch testing ──────────────────────────────────────────────────


async def _run_code_mismatch_tests(
    snippets: list[dict[str, str]],
) -> dict[str, dict[str, str | None]]:
    """Run code mismatch entities through each MedGemma variant.

    Step 1: Cache TerminologyRouter candidates per entity (one API call each).
    Step 2: For each variant, patch _render_template and call medgemma_decide.

    Returns: {variant_name: {entity_label: selected_code_or_None}}
    """
    router = _get_router()
    results: dict[str, dict[str, str | None]] = {}

    # Step 1: Cache candidates
    print("\n  Caching TerminologyRouter candidates...")
    cached_candidates: dict[str, list] = {}
    for ent in CODE_MISMATCH_ENTITIES:
        label = f"{ent['snippet_idx']}:{ent['entity_idx']}"
        entity_name = ent["entity_name"]
        candidates = await router.route_entity(entity_name, "Condition")
        cached_candidates[label] = candidates
        print(f"    {label} '{entity_name}': {len(candidates)} candidates")

    # Step 2: Run each variant
    for variant in MEDGEMMA_VARIANTS:
        vname = variant["name"]
        print(f"\n  Variant: {vname}")
        results[vname] = {}

        for ent in CODE_MISMATCH_ENTITIES:
            label = f"{ent['snippet_idx']}:{ent['entity_idx']}"
            entity_name = ent["entity_name"]
            snippet = snippets[ent["snippet_idx"]]
            criterion_text = snippet["snippet_text"]
            candidates = cached_candidates[label]

            entity_dict = {
                "text": entity_name,
                "entity_type": "Condition",
                "criterion_text": criterion_text,
            }

            patched_render = _make_patched_render(variant)
            with patch(
                "protocol_processor.tools.medgemma_decider._render_template",
                new=patched_render,
            ):
                try:
                    result = await medgemma_decide(
                        entity_dict, candidates, criterion_text
                    )
                    code = result.selected_code
                except Exception as e:
                    print(f"    {label} '{entity_name}': ERROR — {e}")
                    code = None

            match = "OK" if code == ent["expected_code"] else "MISS"
            print(f"    {label} '{entity_name}': {code} [{match}]")
            results[vname][label] = code

    return results


# ── Relation mismatch testing ──────────────────────────────────────────────


async def _run_relation_mismatch_tests(
    snippets: list[dict[str, str]],
) -> dict[str, dict[str, str | None]]:
    """Run relation mismatch entities through each field mapper variant.

    Uses synthetic EntityGroundingResult objects built from golden data
    (no TerminologyRouter or MedGemma calls needed).

    Returns: {variant_name: {entity_label: relation_or_None}}
    """
    results: dict[str, dict[str, str | None]] = {}

    for variant in FIELD_MAPPER_VARIANTS:
        vname = variant["name"]
        print(f"\n  Variant: {vname}")
        results[vname] = {}

        for ent in RELATION_MISMATCH_ENTITIES:
            label = f"{ent['snippet_idx']}:{ent['entity_idx']}"
            snippet = snippets[ent["snippet_idx"]]
            criterion_text = snippet["snippet_text"]

            # Build synthetic EntityGroundingResult from golden data
            entity_result = EntityGroundingResult(
                entity_text=ent["entity_name"],
                entity_type="Condition",
                selected_code=ent["golden_code"],
                selected_system=ent["golden_system"],
                preferred_term=ent["golden_preferred_term"],
                confidence=0.9,
                candidates=[],
                reasoning="A/B test harness — golden code used",
            )

            extra_rules = variant.get("field_mapper_rules_extra")
            try:
                if extra_rules:
                    wrapper = _make_field_mapper_llm_wrapper(extra_rules)
                    with patch(
                        "protocol_processor.tools.field_mapper.create_structured_llm",
                        new=wrapper,
                    ):
                        mappings = await generate_field_mappings(
                            entity_result, criterion_text
                        )
                else:
                    mappings = await generate_field_mappings(
                        entity_result, criterion_text
                    )
                relation = mappings[0].get("relation") if mappings else None
            except Exception as e:
                print(f"    {label} '{ent['entity_name']}': ERROR — {e}")
                relation = None

            match = "OK" if relation == ent["expected_relation"] else "MISS"
            print(f"    {label} '{ent['entity_name']}': {relation} [{match}]")
            results[vname][label] = relation

    return results


# ── Report printing ─────────────────────────────────────────────────────────


def _print_code_report(
    code_results: dict[str, dict[str, str | None]],
) -> None:
    """Print the code selection comparison table."""
    print(f"\n{'=' * 80}")
    print("CODE SELECTION VARIANTS (MedGemma prompt changes)")
    print(f"{'=' * 80}")

    variant_names = list(code_results.keys())

    # Header
    header = f"{'Entity':<26} {'Expected':<12}"
    for vn in variant_names:
        header += f" {vn:<14}"
    print(header)
    print("-" * len(header))

    # Rows
    totals = {vn: 0 for vn in variant_names}
    for ent in CODE_MISMATCH_ENTITIES:
        label = f"{ent['snippet_idx']}:{ent['entity_idx']}"
        name = ent["entity_name"][:24]
        expected = ent["expected_code"]
        row = f"{name:<26} {expected:<12}"
        for vn in variant_names:
            got = code_results[vn].get(label, "?")
            match = got == expected
            if match:
                totals[vn] += 1
            marker = "OK" if match else (got or "None")[:12]
            row += f" {marker:<14}"
        print(row)

    # Totals
    total_ents = len(CODE_MISMATCH_ENTITIES)
    print("-" * len(header))
    totals_row = f"{'Totals:':<26} {'':12}"
    for vn in variant_names:
        totals_row += f" {totals[vn]}/{total_ents:<12}"
    print(totals_row)


def _print_relation_report(
    relation_results: dict[str, dict[str, str | None]],
) -> None:
    """Print the relation extraction comparison table."""
    print(f"\n{'=' * 80}")
    print("RELATION EXTRACTION VARIANTS (Field mapper prompt changes)")
    print(f"{'=' * 80}")

    variant_names = list(relation_results.keys())

    # Header
    header = f"{'Entity':<26} {'Expected':<12}"
    for vn in variant_names:
        header += f" {vn:<16}"
    print(header)
    print("-" * len(header))

    # Rows
    totals = {vn: 0 for vn in variant_names}
    for ent in RELATION_MISMATCH_ENTITIES:
        label = f"{ent['snippet_idx']}:{ent['entity_idx']}"
        name = ent["entity_name"][:24]
        expected = ent["expected_relation"]
        row = f"{name:<26} {expected:<12}"
        for vn in variant_names:
            got = relation_results[vn].get(label, "?")
            match = got == expected
            if match:
                totals[vn] += 1
            marker = "OK" if match else (got or "None")[:14]
            row += f" {marker:<16}"
        print(row)

    # Totals
    total_ents = len(RELATION_MISMATCH_ENTITIES)
    print("-" * len(header))
    totals_row = f"{'Totals:':<26} {'':12}"
    for vn in variant_names:
        totals_row += f" {totals[vn]}/{total_ents:<14}"
    print(totals_row)


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    run_codes = "--relations-only" not in sys.argv
    run_relations = "--codes-only" not in sys.argv

    data = json.loads(SNIPPETS_PATH.read_text())
    snippets = data["grounding_test_snippets"]

    print("=" * 80)
    print("PROMPT A/B TESTING HARNESS")
    if run_codes:
        print(f"  Code mismatch entities: {len(CODE_MISMATCH_ENTITIES)}")
        print(f"  MedGemma variants: {len(MEDGEMMA_VARIANTS)}")
    if run_relations:
        print(f"  Relation mismatch entities: {len(RELATION_MISMATCH_ENTITIES)}")
        print(f"  Field mapper variants: {len(FIELD_MAPPER_VARIANTS)}")
    print("=" * 80)

    start = time.monotonic()

    code_results: dict = {}
    relation_results: dict = {}

    # ── Code mismatch tests ──
    if run_codes:
        print("\n[1/2] CODE SELECTION TESTS")
        code_results = await _run_code_mismatch_tests(snippets)

    # ── Relation mismatch tests ──
    if run_relations:
        print("\n[2/2] RELATION EXTRACTION TESTS")
        relation_results = await _run_relation_mismatch_tests(snippets)

    elapsed = time.monotonic() - start

    # ── Reports ──
    if code_results:
        _print_code_report(code_results)
    if relation_results:
        _print_relation_report(relation_results)

    print(f"\nTotal time: {elapsed:.1f}s")

    # ── Save JSON results ──
    if os.getenv("SAVE_RESULTS", "1") == "1":
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        output = {
            "code_selection": code_results,
            "relation_extraction": relation_results,
            "entities": {
                "code_mismatch": CODE_MISMATCH_ENTITIES,
                "relation_mismatch": [
                    {
                        k: v
                        for k, v in ent.items()
                        if k
                        not in (
                            "golden_code",
                            "golden_system",
                            "golden_preferred_term",
                        )
                    }
                    for ent in RELATION_MISMATCH_ENTITIES
                ],
            },
            "variants": {
                "medgemma": [v["name"] for v in MEDGEMMA_VARIANTS],
                "field_mapper": [v["name"] for v in FIELD_MAPPER_VARIANTS],
            },
        }
        out_path = RESULTS_DIR / "latest.json"
        out_path.write_text(json.dumps(output, indent=2))
        print(f"Results saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
