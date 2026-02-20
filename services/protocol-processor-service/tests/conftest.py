"""Test configuration for protocol-processor-service tests.

Sets environment variables required by cross-service imports before
any test modules are collected.
"""

import os

# api_service.storage requires DATABASE_URL to be set at import time.
# Provide a fake URL for tests that don't actually connect to a database.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

# Limit grounding to 3 criteria and 5 entities in tests.
# Override with PIPELINE_MAX_CRITERIA=0 to run full pipeline.
os.environ.setdefault("PIPELINE_MAX_CRITERIA", "3")
os.environ.setdefault("PIPELINE_MAX_ENTITIES", "5")
