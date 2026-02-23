"""Normalize field_mappings in criteria.conditions to match frontend schema.

Wraps flat string values into typed objects, renames entity_concept_id/
entity_concept_system to entity_code/entity_system, and normalizes
relation operators (has->contains, is->=, not->not_contains).

Revision ID: 45_01_normalize_field_mappings
Revises: 44_01_export_indexes
Create Date: 2026-02-23 00:00:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45_01_normalize_field_mappings"
down_revision: Union[str, None] = "44_01_export_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Legacy relation operators that need normalization
_RELATION_MAP = {
    "has": "contains",
    "is": "=",
    "not": "not_contains",
    "==": "=",
    "range": "within",
}


def _normalize_mapping(mapping: dict) -> dict:
    """Normalize a single field mapping dict (idempotent)."""
    result = dict(mapping)

    # Rename entity_concept_id -> entity_code (if not already renamed)
    if "entity_concept_id" in result and "entity_code" not in result:
        result["entity_code"] = result.pop("entity_concept_id")
    elif "entity_concept_id" in result:
        del result["entity_concept_id"]

    # Rename entity_concept_system -> entity_system (if not already renamed)
    if "entity_concept_system" in result and "entity_system" not in result:
        result["entity_system"] = result.pop("entity_concept_system")
    elif "entity_concept_system" in result:
        del result["entity_concept_system"]

    # Normalize relation
    rel = result.get("relation", "")
    if isinstance(rel, str) and rel in _RELATION_MAP:
        result["relation"] = _RELATION_MAP[rel]

    # Wrap flat value into typed object (idempotent: skip if already dict)
    value = result.get("value")
    if not isinstance(value, dict):
        unit = result.pop("unit", None) or ""
        result["value"] = {
            "type": "standard",
            "value": str(value) if value is not None else "",
            "unit": str(unit),
        }

    return result


def upgrade() -> None:
    """Normalize existing field_mappings in criteria.conditions."""
    conn = op.get_bind()

    rows = conn.execute(
        sa.text(
            "SELECT id, conditions FROM criteria "
            "WHERE conditions IS NOT NULL "
            "AND conditions::text LIKE '%field_mappings%'"
        )
    ).fetchall()

    for row in rows:
        row_id = row[0]
        conditions = row[1]
        if isinstance(conditions, str):
            conditions = json.loads(conditions)

        field_mappings = conditions.get("field_mappings")
        if not isinstance(field_mappings, list):
            continue

        normalized = [_normalize_mapping(m) for m in field_mappings]
        conditions["field_mappings"] = normalized

        conn.execute(
            sa.text("UPDATE criteria SET conditions = :cond WHERE id = :id"),
            {"cond": json.dumps(conditions), "id": row_id},
        )


def downgrade() -> None:
    """No-op: cannot reconstruct original flat format reliably."""
    pass
