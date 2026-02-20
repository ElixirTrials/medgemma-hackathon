#!/usr/bin/env python3
"""E2E smoketest: upload a PDF through the API and wait for pipeline completion.

Usage:
    uv run python scripts/e2e_smoketest.py [path/to/test.pdf]
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

import httpx
import jwt

API_URL = "http://localhost:8000"
JWT_SECRET = "dev-secret-key-change-in-production"
DEFAULT_PDF = "data/protocols/clinicaltrials/Prot_000-f1ed5129.pdf"
TIMEOUT_SECONDS = 600
POLL_INTERVAL = 5

TERMINAL_STATUSES = frozenset(
    {
        "pending_review",
        "complete",
        "extraction_failed",
        "grounding_failed",
        "pipeline_failed",
        "dead_letter",
    }
)


def make_client() -> httpx.Client:
    token = jwt.encode(
        {"sub": "smoketest-user", "email": "smoketest@test.com", "name": "Smoketest"},
        JWT_SECRET,
        algorithm="HS256",
    )
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    )


def upload_pdf(client: httpx.Client, pdf_path: Path) -> str:
    """Upload a PDF through the 3-step API flow. Returns protocol_id."""
    pdf_bytes = pdf_path.read_bytes()
    print(f"  PDF size: {len(pdf_bytes):,} bytes")

    # Step 1: Request upload URL
    resp = client.post(
        "/protocols/upload",
        json={
            "filename": pdf_path.name,
            "content_type": "application/pdf",
            "file_size_bytes": len(pdf_bytes),
        },
    )
    assert resp.status_code == 200, (
        f"Upload request failed ({resp.status_code}): {resp.text}"
    )
    data = resp.json()
    protocol_id = data["protocol_id"]
    upload_url = data["upload_url"]
    print(f"  Protocol ID: {protocol_id}")
    print(f"  Upload URL: {upload_url}")

    # Step 2: PUT the PDF bytes
    put_resp = httpx.put(
        upload_url,
        content=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
        timeout=30.0,
    )
    assert put_resp.status_code == 200, (
        f"PUT failed ({put_resp.status_code}): {put_resp.text}"
    )
    print("  PUT upload: OK")

    # Step 3: Confirm upload
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    confirm_resp = client.post(
        f"/protocols/{protocol_id}/confirm-upload",
        json={"pdf_bytes_base64": pdf_b64},
    )
    assert confirm_resp.status_code == 200, (
        f"Confirm failed ({confirm_resp.status_code}): {confirm_resp.text}"
    )
    print("  Confirm upload: OK")
    return protocol_id


def wait_for_pipeline(client: httpx.Client, protocol_id: str) -> dict:
    """Poll until the pipeline reaches a terminal status."""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_status = ""
    while True:
        resp = client.get(f"/protocols/{protocol_id}")
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "unknown")

        if status != last_status:
            elapsed = TIMEOUT_SECONDS - (deadline - time.monotonic())
            print(f"  [{elapsed:5.0f}s] Status: {status}")
            last_status = status

        if status in TERMINAL_STATUSES:
            return data

        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Protocol {protocol_id} still '{status}' after {TIMEOUT_SECONDS}s"
            )
        time.sleep(POLL_INTERVAL)


def fetch_criteria(client: httpx.Client, protocol_id: str) -> list[dict]:
    """Fetch criteria from the first batch."""
    batches_resp = client.get(f"/protocols/{protocol_id}/batches")
    batches_resp.raise_for_status()
    batches = batches_resp.json()
    if not batches:
        print("  WARNING: No batches found")
        return []

    batch_id = batches[0]["id"]
    criteria_resp = client.get(f"/reviews/batches/{batch_id}/criteria")
    criteria_resp.raise_for_status()
    return criteria_resp.json()


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pdf_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF
    pdf_path = Path(pdf_arg)
    if not pdf_path.is_absolute():
        pdf_path = repo_root / pdf_path

    assert pdf_path.exists(), f"PDF not found: {pdf_path}"

    print("=" * 60)
    print("E2E Pipeline Smoketest")
    print("=" * 60)

    client = make_client()

    # Health check
    try:
        health = client.get("/health")
        assert health.status_code == 200
        print("\n[1/4] API health check: OK")
    except Exception as e:
        print(f"\nERROR: API not reachable at {API_URL}: {e}")
        sys.exit(1)

    # Upload
    print(f"\n[2/4] Uploading PDF: {pdf_path.name}")
    start = time.monotonic()
    protocol_id = upload_pdf(client, pdf_path)

    # Wait for pipeline
    print(f"\n[3/4] Waiting for pipeline (timeout={TIMEOUT_SECONDS}s)...")
    try:
        result = wait_for_pipeline(client, protocol_id)
    except TimeoutError as e:
        print(f"\n  TIMEOUT: {e}")
        sys.exit(1)

    elapsed = time.monotonic() - start
    status = result.get("status", "unknown")
    print(f"\n  Pipeline finished in {elapsed:.1f}s with status: {status}")

    if status in {
        "extraction_failed",
        "grounding_failed",
        "pipeline_failed",
        "dead_letter",
    }:
        print(f"  ERROR REASON: {result.get('error_reason', 'unknown')}")
        sys.exit(1)

    # Fetch and report criteria
    print("\n[4/4] Fetching criteria...")
    criteria = fetch_criteria(client, protocol_id)
    if not criteria:
        print("  No criteria returned!")
        sys.exit(1)

    types = [c["criteria_type"] for c in criteria]
    inclusion_count = sum(1 for t in types if t == "inclusion")
    exclusion_count = sum(1 for t in types if t == "exclusion")

    all_entities = []
    for c in criteria:
        all_entities.extend(c.get("entities", []))

    grounded = [
        entity
        for entity in all_entities
        if entity.get("grounding_confidence") is not None
        and entity["grounding_confidence"] > 0
    ]

    print("\n  --- Results ---")
    print(f"  Total criteria:    {len(criteria)}")
    print(f"  Inclusion:         {inclusion_count}")
    print(f"  Exclusion:         {exclusion_count}")
    print(f"  Total entities:    {len(all_entities)}")
    print(f"  Grounded entities: {len(grounded)}")
    print(f"  Pipeline time:     {elapsed:.1f}s")

    # Show a few sample entities
    if grounded:
        print("\n  --- Sample Grounded Entities (up to 5) ---")
        for entity in grounded[:5]:
            print(f"    {entity.get('text', '?')[:60]}")
            print(
                "      type="
                f"{entity.get('entity_type')} "
                f"confidence={entity.get('grounding_confidence')}"
            )
            print(
                f"      snomed={entity.get('snomed_code')} "
                f"umls={entity.get('umls_cui')}"
            )

    print(f"\n{'=' * 60}")
    print(
        "SMOKETEST PASSED"
        if status == "pending_review"
        else f"SMOKETEST RESULT: {status}"
    )
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    main()
