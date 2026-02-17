#!/usr/bin/env python3
"""Quality evaluation script for the unified pipeline.

Uploads sample PDFs through the running Docker Compose stack, waits for
pipeline completion, queries results via the API, computes statistics,
and generates a structured markdown report.

Usage:
    uv run python scripts/quality_eval.py              # Upload + evaluate
    uv run python scripts/quality_eval.py --fresh      # Force re-upload
    uv run python scripts/quality_eval.py --skip-upload # Use existing data
    uv run python scripts/quality_eval.py --protocol-ids id1,id2
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import httpx
import jwt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Allow running as `uv run python scripts/quality_eval.py` from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from quality_eval_config import (  # noqa: E402
    API_URL,
    JWT_SECRET,
    PIPELINE_TIMEOUT,
    REPORT_OUTPUT_DIR,
    SAMPLE_PDFS,
)

# Terminal statuses (same as tests/e2e/conftest.py)
_TERMINAL_STATUSES = frozenset(
    {
        "pending_review",
        "complete",
        "extraction_failed",
        "grounding_failed",
        "pipeline_failed",
        "dead_letter",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client() -> httpx.Client:
    """Create an authenticated httpx client with a JWT bearer token."""
    token = jwt.encode(
        {"sub": "quality-eval", "email": "eval@system.local", "name": "Quality Eval"},
        JWT_SECRET,
        algorithm="HS256",
    )
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    )


def _wait_for_pipeline(
    client: httpx.Client,
    protocol_id: str,
    timeout: int = PIPELINE_TIMEOUT,
    poll_interval: int = 5,
) -> dict:
    """Poll protocol status until it reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while True:
        resp = client.get(f"/protocols/{protocol_id}")
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "")
        if status in _TERMINAL_STATUSES:
            return data

        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Protocol {protocol_id} still in '{status}' after {timeout}s"
            )

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Step 1: Upload and process PDFs
# ---------------------------------------------------------------------------


def upload_pdf(client: httpx.Client, pdf_path: str) -> str:
    """Upload a single PDF through the three-step flow. Returns protocol_id."""
    path = _REPO_ROOT / pdf_path
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pdf_bytes = path.read_bytes()

    # Step 1: Request upload URL
    resp = client.post(
        "/protocols/upload",
        json={
            "filename": path.name,
            "content_type": "application/pdf",
            "file_size_bytes": len(pdf_bytes),
        },
    )
    resp.raise_for_status()
    data = resp.json()
    protocol_id = data["protocol_id"]
    upload_url = data["upload_url"]

    # Step 2: PUT the PDF bytes to the upload URL
    put_resp = httpx.put(
        upload_url,
        content=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
        timeout=30.0,
    )
    put_resp.raise_for_status()

    # Step 3: Confirm upload with base64 PDF
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    confirm_resp = client.post(
        f"/protocols/{protocol_id}/confirm-upload",
        json={"pdf_bytes_base64": pdf_b64},
    )
    confirm_resp.raise_for_status()

    return protocol_id


def upload_and_process(
    client: httpx.Client, fresh: bool = False
) -> list[dict]:
    """Upload sample PDFs and wait for pipeline completion.

    Returns list of dicts with protocol_id, status, and title for each PDF.
    """
    results: list[dict] = []

    for pdf_path in SAMPLE_PDFS:
        pdf_name = Path(pdf_path).name
        print(f"  [{pdf_name}] Uploading...")

        try:
            protocol_id = upload_pdf(client, pdf_path)
            print(f"  [{pdf_name}] protocol_id={protocol_id}, waiting for pipeline...")

            final = _wait_for_pipeline(client, protocol_id)
            status = final.get("status", "unknown")
            title = final.get("title", pdf_name)
            print(f"  [{pdf_name}] Pipeline finished: status={status}")

            results.append(
                {
                    "protocol_id": protocol_id,
                    "status": status,
                    "title": title,
                    "pdf_path": pdf_path,
                }
            )
        except Exception as exc:
            print(f"  [{pdf_name}] ERROR: {exc}")
            results.append(
                {
                    "protocol_id": None,
                    "status": "error",
                    "title": pdf_name,
                    "pdf_path": pdf_path,
                    "error": str(exc),
                }
            )

    return results


# ---------------------------------------------------------------------------
# Step 2: Collect results via API
# ---------------------------------------------------------------------------


