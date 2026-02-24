#!/usr/bin/env python3
"""Ground the new test snippets (no expected values) and report results.

Usage:
    set -a && source .env && set +a
    uv run python scripts/test_new_snippets.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

SNIPPETS_PATH = Path(__file__).parent.parent / "tests" / "e2e" / "test_snippets.json"
data = json.loads(SNIPPETS_PATH.read_text())
grounding_snippets = data["grounding_test_snippets"]

# Only the new ones (empty entities)
NEW_SNIPPETS = [s for s in grounding_snippets if len(s["entities"]) == 0]


async def ground_snippet(snippet: dict) -> dict:
    """Ground using the entity names from the snippet via TerminologyRouter + MedGemma + OMOP."""
    from protocol_processor.nodes.ground import (
        _ground_entity_with_retry,
        _reconcile_dual_grounding,
    )
    from protocol_processor.tools.omop_mapper import lookup_omop_concept
    from protocol_processor.tools.terminology_router import (
        TerminologyRouter,
        _is_likely_acronym,
    )
    from protocol_processor.tools.entity_decomposer import (
        decompose_entities_from_criterion,
    )
    from protocol_processor.tools.field_mapper import generate_field_mappings
    from protocol_processor.nodes.ground import _ground_categorical_values

    router = TerminologyRouter()
    results = []

    # Step 1: Extract entities from snippet text using Gemini
    print("  Extracting entities...")
    entities = await decompose_entities_from_criterion(snippet["snippet_text"], None)
    print(
        f"  Found {len(entities)} entities: {[e.get('text', e.get('entity', '?')) for e in entities]}"
    )

    # Step 2: Ground each entity
    for ent in entities:
        entity_text = ent.get("text", ent.get("entity", ""))
        entity_type = ent.get("entity_type", "Condition")

        entity_dict = {
            "text": entity_text,
            "entity_type": entity_type,
            "criterion_text": snippet["snippet_text"],
        }

        try:
            acronym = _is_likely_acronym(entity_text)
            tu_task = _ground_entity_with_retry(
                entity_dict, router, snippet["snippet_text"]
            )
            omop_task = lookup_omop_concept(
                entity_text, entity_type, is_acronym=acronym
            )
            (result, _attempts), omop_result = await asyncio.gather(tu_task, omop_task)
            result = _reconcile_dual_grounding(result, omop_result)

            # Field mappings
            field_mappings = await generate_field_mappings(
                result, snippet["snippet_text"]
            )
            if field_mappings:
                field_mappings = _ground_categorical_values(field_mappings)
            result.field_mappings = field_mappings or None

            fm_summary = []
            if result.field_mappings:
                for fm in result.field_mappings:
                    v = fm.get("value", {})
                    val_str = v.get("value", "") if isinstance(v, dict) else str(v)
                    unit = v.get("unit", "") if isinstance(v, dict) else ""
                    rel = fm.get("relation", "")
                    fm_summary.append(f"{rel} {val_str} {unit}".strip())

            results.append(
                {
                    "entity_name": result.preferred_term or result.entity_text,
                    "entity_text": result.entity_text,
                    "entity_type": entity_type,
                    "system": result.selected_system,
                    "code": result.selected_code,
                    "confidence": result.confidence,
                    "omop_id": result.omop_concept_id,
                    "reconciliation": result.reconciliation_status,
                    "field_mappings_summary": fm_summary,
                }
            )
        except Exception as e:
            results.append(
                {
                    "entity_name": entity_text,
                    "entity_type": entity_type,
                    "error": str(e),
                }
            )

    return {"snippet_text": snippet["snippet_text"], "grounded_entities": results}


def print_results(all_results: list[dict]) -> None:
    for i, res in enumerate(all_results):
        print(f"\n{'=' * 80}")
        print(f"Snippet: {res['snippet_text']}")
        print(f"{'=' * 80}")

        for ent in res["grounded_entities"]:
            err = ent.get("error")
            if err:
                print(
                    f"  \033[31m✗\033[0m {ent['entity_name']} ({ent.get('entity_type', '?')})"
                )
                print(f"      ERROR: {err}")
                continue

            name = ent["entity_name"]
            system = ent.get("system", "?")
            code = ent.get("code", "?")
            conf = ent.get("confidence", 0)
            omop = ent.get("omop_id", "—")
            recon = ent.get("reconciliation", "—")
            etype = ent.get("entity_type", "?")
            fm = ent.get("field_mappings_summary", [])

            icon = "\033[32m✓\033[0m" if code else "\033[31m✗\033[0m"
            print(f"  {icon} {name}")
            print(f"      type={etype}  code={system}:{code}  conf={conf:.2f}")
            print(f"      omop={omop}  reconciliation={recon}")
            if fm:
                print(f"      field_mappings: {fm}")

        if not res["grounded_entities"]:
            print("  (no entities extracted)")


async def main() -> None:
    print("Grounding New Snippets — Full Extraction + Grounding")
    print(f"Running {len(NEW_SNIPPETS)} new snippets...\n")

    results = []
    for i, snippet in enumerate(NEW_SNIPPETS):
        print(f"[{i + 1}/{len(NEW_SNIPPETS)}] {snippet['snippet_text']}")
        result = await ground_snippet(snippet)
        results.append(result)

    print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
