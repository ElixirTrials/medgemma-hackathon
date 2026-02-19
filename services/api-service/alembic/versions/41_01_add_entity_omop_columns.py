"""Add omop_concept_id and reconciliation_status to Entity.

Revision ID: 41_01_entity_omop_cols
Revises: 40_01_entity_grounding_cols
Create Date: 2026-02-19 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41_01_entity_omop_cols"
down_revision: Union[str, None] = "40_01_entity_grounding_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add omop_concept_id and reconciliation_status columns to entity table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("entity")}

    with op.batch_alter_table("entity") as batch_op:
        if "omop_concept_id" not in existing:
            batch_op.add_column(
                sa.Column("omop_concept_id", sa.String(), nullable=True)
            )
            batch_op.create_index(
                "ix_entity_omop_concept_id", ["omop_concept_id"]
            )
        if "reconciliation_status" not in existing:
            batch_op.add_column(
                sa.Column("reconciliation_status", sa.String(), nullable=True)
            )


def downgrade() -> None:
    """Remove omop_concept_id and reconciliation_status from entity table."""
    with op.batch_alter_table("entity") as batch_op:
        batch_op.drop_index("ix_entity_omop_concept_id")
        batch_op.drop_column("reconciliation_status")
        batch_op.drop_column("omop_concept_id")
