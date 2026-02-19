"""E2E regression baseline thresholds for pipeline output validation.

These thresholds are intentionally conservative (low) to avoid flaky tests.
They represent the minimum acceptable output from the extraction + grounding
pipeline for each test PDF. The pipeline should easily exceed these numbers
on real clinical trial protocol PDFs.

Once a stable baseline is established from actual pipeline runs, these
thresholds should be tightened to catch regressions more precisely. Update
the values based on observed output counts from several consecutive green
runs.

Usage:
    from tests.e2e.baseline import BASELINES, get_baseline

    baseline = get_baseline("data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf")
    assert criteria_count >= baseline["min_criteria"]
"""

from __future__ import annotations

BASELINES: dict[str, dict[str, int]] = {
    "data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf": {
        "min_criteria": 3,  # At least 3 criteria extracted
        "min_inclusion": 1,  # At least 1 inclusion criterion
        "min_exclusion": 1,  # At least 1 exclusion criterion
        "min_entities": 2,  # At least 2 entities across all criteria
        "min_grounded_entities": 1,  # At least 1 entity with non-zero confidence
    },
}


def get_baseline(pdf_path: str) -> dict[str, int]:
    """Look up baseline thresholds for a test PDF.

    Args:
        pdf_path: Relative path from repo root to the PDF file
            (must match a key in BASELINES exactly).

    Returns:
        Dict with min_criteria, min_inclusion, min_exclusion,
        min_entities, min_grounded_entities.

    Raises:
        KeyError: If no baseline entry exists for the given PDF path.
    """
    if pdf_path not in BASELINES:
        available = ", ".join(sorted(BASELINES.keys()))
        raise KeyError(
            f"No baseline entry for '{pdf_path}'. Available baselines: {available}"
        )
    return BASELINES[pdf_path]
