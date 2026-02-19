"""Full pipeline E2E tests: upload PDF -> extraction -> grounding -> criteria with entities.

Tests cover:
- E2E-01: Pipeline completes to pending_review status
- E2E-02: Extracted criteria include both inclusion and exclusion types
- E2E-03: Entities are grounded with non-zero confidence and coding references
- E2E-06: Numeric regression baseline thresholds are met

Each test uploads its own PDF (independent, no shared state). The cleanup
fixture in conftest.py is autouse and handles deletion after each test.

Requires:
- Docker Compose stack running (API + PostgreSQL + protocol-processor)
- Real Gemini API access (GOOGLE_API_KEY or ADC configured)
- Test PDF at data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

from .baseline import get_baseline
from .conftest import wait_for_pipeline

# Default test PDF (smallest CRC protocol, ~90K)
_DEFAULT_PDF = "data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf"

_FAILURE_STATUSES = frozenset(
    {"extraction_failed", "grounding_failed", "pipeline_failed", "dead_letter"}
)


# ---------------------------------------------------------------------------
# Shared helpers (module-level, not fixtures)
# ---------------------------------------------------------------------------


def _upload_and_wait(
    upload_test_pdf: Callable[..., str],
    e2e_api_client: httpx.Client,
    pdf_path: str | None = None,
) -> tuple[str, dict]:
    """Upload a PDF and wait for the pipeline to reach a terminal status.

    Args:
        upload_test_pdf: Factory fixture that uploads a PDF and returns protocol_id.
        e2e_api_client: Authenticated httpx client.
        pdf_path: Optional path to a specific PDF. Uses default if None.

    Returns:
        Tuple of (protocol_id, protocol_data dict).

    Raises:
        AssertionError: If pipeline reaches a failure status instead of pending_review.
    """
    protocol_id = upload_test_pdf(pdf_path=pdf_path or _DEFAULT_PDF)
    protocol_data = wait_for_pipeline(e2e_api_client, protocol_id, timeout=180)

    status = protocol_data.get("status", "")
    assert status not in _FAILURE_STATUSES, (
        f"Pipeline failed with status '{status}' for protocol {protocol_id}"
    )
    assert status == "pending_review", (
        f"Expected 'pending_review' but got '{status}' for protocol {protocol_id}"
    )

    return protocol_id, protocol_data


def _fetch_criteria(
    e2e_api_client: httpx.Client,
    protocol_id: str,
) -> list[dict]:
    """Fetch criteria for a protocol by retrieving its first batch.

    Args:
        e2e_api_client: Authenticated httpx client.
        protocol_id: Protocol to fetch criteria for.

    Returns:
        List of criterion dicts (each with entities list).

    Raises:
        AssertionError: If no batches or no criteria found.
    """
    # Get batches for the protocol
    batches_resp = e2e_api_client.get(f"/protocols/{protocol_id}/batches")
    assert batches_resp.status_code == 200, (
        f"Failed to fetch batches ({batches_resp.status_code}): {batches_resp.text}"
    )
    batches = batches_resp.json()
    assert len(batches) > 0, f"No batches found for protocol {protocol_id}"

    batch_id = batches[0]["id"]

    # Get criteria for the first batch
    criteria_resp = e2e_api_client.get(f"/reviews/batches/{batch_id}/criteria")
    assert criteria_resp.status_code == 200, (
        f"Failed to fetch criteria ({criteria_resp.status_code}): {criteria_resp.text}"
    )
    criteria = criteria_resp.json()
    assert len(criteria) > 0, (
        f"No criteria found in batch {batch_id} for protocol {protocol_id}"
    )

    return criteria


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFullPipeline:
    """E2E tests for the full upload-to-criteria-with-entities pipeline."""

    def test_pipeline_completes_successfully(
        self,
        upload_test_pdf: Callable[..., str],
        e2e_api_client: httpx.Client,
    ) -> None:
        """E2E-01: Pipeline reaches pending_review status after uploading a real PDF."""
        _protocol_id, protocol_data = _upload_and_wait(
            upload_test_pdf, e2e_api_client
        )
        assert protocol_data["status"] == "pending_review"

    def test_criteria_have_inclusion_and_exclusion(
        self,
        upload_test_pdf: Callable[..., str],
        e2e_api_client: httpx.Client,
    ) -> None:
        """E2E-02: Extracted criteria include both inclusion and exclusion types."""
        protocol_id, _data = _upload_and_wait(upload_test_pdf, e2e_api_client)
        criteria = _fetch_criteria(e2e_api_client, protocol_id)

        baseline = get_baseline(_DEFAULT_PDF)

        # Collect criteria types
        types = [c["criteria_type"] for c in criteria]
        inclusion_count = sum(1 for t in types if t == "inclusion")
        exclusion_count = sum(1 for t in types if t == "exclusion")

        assert "inclusion" in types, (
            f"No inclusion criteria found. Types present: {set(types)}"
        )
        assert "exclusion" in types, (
            f"No exclusion criteria found. Types present: {set(types)}"
        )
        assert len(criteria) >= baseline["min_criteria"], (
            f"Total criteria ({len(criteria)}) below baseline ({baseline['min_criteria']})"
        )
        assert inclusion_count >= baseline["min_inclusion"], (
            f"Inclusion count ({inclusion_count}) below baseline ({baseline['min_inclusion']})"
        )
        assert exclusion_count >= baseline["min_exclusion"], (
            f"Exclusion count ({exclusion_count}) below baseline ({baseline['min_exclusion']})"
        )

    def test_entities_grounded_with_confidence(
        self,
        upload_test_pdf: Callable[..., str],
        e2e_api_client: httpx.Client,
    ) -> None:
        """E2E-03: Entities are grounded with non-zero confidence and coding refs."""
        protocol_id, _data = _upload_and_wait(upload_test_pdf, e2e_api_client)
        criteria = _fetch_criteria(e2e_api_client, protocol_id)

        baseline = get_baseline(_DEFAULT_PDF)

        # Collect all entities from all criteria
        all_entities = []
        for criterion in criteria:
            all_entities.extend(criterion.get("entities", []))

        assert len(all_entities) >= baseline["min_entities"], (
            f"Total entities ({len(all_entities)}) below baseline ({baseline['min_entities']})"
        )

        # Filter grounded entities (non-null, non-zero confidence)
        grounded = [
            e for e in all_entities
            if e.get("grounding_confidence") is not None
            and e["grounding_confidence"] > 0
        ]
        assert len(grounded) >= baseline["min_grounded_entities"], (
            f"Grounded entities ({len(grounded)}) below baseline "
            f"({baseline['min_grounded_entities']})"
        )

        # At least one grounded entity should have a coding reference
        has_coding_ref = any(
            e.get("umls_cui") is not None or e.get("snomed_code") is not None
            for e in grounded
        )
        assert has_coding_ref, (
            "No grounded entity has a non-null umls_cui or snomed_code"
        )

    def test_regression_baseline(
        self,
        upload_test_pdf: Callable[..., str],
        e2e_api_client: httpx.Client,
    ) -> None:
        """E2E-06: All numeric regression baseline thresholds are met."""
        protocol_id, _data = _upload_and_wait(upload_test_pdf, e2e_api_client)
        criteria = _fetch_criteria(e2e_api_client, protocol_id)

        baseline = get_baseline(_DEFAULT_PDF)

        # Compute actual counts
        types = [c["criteria_type"] for c in criteria]
        inclusion_count = sum(1 for t in types if t == "inclusion")
        exclusion_count = sum(1 for t in types if t == "exclusion")

        all_entities = []
        for criterion in criteria:
            all_entities.extend(criterion.get("entities", []))

        grounded = [
            e for e in all_entities
            if e.get("grounding_confidence") is not None
            and e["grounding_confidence"] > 0
        ]

        # Print actual vs baseline for visibility (pytest -s)
        print(f"\n--- Regression Baseline Report for {_DEFAULT_PDF} ---")
        print(f"  Criteria:          {len(criteria):>4} (baseline: {baseline['min_criteria']})")
        print(f"  Inclusion:         {inclusion_count:>4} (baseline: {baseline['min_inclusion']})")
        print(f"  Exclusion:         {exclusion_count:>4} (baseline: {baseline['min_exclusion']})")
        print(f"  Entities:          {len(all_entities):>4} (baseline: {baseline['min_entities']})")
        print(f"  Grounded entities: {len(grounded):>4} (baseline: {baseline['min_grounded_entities']})")
        print("---")

        # Assert ALL baseline thresholds
        assert len(criteria) >= baseline["min_criteria"], (
            f"Total criteria ({len(criteria)}) below baseline ({baseline['min_criteria']})"
        )
        assert inclusion_count >= baseline["min_inclusion"], (
            f"Inclusion count ({inclusion_count}) below baseline ({baseline['min_inclusion']})"
        )
        assert exclusion_count >= baseline["min_exclusion"], (
            f"Exclusion count ({exclusion_count}) below baseline ({baseline['min_exclusion']})"
        )
        assert len(all_entities) >= baseline["min_entities"], (
            f"Entity count ({len(all_entities)}) below baseline ({baseline['min_entities']})"
        )
        assert len(grounded) >= baseline["min_grounded_entities"], (
            f"Grounded entity count ({len(grounded)}) below baseline "
            f"({baseline['min_grounded_entities']})"
        )
