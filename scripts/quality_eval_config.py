"""Configuration for the quality evaluation script."""

from __future__ import annotations

import os

# PDF paths relative to repository root
SAMPLE_PDFS: list[str] = [
    "data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf",
    "data/protocols/crc_protocols/clinicaltrials/Prot_000-f1ed5129.pdf",
]

# API URL — override via QUALITY_EVAL_API_URL env var
API_URL: str = os.getenv("QUALITY_EVAL_API_URL", "http://localhost:8000")

# Report output directory (relative to repo root)
REPORT_OUTPUT_DIR: str = "reports"

# Maximum seconds to wait for pipeline completion per PDF
PIPELINE_TIMEOUT: int = 300

# JWT secret for authenticating API requests
JWT_SECRET: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
