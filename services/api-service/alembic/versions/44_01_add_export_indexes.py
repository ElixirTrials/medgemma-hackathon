"""Add indexes to optimize export join patterns.

Phase 4: Indexes for CIRCE, FHIR Group, and evaluation SQL exports.

Revision ID: 44_01_export_indexes
Revises: 43_01_unit_value_concept_ids
Create Date: 2026-02-19 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "44_01_export_indexes"
down_revision: Union[str, None] = "43_01_unit_value_concept_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Index definitions: (index_name, table_name, columns)
_INDEXES = [
    (
        "ix_atomic_domain_concept",
        "atomic_criteria",
        ["entity_domain", "omop_concept_id"],
    ),
    (
        "ix_composite_proto_incl",
        "composite_criteria",
        ["protocol_id", "inclusion_exclusion"],
    ),
    (
        "ix_rel_child_criterion",
        "criterion_relationships",
        ["child_criterion_id"],
    ),
    (
        "ix_atomic_crit_incl",
        "atomic_criteria",
        ["criterion_id", "inclusion_exclusion"],
    ),
]


def upgrade() -> None:
    """Add export-optimized indexes (idempotent)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    for index_name, table_name, columns in _INDEXES:
        existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    """Remove export-optimized indexes."""
    for index_name, table_name, _columns in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)
