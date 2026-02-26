#!/usr/bin/env python3
"""Grounding Variant Experiment — run ALL grounding test entities through 3 prompt variants.

Runs 3 variants (A: Baseline, B: Targeted, C: Enhanced) across all grounding
test snippets and compares code selection, relation, value, and unit results.

Phases:
  1. Cache — TerminologyRouter candidates + unit normalization (one-time API calls)
  2. Run — 3 variants × all entities through medgemma_decide + generate_field_mappings
  3. Score — compare each dimension against golden data
  4. Analyze — MLFlow trace analysis (failure patterns, confidence, retries, latency)
  5. Decide — stop or continue recommendation

Usage:
    set -a && source .env && set +a && uv run python tests/e2e/run_variant_experiment.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ── sys.path setup ────────────────────────────────────────────────────────
_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root / "services" / "protocol-processor-service" / "src"))
sys.path.insert(0, str(_root / "services" / "api-service" / "src"))
sys.path.insert(0, str(_root / "libs" / "shared" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for prompt_variants

from shared.warnings_config import suppress_google_genai_deprecations  # noqa: E402

suppress_google_genai_deprecations()

from prompt_variants import EXPERIMENT_VARIANTS  # noqa: E402

from protocol_processor.nodes.ground import _get_router  # noqa: E402
from protocol_processor.prompts import render_template as _original_render_template  # noqa: E402
from protocol_processor.schemas.grounding import EntityGroundingResult  # noqa: E402
from protocol_processor.tools.field_mapper import generate_field_mappings  # noqa: E402
from protocol_processor.tools.medgemma_decider import medgemma_decide  # noqa: E402
from protocol_processor.tools.unit_normalizer import normalize_unit  # noqa: E402

SNIPPETS_PATH = Path(__file__).parent / "test_snippets.json"
RESULTS_DIR = Path(__file__).parent / "prompt_variant_results"

# ── Entity type mapping (for router dispatch + failure analysis) ──────────

_ENTITY_TYPE_MAP: dict[str, str] = {
    "Serum creatinine": "Lab_Value",
    "Estimated Glomerular Filtration Rate": "Lab_Value",
    "Body Weight": "Lab_Value",
    "Body Mass Index": "Lab_Value",
    "Ankylosing Spondylitis": "Condition",
    "Radiologic examination": "Procedure",
    "Male Gender": "Demographic",
    "Female Phenotype": "Demographic",
    "Parkinson's Disease": "Condition",
    "GBA gene mutation": "Condition",
    "American Society of Anesthesiologists physical status classification": "Procedure",
    "Female Sterilization": "Procedure",
    "Collection of venous blood by venipuncture": "Procedure",
    "Pregnancy": "Condition",
    "Total Knee Arthroplasty": "Procedure",
    "Osteoarthritis of the Knee": "Condition",
    "Postmenopause": "Condition",
    "Barrier Contraception": "Medication",
    "Oral Contraceptive": "Medication",
}


def _entity_type(name: str) -> str:
    return _ENTITY_TYPE_MAP.get(name, "Condition")


# ── Patching helpers (reused from run_prompt_variants.py) ─────────────────


def _make_patched_render(variant: dict):
    """Create a patched render_template that appends variant-specific text."""

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
    """Wrapper that injects extra rules before </rules> in prompts."""

    def __init__(self, real_llm: Any, extra_rules: str):
        self._real = real_llm
        self._extra = extra_rules

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        modified = prompt.replace("</rules>", self._extra + "\n</rules>")
        return await self._real.ainvoke(modified, *args, **kwargs)

    def invoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        modified = prompt.replace("</rules>", self._extra + "\n</rules>")
        return self._real.invoke(modified, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _make_field_mapper_llm_wrapper(extra_rules: str):
    """Create a patched create_structured_llm that injects extra rules."""
    from protocol_processor.tools.gemini_utils import (
        create_structured_llm as _real_create,
    )

    def patched_create(output_schema: Any) -> Any:
        real_llm = _real_create(output_schema)
        if real_llm is None:
            return None
        return _PromptModifyingLLM(real_llm, extra_rules)

    return patched_create


# ── Data types ────────────────────────────────────────────────────────────


class EntityResult:
    """Per-entity result for one variant run."""

    __slots__ = (
        "entity_name",
        "entity_type",
        "code",
        "confidence",
        "relation",
        "value",
        "latency_ms",
        "error",
        "retries",
    )

    def __init__(self) -> None:
        self.entity_name: str = ""
        self.entity_type: str = ""
        self.code: str | None = None
        self.confidence: float = 0.0
        self.relation: str | None = None
        self.value: str | None = None
        self.latency_ms: float = 0.0
        self.error: str | None = None
        self.retries: int = 0


# ── Phase 1: Cache ────────────────────────────────────────────────────────


async def _cache_candidates(
    snippets: list[dict],
) -> dict[str, list]:
    """Cache TerminologyRouter candidates per entity (one API call each)."""
    router = _get_router()
    cached: dict[str, list] = {}

    for s_idx, snippet in enumerate(snippets):
        for e_idx, golden in enumerate(snippet["entities"]):
            key = f"{s_idx}:{e_idx}"
            name = golden["entity_name"]
            etype = _entity_type(name)
            try:
                candidates = await router.route_entity(name, etype)
            except Exception as e:
                print(f"    WARN: router failed for {key} '{name}': {e}")
                candidates = []
            cached[key] = candidates
            print(f"    {key} '{name}' ({etype}): {len(candidates)} candidates")

    return cached


def _cache_units(snippets: list[dict]) -> dict[str, tuple[str | None, int | None]]:
    """Cache normalize_unit() results per entity (deterministic, no LLM)."""
    cached: dict[str, tuple[str | None, int | None]] = {}
    for s_idx, snippet in enumerate(snippets):
        for e_idx, golden in enumerate(snippet["entities"]):
            unit = golden.get("unit")
            if unit is not None:
                key = f"{s_idx}:{e_idx}"
                cached[key] = normalize_unit(unit)
    return cached


# ── Phase 2: Run variants ────────────────────────────────────────────────


async def _run_entity(
    variant: dict,
    snippet: dict,
    golden: dict,
    s_idx: int,
    e_idx: int,
    candidates: list,
    semaphore: asyncio.Semaphore,
) -> EntityResult:
    """Run a single entity through medgemma_decide + generate_field_mappings."""
    result = EntityResult()
    result.entity_name = golden["entity_name"]
    result.entity_type = _entity_type(golden["entity_name"])

    entity_dict = {
        "text": golden["entity_name"],
        "entity_type": result.entity_type,
        "criterion_text": snippet["snippet_text"],
    }

    async with semaphore:
        t0 = time.monotonic()
        try:
            # ── Code selection (MedGemma) ──
            patched_render = _make_patched_render(variant)
            with patch(
                "protocol_processor.prompts.render_template",
                new=patched_render,
            ):
                grounding_result = await medgemma_decide(
                    entity_dict, candidates, snippet["snippet_text"]
                )
            result.code = grounding_result.selected_code
            result.confidence = grounding_result.confidence

            # ── Field mapping (Gemini) ──
            # Build a synthetic EntityGroundingResult using the code we just got
            entity_for_fm = EntityGroundingResult(
                entity_text=golden["entity_name"],
                entity_type=result.entity_type,
                selected_code=grounding_result.selected_code,
                selected_system=grounding_result.selected_system,
                preferred_term=grounding_result.preferred_term,
                confidence=grounding_result.confidence,
                candidates=candidates,
                reasoning=grounding_result.reasoning,
            )

            extra_rules = variant.get("field_mapper_rules_extra")
            if extra_rules:
                wrapper = _make_field_mapper_llm_wrapper(extra_rules)
                with patch(
                    "protocol_processor.tools.field_mapper.create_structured_llm",
                    new=wrapper,
                ):
                    mappings = await generate_field_mappings(
                        entity_for_fm, snippet["snippet_text"]
                    )
            else:
                mappings = await generate_field_mappings(
                    entity_for_fm, snippet["snippet_text"]
                )

            if mappings:
                result.relation = mappings[0].get("relation")
                val_obj = mappings[0].get("value", {})
                if isinstance(val_obj, dict):
                    result.value = val_obj.get("value")
                else:
                    result.value = str(val_obj)

        except Exception as e:
            result.error = str(e)
        finally:
            result.latency_ms = (time.monotonic() - t0) * 1000

    return result


async def _run_variant(
    variant: dict,
    snippets: list[dict],
    cached_candidates: dict[str, list],
    semaphore: asyncio.Semaphore,
) -> dict[str, EntityResult]:
    """Run all entities through one variant."""
    vname = variant["name"]
    print(f"\n  Running variant: {vname}")

    tasks = []
    keys = []
    for s_idx, snippet in enumerate(snippets):
        for e_idx, golden in enumerate(snippet["entities"]):
            key = f"{s_idx}:{e_idx}"
            keys.append(key)
            tasks.append(
                _run_entity(
                    variant,
                    snippet,
                    golden,
                    s_idx,
                    e_idx,
                    cached_candidates.get(key, []),
                    semaphore,
                )
            )

    results = await asyncio.gather(*tasks)

    entity_results: dict[str, EntityResult] = {}
    for key, er in zip(keys, results):
        entity_results[key] = er
        status = "OK" if not er.error else f"ERR: {er.error[:60]}"
        print(f"    {key} '{er.entity_name[:40]}': code={er.code} [{status}]")

    return entity_results


# ── Phase 3: Score & Compare ──────────────────────────────────────────────


def _score_variants(
    variant_results: dict[str, dict[str, EntityResult]],
    snippets: list[dict],
    unit_cache: dict[str, tuple[str | None, int | None]],
) -> dict[str, dict[str, dict[str, str]]]:
    """Score each variant on 5 dimensions per entity.

    Returns: {variant_name: {entity_key: {metric: "OK"|"MISS (got)"}}}
    """
    scores: dict[str, dict[str, dict[str, str]]] = {}

    for vname, results in variant_results.items():
        scores[vname] = {}
        for s_idx, snippet in enumerate(snippets):
            for e_idx, golden in enumerate(snippet["entities"]):
                key = f"{s_idx}:{e_idx}"
                er = results.get(key)
                if er is None:
                    scores[vname][key] = {
                        "code": "ERR",
                        "relation": "ERR",
                        "value": "ERR",
                    }
                    continue

                entry: dict[str, str] = {}

                # Code match
                if er.code == golden["code"]:
                    entry["code"] = "OK"
                else:
                    entry["code"] = f"MISS ({er.code})"

                # Relation match
                expected_rel = golden.get("relation")
                if expected_rel is None:
                    entry["relation"] = "N/A"
                elif er.relation == expected_rel:
                    entry["relation"] = "OK"
                else:
                    entry["relation"] = f"MISS ({er.relation})"

                # Value match
                expected_val = golden.get("value")
                if expected_val is None:
                    entry["value"] = "N/A"
                elif er.value == expected_val:
                    entry["value"] = "OK"
                else:
                    entry["value"] = f"MISS ({er.value})"

                # Unit UCUM match
                if key in unit_cache:
                    got_ucum, got_omop = unit_cache[key]
                    expected_ucum = golden.get("unit_ucum")
                    expected_omop = golden.get("unit_omop_concept_id")
                    entry["unit_ucum"] = (
                        "OK" if got_ucum == expected_ucum else f"MISS ({got_ucum})"
                    )
                    entry["unit_omop"] = (
                        "OK" if got_omop == expected_omop else f"MISS ({got_omop})"
                    )

                scores[vname][key] = entry

    return scores


def _count_matches(
    scores: dict[str, dict[str, dict[str, str]]],
    metric: str,
) -> dict[str, tuple[int, int]]:
    """Count matches for a metric across variants. Returns {vname: (ok, total)}."""
    counts: dict[str, tuple[int, int]] = {}
    for vname, entities in scores.items():
        ok = 0
        total = 0
        for entry in entities.values():
            val = entry.get(metric)
            if val is None or val == "N/A":
                continue
            total += 1
            if val == "OK":
                ok += 1
        counts[vname] = (ok, total)
    return counts


# ── Phase 4: MLFlow Trace Analysis ───────────────────────────────────────


def _analyze_traces(
    variant_results: dict[str, dict[str, EntityResult]],
    scores: dict[str, dict[str, dict[str, str]]],
    snippets: list[dict],
) -> dict[str, Any]:
    """Analyze per-variant trace data collected during Phase 2.

    Since MLFlow trace store queries require the MLFlow server running and
    the SQLite DB to be populated, this function uses the inline-collected
    data (confidence, latency, retries, error) from EntityResult objects.
    """
    analysis: dict[str, Any] = {}

    for vname in variant_results:
        results = variant_results[vname]
        entity_scores = scores[vname]

        # Failure patterns: group mismatches by entity type and dimension
        failures_by_type: dict[str, dict[str, int]] = {}
        for key, entry in entity_scores.items():
            er = results.get(key)
            if er is None:
                continue
            etype = er.entity_type
            for metric in ("code", "relation", "value"):
                val = entry.get(metric, "N/A")
                if val not in ("OK", "N/A"):
                    failures_by_type.setdefault(etype, {})
                    failures_by_type[etype][metric] = (
                        failures_by_type[etype].get(metric, 0) + 1
                    )

        # Confidence vs accuracy
        conf_correct: list[float] = []
        conf_incorrect: list[float] = []
        for key, entry in entity_scores.items():
            er = results.get(key)
            if er is None:
                continue
            code_ok = entry.get("code") == "OK"
            if code_ok:
                conf_correct.append(er.confidence)
            elif entry.get("code", "N/A") != "N/A":
                conf_incorrect.append(er.confidence)

        # Retry stats — we don't have direct retry counts from inline data,
        # but we can count errors as proxy for "needed retry"
        error_count = sum(1 for er in results.values() if er.error)

        # Latency
        latencies = sorted(
            er.latency_ms for er in results.values() if er.latency_ms > 0
        )
        median_lat = latencies[len(latencies) // 2] if latencies else 0
        p95_lat = latencies[int(len(latencies) * 0.95)] if latencies else 0

        analysis[vname] = {
            "failures_by_type": failures_by_type,
            "avg_conf_correct": (
                sum(conf_correct) / len(conf_correct) if conf_correct else 0
            ),
            "avg_conf_incorrect": (
                sum(conf_incorrect) / len(conf_incorrect) if conf_incorrect else 0
            ),
            "error_count": error_count,
            "median_latency_ms": median_lat,
            "p95_latency_ms": p95_lat,
        }

    return analysis


# ── Phase 5: Recommendation ──────────────────────────────────────────────


def _recommend(
    scores: dict[str, dict[str, dict[str, str]]],
    analysis: dict[str, Any],
) -> str:
    """Generate stop/continue recommendation from scores and analysis."""
    # Find best variant by total correct across code + relation + value
    best_name = ""
    best_score = -1
    best_total = 0
    variant_totals: dict[str, tuple[int, int]] = {}

    for vname, entities in scores.items():
        ok = 0
        total = 0
        for entry in entities.values():
            for metric in ("code", "relation", "value"):
                val = entry.get(metric, "N/A")
                if val == "N/A":
                    continue
                total += 1
                if val == "OK":
                    ok += 1
        variant_totals[vname] = (ok, total)
        if ok > best_score:
            best_score = ok
            best_total = total
            best_name = vname

    # Check if 100% on all dimensions
    if best_score == best_total and best_total > 0:
        return (
            f"STOP — Winner: {best_name} ({best_score}/{best_total} perfect).\n"
            f"  Apply prompt diff to production."
        )

    # Count failures for best variant
    best_entities = scores[best_name]
    results_a = analysis.get(best_name, {})
    failures_by_type = results_a.get("failures_by_type", {})

    total_failures = sum(sum(counts.values()) for counts in failures_by_type.values())
    num_types_with_failures = len(failures_by_type)

    # Collect specific failure entities for reporting
    failure_details: list[str] = []
    for key, entry in best_entities.items():
        for metric in ("code", "relation", "value"):
            val = entry.get(metric, "N/A")
            if val not in ("OK", "N/A"):
                failure_details.append(f"  {key}: {metric} {val}")

    # Check if all variants are equal (no improvement)
    all_equal = len(set(v[0] for v in variant_totals.values())) == 1
    if all_equal:
        return (
            "STOP — All variants perform equally. Prompts are not the bottleneck.\n"
            "  Investigate TerminologyRouter candidate quality or model capability."
        )

    if total_failures <= 2 and num_types_with_failures == 1:
        failing_type = list(failures_by_type.keys())[0]
        return (
            f"STOP — Winner: {best_name} ({best_score}/{best_total}).\n"
            f"  {total_failures} failure(s) in {failing_type} type only.\n"
            f"  If 4th variant needed, target: {failing_type}-specific prompt addition.\n"
            + "\n".join(failure_details)
        )

    # More than 2 failures across types → continue
    hypothesis_lines = [
        "# Variant D Hypothesis",
        "",
        "## Context",
        f"Best variant: {best_name} ({best_score}/{best_total})",
        f"Total failures: {total_failures} across {num_types_with_failures} entity types",
        "",
        "## Failure Breakdown",
    ]
    for etype, counts in failures_by_type.items():
        hypothesis_lines.append(f"- {etype}: {counts}")
    hypothesis_lines.extend(
        [
            "",
            "## Proposed Changes",
            "Based on failure pattern analysis, Variant D should address:",
        ]
    )
    for etype, counts in failures_by_type.items():
        for metric, count in counts.items():
            hypothesis_lines.append(
                f"- {etype} {metric} failures ({count}): add {etype}-specific "
                f"{'code selection' if metric == 'code' else 'field mapper'} rules"
            )
    hypothesis_lines.extend(
        [
            "",
            "## Specific Failures",
            *failure_details,
        ]
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    hyp_path = RESULTS_DIR / "variant_d_hypothesis.md"
    hyp_path.write_text("\n".join(hypothesis_lines))

    return (
        f"CONTINUE — Best variant: {best_name} ({best_score}/{best_total}).\n"
        f"  {total_failures} failures across {num_types_with_failures} entity types.\n"
        f"  Variant D hypothesis saved to {hyp_path}\n" + "\n".join(failure_details)
    )


# ── Report printing ───────────────────────────────────────────────────────


def _print_entity_table(
    scores: dict[str, dict[str, dict[str, str]]],
    snippets: list[dict],
) -> None:
    """Print the per-entity comparison table."""
    variant_names = list(scores.keys())
    vn_width = max(len(vn) for vn in variant_names)
    vn_width = max(vn_width, 12)

    header = f"{'Entity':<30} {'Metric':<10} {'Expected':<14}"
    for vn in variant_names:
        header += f" {vn:<{vn_width}}"
    print(header)
    print("─" * len(header))

    for s_idx, snippet in enumerate(snippets):
        for e_idx, golden in enumerate(snippet["entities"]):
            key = f"{s_idx}:{e_idx}"
            name = golden["entity_name"]
            display_name = name[:28]

            for metric, expected_key in [
                ("code", "code"),
                ("relation", "relation"),
                ("value", "value"),
            ]:
                expected = golden.get(expected_key, "")
                if expected is None:
                    continue

                expected_str = str(expected)[:12]
                label = display_name if metric == "code" else ""
                row = f"{label:<30} {metric:<10} {expected_str:<14}"

                for vn in variant_names:
                    val = scores[vn].get(key, {}).get(metric, "?")
                    display = val[:vn_width] if isinstance(val, str) else str(val)
                    row += f" {display:<{vn_width}}"
                print(row)

            # Unit metrics (only if entity has units)
            if golden.get("unit") is not None:
                for metric in ("unit_ucum", "unit_omop"):
                    expected_key_u = (
                        "unit_ucum" if metric == "unit_ucum" else "unit_omop_concept_id"
                    )
                    expected_val = golden.get(expected_key_u, "")
                    expected_str = str(expected_val)[:12] if expected_val else ""
                    row = f"{'':<30} {metric:<10} {expected_str:<14}"
                    for vn in variant_names:
                        val = scores[vn].get(key, {}).get(metric, "N/A")
                        display = val[:vn_width] if isinstance(val, str) else str(val)
                        row += f" {display:<{vn_width}}"
                    print(row)


def _print_summary(
    scores: dict[str, dict[str, dict[str, str]]],
) -> None:
    """Print the variant summary table."""
    variant_names = list(scores.keys())
    vn_width = max(len(vn) for vn in variant_names)
    vn_width = max(vn_width, 14)

    header = f"{'':20}"
    for vn in variant_names:
        header += f" {vn:<{vn_width}}"
    print(header)

    for metric in ("code", "relation", "value", "unit_ucum", "unit_omop"):
        counts = _count_matches(scores, metric)
        label = {
            "code": "Code match:",
            "relation": "Relation match:",
            "value": "Value match:",
            "unit_ucum": "Unit UCUM:",
            "unit_omop": "Unit OMOP:",
        }[metric]

        row = f"{label:20}"
        for vn in variant_names:
            ok, total = counts.get(vn, (0, 0))
            if total > 0:
                pct = 100 * ok // total
                cell = f"{ok}/{total} ({pct}%)"
            else:
                cell = "N/A"
            row += f" {cell:<{vn_width}}"
        print(row)


def _print_analysis(analysis: dict[str, Any]) -> None:
    """Print the MLFlow trace analysis."""
    print("\nFailure Patterns:")
    for vname, data in analysis.items():
        failures = data.get("failures_by_type", {})
        if not failures:
            print(f"  {vname}: no failures")
            continue
        parts = []
        for etype, counts in failures.items():
            for metric, count in counts.items():
                parts.append(f"{count} {metric} ({etype})")
        print(f"  {vname}: {', '.join(parts)}")

    print("\nConfidence vs Accuracy:")
    for vname, data in analysis.items():
        avg_c = data.get("avg_conf_correct", 0)
        avg_i = data.get("avg_conf_incorrect", 0)
        calibration = ""
        if avg_i > 0 and avg_c > 0:
            gap = avg_c - avg_i
            if gap > 0.4:
                calibration = " <- best calibrated"
            elif gap > 0.2:
                calibration = " <- well calibrated"
        print(
            f"  {vname}: avg confidence on correct={avg_c:.2f}, "
            f"on incorrect={avg_i:.2f}{calibration}"
        )

    print("\nError Stats:")
    for vname, data in analysis.items():
        errors = data.get("error_count", 0)
        print(f"  {vname}: {errors} errors")

    print("\nLatency (median / p95):")
    for vname, data in analysis.items():
        med = data.get("median_latency_ms", 0) / 1000
        p95 = data.get("p95_latency_ms", 0) / 1000
        print(f"  {vname}: {med:.1f}s / {p95:.1f}s")


# ── Main ──────────────────────────────────────────────────────────────────


async def main() -> None:
    data = json.loads(SNIPPETS_PATH.read_text())
    snippets = data["grounding_test_snippets"]

    total_entities = sum(len(s["entities"]) for s in snippets)
    num_variants = len(EXPERIMENT_VARIANTS)

    print("=" * 67)
    print(
        f"GROUNDING VARIANT EXPERIMENT — {total_entities} entities "
        f"x {num_variants} variants"
    )
    print("=" * 67)

    start = time.monotonic()
    semaphore = asyncio.Semaphore(4)

    # ── Phase 1: Cache ──
    print("\n[Phase 1] Caching TerminologyRouter candidates...")
    cached_candidates = await _cache_candidates(snippets)
    print(f"  Cached {len(cached_candidates)} entity candidate sets")

    print("\n[Phase 1] Caching unit normalization...")
    unit_cache = _cache_units(snippets)
    print(f"  Cached {len(unit_cache)} unit normalizations")

    # ── Phase 2: Run variants ──
    print("\n[Phase 2] Running variants...")
    variant_results: dict[str, dict[str, EntityResult]] = {}
    for variant in EXPERIMENT_VARIANTS:
        variant_results[variant["name"]] = await _run_variant(
            variant, snippets, cached_candidates, semaphore
        )

    elapsed = time.monotonic() - start

    # ── Phase 3: Score ──
    print(f"\n{'=' * 67}")
    print("ENTITY RESULTS")
    print(f"{'=' * 67}\n")

    scores = _score_variants(variant_results, snippets, unit_cache)
    _print_entity_table(scores, snippets)

    print(f"\n{'=' * 67}")
    print("VARIANT SUMMARY")
    print(f"{'=' * 67}\n")
    _print_summary(scores)

    # ── Phase 4: Trace analysis ──
    print(f"\n{'=' * 67}")
    print("MLFLOW TRACE ANALYSIS")
    print(f"{'=' * 67}")

    analysis = _analyze_traces(variant_results, scores, snippets)
    _print_analysis(analysis)

    # ── Phase 5: Recommendation ──
    print(f"\n{'=' * 67}")
    print("RECOMMENDATION")
    print(f"{'=' * 67}\n")

    recommendation = _recommend(scores, analysis)
    print(recommendation)

    print(f"\nTotal time: {elapsed:.1f}s")

    # ── Save results JSON ──
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "variants": [v["name"] for v in EXPERIMENT_VARIANTS],
        "total_entities": total_entities,
        "elapsed_s": round(elapsed, 1),
        "scores": {
            vname: {key: entry for key, entry in entities.items()}
            for vname, entities in scores.items()
        },
        "summary": {
            metric: {
                vname: {"ok": ok, "total": total}
                for vname, (ok, total) in _count_matches(scores, metric).items()
            }
            for metric in ("code", "relation", "value", "unit_ucum", "unit_omop")
        },
        "analysis": {
            vname: {k: v for k, v in data.items() if k != "failures_by_type"}
            | {"failures_by_type": data.get("failures_by_type", {})}
            for vname, data in analysis.items()
        },
        "recommendation": recommendation.split("\n")[0],
    }
    out_path = RESULTS_DIR / "variant_experiment.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