def collect_criteria(
    client: httpx.Client, protocol_id: str
) -> list[dict]:
    """Fetch all criteria + entities for a protocol via the API."""
    # Get batches for the protocol
    resp = client.get(f"/protocols/{protocol_id}/batches")
    resp.raise_for_status()
    batches = resp.json()

    if isinstance(batches, dict):
        # Paginated response
        batches = batches.get("items", [])

    all_criteria: list[dict] = []
    for batch in batches:
        batch_id = batch["id"]
        cr_resp = client.get(f"/reviews/batches/{batch_id}/criteria")
        cr_resp.raise_for_status()
        criteria_list = cr_resp.json()
        for criterion in criteria_list:
            criterion["_batch_id"] = batch_id
            criterion["_protocol_id"] = protocol_id
        all_criteria.extend(criteria_list)

    return all_criteria


# ---------------------------------------------------------------------------
# Step 3: Compute statistics
# ---------------------------------------------------------------------------


def _extract_entities(criteria_list: list[dict]) -> list[dict]:
    """Flatten entities from a criteria list."""
    entities: list[dict] = []
    for criterion in criteria_list:
        entities.extend(criterion.get("entities", []))
    return entities


def compute_per_protocol_stats(
    protocol_id: str, criteria_list: list[dict]
) -> dict:
    """Compute per-protocol statistics."""
    entities = _extract_entities(criteria_list)

    inclusion_count = sum(
        1 for c in criteria_list if c.get("criteria_type") == "inclusion"
    )
    exclusion_count = sum(
        1 for c in criteria_list if c.get("criteria_type") == "exclusion"
    )

    cui_count = sum(1 for e in entities if e.get("umls_cui"))
    total_entities = len(entities)
    cui_rate = cui_count / total_entities if total_entities > 0 else 0.0

    method_counter: Counter = Counter()
    for e in entities:
        method = e.get("grounding_method") or "none"
        method_counter[method] += 1

    return {
        "protocol_id": protocol_id,
        "criteria_count": len(criteria_list),
        "inclusion_count": inclusion_count,
        "exclusion_count": exclusion_count,
        "entity_count": total_entities,
        "cui_rate": cui_rate,
        "grounding_method_distribution": dict(method_counter),
    }


def compute_aggregate_stats(all_entities: list[dict]) -> dict:
    """Compute aggregate statistics across all entities."""
    confidences = [
        e["grounding_confidence"]
        for e in all_entities
        if e.get("grounding_confidence") is not None
    ]

    total = len(all_entities)
    cui_count = sum(1 for e in all_entities if e.get("umls_cui"))

    entity_type_counter: Counter = Counter()
    for e in all_entities:
        entity_type_counter[e.get("entity_type", "unknown")] += 1

    return {
        "mean_confidence": mean(confidences) if confidences else 0.0,
        "median_confidence": median(confidences) if confidences else 0.0,
        "overall_cui_rate": cui_count / total if total > 0 else 0.0,
        "entity_type_distribution": dict(entity_type_counter),
        "total_entities": total,
    }


def compute_confidence_distribution(all_entities: list[dict]) -> dict:
    """Compute confidence distribution across buckets."""
    buckets = {
        "null/zero": 0,
        "0-0.5": 0,
        "0.5-0.7": 0,
        "0.7-0.9": 0,
        "0.9-1.0": 0,
    }

    for e in all_entities:
        conf = e.get("grounding_confidence")
        if conf is None or conf == 0:
            buckets["null/zero"] += 1
        elif conf < 0.5:
            buckets["0-0.5"] += 1
        elif conf < 0.7:
            buckets["0.5-0.7"] += 1
        elif conf < 0.9:
            buckets["0.7-0.9"] += 1
        else:
            buckets["0.9-1.0"] += 1

    total = len(all_entities)
    result: dict = {}
    for label, count in buckets.items():
        pct = (count / total * 100) if total > 0 else 0.0
        result[label] = {"count": count, "percentage": round(pct, 1)}

    return result


def compute_terminology_success(all_entities: list[dict]) -> dict:
    """Compute per-terminology-system grounding success rates."""
    total = len(all_entities)

    systems = {
        "UMLS": "umls_cui",
        "SNOMED": "snomed_code",
        "RxNorm": "rxnorm_code",
        "ICD-10": "icd10_code",
        "LOINC": "loinc_code",
        "HPO": "hpo_code",
    }

    result: dict = {}
    for system_name, field in systems.items():
        count = sum(1 for e in all_entities if e.get(field))
        rate = count / total if total > 0 else 0.0
        result[system_name] = {"count": count, "rate": round(rate * 100, 1)}

    return result


