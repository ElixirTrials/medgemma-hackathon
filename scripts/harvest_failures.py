#!/usr/bin/env python3
"""Harvest hard pipeline failures into test snippets for regression testing.

Queries the database for protocols stuck in extraction_failed/grounding_failed,
entities with zero terminology codes, and entities with missing relation/value.
Uses MLflow traces for context and Gemini to generate golden test snippets.

Usage:
    set -a && source .env && set +a
    uv run python scripts/harvest_failures.py                    # default: last 24h
    uv run python scripts/harvest_failures.py --since-hours 72   # last 3 days
    uv run python scripts/harvest_failures.py --dry-run           # classify only, don't write
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, TypedDict, cast

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import create_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SNIPPETS_PATH = Path(__file__).parent.parent / "tests" / "e2e" / "test_snippets.json"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class HarvestState(TypedDict):
    since_hours: int
    dry_run: bool
    failed_protocols: list[dict[str, Any]]
    failed_entities: list[dict[str, Any]]
    trace_data: list[dict[str, Any]]
    new_extraction_snippets: list[dict[str, Any]]
    new_grounding_snippets: list[dict[str, Any]]
    snippets_added: int


# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------


class ExtractionSnippet(BaseModel):
    """Golden extraction test case."""

    snippet_text: str = Field(description="The original clinical text")
    extracted_criteria: str | None = Field(
        description="The extracted criterion text, or null if not a criterion"
    )
    classification: str = Field(description="One of: inclusion, exclusion, neither")


class GroundingEntity(BaseModel):
    """A single grounded entity in a test case."""

    entity_name: str = Field(description="Preferred term for the entity")
    system: str = Field(
        description="Terminology system: UMLS, SNOMED, RxNorm, ICD10, LOINC, HPO"
    )
    code: str = Field(description="The correct terminology code")
    relation: str = Field(
        description="Relational operator: ==, !=, <, >, <=, >=, contains, etc."
    )
    value: str = Field(description="The constraint value")


class GroundingSnippet(BaseModel):
    """Golden grounding test case."""

    snippet_text: str = Field(description="The original clinical criterion text")
    entities: list[GroundingEntity] = Field(description="Correctly grounded entities")


class FailureClassification(BaseModel):
    """LLM classification + generated snippet for a single failure."""

    failure_type: str = Field(
        description="One of: extraction_incomplete, extraction_erroneous, "
        "grounding_no_code, grounding_no_relation_value"
    )
    extraction_snippet: ExtractionSnippet | None = Field(
        default=None,
        description="Generated extraction test case (for extraction failures)",
    )
    grounding_snippet: GroundingSnippet | None = Field(
        default=None,
        description="Generated grounding test case (for grounding failures)",
    )


# ---------------------------------------------------------------------------
# Node 1: query_failures
# ---------------------------------------------------------------------------


def _get_engine() -> Engine:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is required")
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, connect_args=connect_args, echo=False)


def query_failures(state: HarvestState) -> dict[str, Any]:
    """Query DB for hard pipeline failures."""
    hours = state["since_hours"]
    engine = _get_engine()

    failed_protocols: list[dict[str, Any]] = []
    failed_entities: list[dict[str, Any]] = []

    with engine.connect() as conn:
        # Query 1: Failed protocols
        rows = conn.execute(
            text(
                """
                SELECT p.id, p.title, p.status, p.error_reason, p.metadata_
                FROM protocol p
                WHERE p.status IN ('extraction_failed', 'grounding_failed')
                  AND p.updated_at > now() - make_interval(hours => :hours)
                """
            ),
            {"hours": hours},
        ).fetchall()

        for r in rows:
            failed_protocols.append(
                {
                    "protocol_id": r[0],
                    "title": r[1],
                    "status": r[2],
                    "error_reason": r[3],
                    "metadata": r[4],
                    "source": "protocol_failure",
                }
            )

        # Query 2: Entities with zero codes (hard failures)
        rows = conn.execute(
            text(
                """
                SELECT e.id, e.text, e.entity_type, e.grounding_error,
                       c.text as criterion_text, c.criteria_type, c.conditions,
                       cb.protocol_id
                FROM entity e
                JOIN criteria c ON e.criteria_id = c.id
                JOIN criteriabatch cb ON c.batch_id = cb.id
                WHERE e.grounding_error IS NOT NULL
                  AND e.umls_cui IS NULL AND e.snomed_code IS NULL
                  AND e.rxnorm_code IS NULL AND e.icd10_code IS NULL
                  AND e.loinc_code IS NULL AND e.hpo_code IS NULL
                  AND e.updated_at > now() - make_interval(hours => :hours)
                """
            ),
            {"hours": hours},
        ).fetchall()

        for r in rows:
            failed_entities.append(
                {
                    "entity_id": r[0],
                    "text": r[1],
                    "entity_type": r[2],
                    "grounding_error": r[3],
                    "criterion_text": r[4],
                    "criteria_type": r[5],
                    "conditions": r[6],
                    "protocol_id": r[7],
                    "source": "no_code",
                }
            )

        # Query 3: Entities with code but possibly missing relation/value
        rows = conn.execute(
            text(
                """
                SELECT e.id, e.text, e.entity_type, e.umls_cui, e.snomed_code,
                       c.text as criterion_text, c.criteria_type, c.conditions,
                       cb.protocol_id
                FROM entity e
                JOIN criteria c ON e.criteria_id = c.id
                JOIN criteriabatch cb ON c.batch_id = cb.id
                WHERE (e.umls_cui IS NOT NULL OR e.snomed_code IS NOT NULL
                       OR e.rxnorm_code IS NOT NULL OR e.icd10_code IS NOT NULL
                       OR e.loinc_code IS NOT NULL OR e.hpo_code IS NOT NULL)
                  AND e.updated_at > now() - make_interval(hours => :hours)
                """
            ),
            {"hours": hours},
        ).fetchall()

        for r in rows:
            conditions = r[7]
            if not conditions or not isinstance(conditions, dict):
                continue
            field_mappings = conditions.get("field_mappings", [])
            if not isinstance(field_mappings, list):
                continue

            has_missing = False
            for fm in field_mappings:
                if not isinstance(fm, dict):
                    continue
                rel = fm.get("relation")
                val = fm.get("value")
                # Check for FieldMappingValue-style objects too
                if isinstance(val, dict):
                    val = val.get("raw") or val.get("numeric")
                if not rel or val is None or val == "":
                    has_missing = True
                    break

            if has_missing:
                failed_entities.append(
                    {
                        "entity_id": r[0],
                        "text": r[1],
                        "entity_type": r[2],
                        "umls_cui": r[3],
                        "snomed_code": r[4],
                        "criterion_text": r[5],
                        "criteria_type": r[6],
                        "conditions": conditions,
                        "protocol_id": r[8],
                        "source": "missing_relation_value",
                    }
                )

    logger.info(
        "Found %d failed protocols and %d failed entities",
        len(failed_protocols),
        len(failed_entities),
    )
    return {"failed_protocols": failed_protocols, "failed_entities": failed_entities}


# ---------------------------------------------------------------------------
# Node 2: fetch_traces
# ---------------------------------------------------------------------------


def fetch_traces(state: HarvestState) -> dict[str, Any]:
    """Fetch MLflow traces for each failure to provide LLM context."""
    trace_data: list[dict[str, Any]] = []

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        logger.warning("MLFLOW_TRACKING_URI not set — skipping trace fetch")
        return {"trace_data": trace_data}

    try:
        import mlflow

        client = mlflow.MlflowClient()
    except Exception:
        logger.warning("MLflow client unavailable — skipping trace fetch")
        return {"trace_data": trace_data}

    # Collect unique protocol IDs from both failure lists
    protocol_ids: set[str] = set()
    for p in state["failed_protocols"]:
        protocol_ids.add(p["protocol_id"])
    for e in state["failed_entities"]:
        pid = e.get("protocol_id")
        if pid:
            protocol_ids.add(pid)

    for pid in protocol_ids:
        try:
            traces = client.search_traces(
                filter_string=f"tags.protocol_id = '{pid}'",
                max_results=20,
            )
        except Exception as exc:
            logger.debug("Trace search failed for %s: %s", pid, exc)
            continue

        for t in traces:
            spans_info = []
            if t.data and t.data.spans:
                for span in t.data.spans:
                    spans_info.append(
                        {
                            "name": span.name,
                            "status": str(getattr(span, "status", "UNKNOWN")),
                            "inputs": getattr(span, "inputs", None),
                            "outputs": getattr(span, "outputs", None),
                        }
                    )
            trace_data.append(
                {
                    "protocol_id": pid,
                    "tags": {
                        k: v
                        for k, v in (t.info.tags or {}).items()
                        if not k.startswith("mlflow.")
                    },
                    "spans": spans_info,
                }
            )

    logger.info(
        "Fetched %d trace records across %d protocols",
        len(trace_data),
        len(protocol_ids),
    )
    return {"trace_data": trace_data}


# ---------------------------------------------------------------------------
# Node 3: classify_and_generate
# ---------------------------------------------------------------------------


def _build_failure_prompt(failure: dict[str, Any], traces: list[dict[str, Any]]) -> str:
    """Build a prompt for Gemini to classify and generate a golden test snippet."""
    parts = [
        "Analyze this clinical trial pipeline failure and generate a correct golden test case.\n"
    ]

    if failure.get("source") == "protocol_failure":
        parts.append(f"FAILURE TYPE: Protocol-level {failure['status']}")
        parts.append(f"Protocol title: {failure.get('title', 'N/A')}")
        parts.append(f"Error reason: {failure.get('error_reason', 'N/A')}")
        meta = failure.get("metadata")
        if meta:
            parts.append(f"Metadata: {json.dumps(meta, default=str)[:500]}")
    else:
        parts.append(f"FAILURE TYPE: Entity-level {failure['source']}")
        parts.append(f"Entity text: {failure.get('text', 'N/A')}")
        parts.append(f"Entity type: {failure.get('entity_type', 'N/A')}")
        parts.append(f"Criterion text: {failure.get('criterion_text', 'N/A')}")
        parts.append(f"Criteria type: {failure.get('criteria_type', 'N/A')}")
        if failure.get("grounding_error"):
            parts.append(f"Grounding error: {failure['grounding_error']}")
        if failure.get("conditions"):
            parts.append(
                f"Conditions: {json.dumps(failure['conditions'], default=str)[:500]}"
            )

    # Attach trace context
    pid = failure.get("protocol_id")
    relevant_traces = [t for t in traces if t.get("protocol_id") == pid]
    if relevant_traces:
        parts.append("\nMLFLOW TRACE CONTEXT:")
        for tr in relevant_traces[:3]:  # limit to avoid token explosion
            for span in tr.get("spans", [])[:5]:
                parts.append(f"  Span: {span['name']} status={span['status']}")
                if span.get("inputs"):
                    inp = json.dumps(span["inputs"], default=str)[:200]
                    parts.append(f"    Inputs: {inp}")
                if span.get("outputs"):
                    out = json.dumps(span["outputs"], default=str)[:200]
                    parts.append(f"    Outputs: {out}")

    parts.append(
        "\nINSTRUCTIONS:"
        "\n1. Classify the failure as one of: extraction_incomplete, extraction_erroneous, "
        "grounding_no_code, grounding_no_relation_value"
        "\n2. Generate the CORRECT expected output as a golden test snippet."
        "\n3. For extraction failures: provide snippet_text, extracted_criteria, and classification "
        "(inclusion/exclusion/neither)."
        "\n4. For grounding failures: provide snippet_text and a list of correctly grounded entities "
        "with entity_name, system (UMLS/SNOMED/RxNorm/ICD10/LOINC/HPO), code, relation, and value."
        "\n5. Use your clinical knowledge to determine the correct terminology codes."
    )

    return "\n".join(parts)


def classify_and_generate(state: HarvestState) -> dict[str, Any]:
    """Use Gemini to classify failures and generate golden test snippets."""
    all_failures: list[dict[str, Any]] = []
    for p in state["failed_protocols"]:
        all_failures.append(p)
    for e in state["failed_entities"]:
        all_failures.append(e)

    if not all_failures:
        logger.info("No failures to classify")
        return {"new_extraction_snippets": [], "new_grounding_snippets": []}

    # Load existing snippets for dedup
    existing_texts: set[str] = set()
    if SNIPPETS_PATH.exists():
        existing = json.loads(SNIPPETS_PATH.read_text())
        for s in existing.get("extraction_test_snippets", []):
            existing_texts.add(s.get("snippet_text", ""))
        for s in existing.get("grounding_test_snippets", []):
            existing_texts.add(s.get("snippet_text", ""))

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro")
    structured_llm = llm.with_structured_output(FailureClassification)

    new_extraction: list[dict[str, Any]] = []
    new_grounding: list[dict[str, Any]] = []
    traces = state.get("trace_data", [])

    for i, failure in enumerate(all_failures):
        prompt = _build_failure_prompt(failure, traces)
        logger.info(
            "[%d/%d] Classifying: %s",
            i + 1,
            len(all_failures),
            (failure.get("text") or failure.get("title", ""))[:60],
        )

        try:
            result = cast(FailureClassification, structured_llm.invoke(prompt))
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)
            continue

        if result.extraction_snippet:
            snippet = result.extraction_snippet
            if snippet.snippet_text not in existing_texts:
                new_extraction.append(snippet.model_dump())
                existing_texts.add(snippet.snippet_text)

        if result.grounding_snippet:
            gsnippet = result.grounding_snippet
            if gsnippet.snippet_text not in existing_texts:
                new_grounding.append(gsnippet.model_dump())
                existing_texts.add(gsnippet.snippet_text)

    logger.info(
        "Generated %d extraction + %d grounding new snippets",
        len(new_extraction),
        len(new_grounding),
    )
    return {
        "new_extraction_snippets": new_extraction,
        "new_grounding_snippets": new_grounding,
    }


# ---------------------------------------------------------------------------
# Node 4: save_snippets
# ---------------------------------------------------------------------------


def save_snippets(state: HarvestState) -> dict[str, Any]:
    """Append new snippets to test_snippets.json."""
    new_extraction = state.get("new_extraction_snippets", [])
    new_grounding = state.get("new_grounding_snippets", [])
    total_new = len(new_extraction) + len(new_grounding)

    if total_new == 0:
        logger.info("No new snippets to save")
        return {"snippets_added": 0}

    if state.get("dry_run"):
        print(f"\n{'=' * 60}")
        print("DRY RUN — would add the following snippets:")
        print(f"{'=' * 60}")
        if new_extraction:
            print(f"\nExtraction snippets ({len(new_extraction)}):")
            print(json.dumps(new_extraction, indent=2))
        if new_grounding:
            print(f"\nGrounding snippets ({len(new_grounding)}):")
            print(json.dumps(new_grounding, indent=2))
        return {"snippets_added": 0}

    # Read existing
    if SNIPPETS_PATH.exists():
        data = json.loads(SNIPPETS_PATH.read_text())
    else:
        data = {"extraction_test_snippets": [], "grounding_test_snippets": []}

    data["extraction_test_snippets"].extend(new_extraction)
    data["grounding_test_snippets"].extend(new_grounding)

    SNIPPETS_PATH.write_text(json.dumps(data, indent=2) + "\n")

    print(f"\nSaved {total_new} new snippets to {SNIPPETS_PATH}")
    print(
        f"  Extraction: +{len(new_extraction)} (total: {len(data['extraction_test_snippets'])})"
    )
    print(
        f"  Grounding:  +{len(new_grounding)} (total: {len(data['grounding_test_snippets'])})"
    )

    return {"snippets_added": total_new}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph():
    g = StateGraph(HarvestState)
    g.add_node("query_failures", query_failures)
    g.add_node("fetch_traces", fetch_traces)
    g.add_node("classify_and_generate", classify_and_generate)
    g.add_node("save_snippets", save_snippets)
    g.add_edge(START, "query_failures")
    g.add_edge("query_failures", "fetch_traces")
    g.add_edge("fetch_traces", "classify_and_generate")
    g.add_edge("classify_and_generate", "save_snippets")
    g.add_edge("save_snippets", END)
    return g.compile()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Harvest hard pipeline failures into test snippets"
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Look-back window in hours (default: 24)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify failures but don't write to test_snippets.json",
    )
    args = parser.parse_args()

    print(f"Harvesting failures from the last {args.since_hours} hours")
    if args.dry_run:
        print("(dry-run mode — no files will be modified)")

    graph = build_graph()
    result = graph.invoke(
        {
            "since_hours": args.since_hours,
            "dry_run": args.dry_run,
            "failed_protocols": [],
            "failed_entities": [],
            "trace_data": [],
            "new_extraction_snippets": [],
            "new_grounding_snippets": [],
            "snippets_added": 0,
        }
    )

    total = len(result.get("failed_protocols", [])) + len(
        result.get("failed_entities", [])
    )
    added = result.get("snippets_added", 0)
    print(f"\nDone. Failures found: {total}, snippets added: {added}")


if __name__ == "__main__":
    main()
