r"""Clear all uploaded protocols and extracted criteria from the database.

Deletes rows in FK-safe order: review, entity, criteria, criteriabatch, protocol,
then auditlog and outboxevent. Requires DATABASE_URL in the environment.

Run from repo root with .env loaded, e.g.:
  set -a && source .env && set +a && uv run --project services/api-service \
    python services/api-service/scripts/clear_protocols_and_criteria.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

# Add api-service src to path so api_service and shared are importable
_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_src))

from shared.models import (  # noqa: E402
    AuditLog,
    Criteria,
    CriteriaBatch,
    Entity,
    OutboxEvent,
    Protocol,
    Review,
)

from api_service.storage import engine  # noqa: E402


def clear_protocols_and_criteria() -> None:
    """Delete all protocol-related data in FK-safe order."""
    with Session(engine) as session:
        session.execute(delete(Review))
        session.execute(delete(Entity))
        session.execute(delete(Criteria))
        session.execute(delete(CriteriaBatch))
        session.execute(delete(Protocol))
        session.execute(delete(AuditLog))
        session.execute(delete(OutboxEvent))
        session.commit()
    print(
        "Cleared: review, entity, criteria, criteriabatch, protocol, "
        "auditlog, outboxevent."
    )


if __name__ == "__main__":
    try:
        clear_protocols_and_criteria()
    except OperationalError as e:
        print(
            "Database connection failed. Is PostgreSQL running? "
            "Start it with: make run-infra",
            file=sys.stderr,
        )
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