# ---------------------------------------------------------------------------
# Step 4: Generate markdown report
# ---------------------------------------------------------------------------


def generate_report(
    protocol_results: list[dict],
    per_protocol_stats: list[dict],
    aggregate: dict,
    confidence_dist: dict,
    terminology: dict,
    total_criteria: int,
) -> str:
    """Generate the markdown report content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    pdf_count = len(protocol_results)

    lines: list[str] = []
    lines.append("# Quality Evaluation Report")
    lines.append(f"Generated: {now}")
    lines.append(
        "Pipeline: unified 5-node LangGraph (ingest->extract->parse->ground->persist)"
    )
    lines.append(f"PDFs evaluated: {pdf_count}")
    lines.append("")

    # --- Per-Protocol Statistics ---
    lines.append("## Per-Protocol Statistics")
    lines.append("")
    lines.append(
        "| Protocol | Criteria | Inc | Exc | Entities | CUI Rate | Status |"
    )
    lines.append(
        "|----------|----------|-----|-----|----------|----------|--------|"
    )

    for pr, ps in zip(protocol_results, per_protocol_stats):
        title = pr.get("title", "Unknown")[:40]
        status = pr.get("status", "unknown")
        cui_pct = f"{ps['cui_rate'] * 100:.1f}%"
        lines.append(
            f"| {title} | {ps['criteria_count']} | {ps['inclusion_count']} "
            f"| {ps['exclusion_count']} | {ps['entity_count']} | {cui_pct} "
            f"| {status} |"
        )

    lines.append("")

    # --- Grounding Method Distribution ---
    lines.append("### Grounding Method Distribution")
    lines.append("")

    # Collect all methods across protocols
    all_methods: set[str] = set()
    for ps in per_protocol_stats:
        all_methods.update(ps["grounding_method_distribution"].keys())
    sorted_methods = sorted(all_methods)

    if sorted_methods:
        header = "| Protocol | " + " | ".join(sorted_methods) + " |"
        sep = "|----------" + "".join("|---------" for _ in sorted_methods) + "|"
        lines.append(header)
        lines.append(sep)

        for pr, ps in zip(protocol_results, per_protocol_stats):
            title = pr.get("title", "Unknown")[:40]
            dist = ps["grounding_method_distribution"]
            values = " | ".join(str(dist.get(m, 0)) for m in sorted_methods)
            lines.append(f"| {title} | {values} |")
    else:
        lines.append("No grounding methods recorded.")

    lines.append("")

    # --- Aggregate Statistics ---
    lines.append("## Aggregate Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total criteria | {total_criteria} |")
    lines.append(f"| Total entities | {aggregate['total_entities']} |")
    lines.append(f"| Mean confidence | {aggregate['mean_confidence']:.3f} |")
    lines.append(f"| Median confidence | {aggregate['median_confidence']:.3f} |")
    lines.append(
        f"| Overall CUI rate | {aggregate['overall_cui_rate'] * 100:.1f}% |"
    )
    lines.append("")

    # --- Entity Type Distribution ---
    lines.append("### Entity Type Distribution")
    lines.append("")
    lines.append("| Type | Count | Percentage |")
    lines.append("|------|-------|------------|")

    total_ent = aggregate["total_entities"]
    for etype, count in sorted(
        aggregate["entity_type_distribution"].items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        pct = (count / total_ent * 100) if total_ent > 0 else 0.0
        lines.append(f"| {etype} | {count} | {pct:.1f}% |")

    lines.append("")

    # --- Confidence Distribution ---
    lines.append("## Confidence Distribution")
    lines.append("")
    lines.append("| Bucket | Count | Percentage |")
    lines.append("|--------|-------|------------|")

    for bucket_name in ["null/zero", "0-0.5", "0.5-0.7", "0.7-0.9", "0.9-1.0"]:
        info = confidence_dist.get(bucket_name, {"count": 0, "percentage": 0.0})
        lines.append(f"| {bucket_name} | {info['count']} | {info['percentage']}% |")

    lines.append("")

    # --- Per-Terminology Grounding Success ---
    lines.append("## Per-Terminology Grounding Success")
    lines.append("")
    lines.append("| System | Entities with Code | Rate |")
    lines.append("|--------|--------------------|------|")

    for system_name in ["UMLS", "SNOMED", "RxNorm", "ICD-10", "LOINC", "HPO"]:
        info = terminology.get(system_name, {"count": 0, "rate": 0.0})
        lines.append(f"| {system_name} | {info['count']} | {info['rate']}% |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the quality evaluation."""
    parser = argparse.ArgumentParser(
        description="Quality evaluation of the unified pipeline"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Force re-upload of PDFs even if protocols already exist",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip PDF upload; use existing protocol data from the API",
    )
    parser.add_argument(
        "--protocol-ids",
        type=str,
        default=None,
        help="Comma-separated protocol IDs to evaluate (use with --skip-upload)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Quality Evaluation - Unified Pipeline")
    print(f"API: {API_URL}")
    print("=" * 60)

    client = _build_client()

    # --- Step 1: Get protocol IDs ---
    protocol_results: list[dict] = []

    if args.skip_upload:
        if args.protocol_ids:
            ids = [pid.strip() for pid in args.protocol_ids.split(",")]
        else:
            # Try to list existing protocols
            print("\nFetching existing protocols from API...")
            resp = client.get("/protocols")
            resp.raise_for_status()
            data = resp.json()
            protocols = data if isinstance(data, list) else data.get("items", [])
            ids = [p["id"] for p in protocols[:5]]  # Limit to 5

        for pid in ids:
            resp = client.get(f"/protocols/{pid}")
            resp.raise_for_status()
            pdata = resp.json()
            protocol_results.append(
                {
                    "protocol_id": pid,
                    "status": pdata.get("status", "unknown"),
                    "title": pdata.get("title", pid),
                    "pdf_path": "existing",
                }
            )
        print(f"  Found {len(protocol_results)} protocol(s)")
    else:
        print("\nStep 1: Uploading and processing PDFs...")
        protocol_results = upload_and_process(client, fresh=args.fresh)

    # Filter to successfully processed protocols
    successful = [
        r
        for r in protocol_results
        if r.get("protocol_id") and r.get("status") != "error"
    ]

    if not successful:
        print("\nERROR: No protocols were successfully processed.")
        sys.exit(1)

    # --- Step 2: Collect results ---
    print("\nStep 2: Collecting criteria and entities...")
    all_criteria_by_protocol: dict[str, list[dict]] = {}
    for pr in successful:
        pid = pr["protocol_id"]
        print(f"  [{pr['title'][:30]}] Fetching criteria...")
        criteria = collect_criteria(client, pid)
        all_criteria_by_protocol[pid] = criteria
        print(f"  [{pr['title'][:30]}] {len(criteria)} criteria found")

    # --- Step 3: Compute statistics ---
    print("\nStep 3: Computing statistics...")

    per_protocol_stats: list[dict] = []
    all_entities: list[dict] = []
    total_criteria = 0

    for pr in successful:
        pid = pr["protocol_id"]
        criteria = all_criteria_by_protocol.get(pid, [])
        total_criteria += len(criteria)
        stats = compute_per_protocol_stats(pid, criteria)
        per_protocol_stats.append(stats)
        all_entities.extend(_extract_entities(criteria))

    aggregate = compute_aggregate_stats(all_entities)
    confidence_dist = compute_confidence_distribution(all_entities)
    terminology = compute_terminology_success(all_entities)

    # --- Step 4: Generate report ---
    print("\nStep 4: Generating report...")

    report_content = generate_report(
        protocol_results=successful,
        per_protocol_stats=per_protocol_stats,
        aggregate=aggregate,
        confidence_dist=confidence_dist,
        terminology=terminology,
        total_criteria=total_criteria,
    )

    output_dir = _REPO_ROOT / REPORT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "quality_eval.md"
    report_path.write_text(report_content)

    print(f"\nReport written to: {report_path}")
    print("=" * 60)

    # Print summary to stdout
    print(f"\nSummary: {total_criteria} criteria, {len(all_entities)} entities")
    print(f"  CUI rate: {aggregate['overall_cui_rate'] * 100:.1f}%")
    if aggregate["mean_confidence"] > 0:
        print(f"  Mean confidence: {aggregate['mean_confidence']:.3f}")
    print("Done.")

    client.close()


if __name__ == "__main__":
    main()
