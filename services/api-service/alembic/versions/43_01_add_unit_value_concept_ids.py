"""Add unit_concept_id and value_concept_id to atomic_criteria.

Phase 3 (Gap 7): UCUM unit normalization columns for OMOP CDM joins.

Revision ID: 43_01_unit_value_concept_ids
Revises: 42_01_expression_tree
Create Date: 2026-02-19 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "43_01_unit_value_concept_ids"
down_revision: Union[str, None] = "42_01_expression_tree"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unit_concept_id and value_concept_id columns to atomic_criteria."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("atomic_criteria")}

    with op.batch_alter_table("atomic_criteria") as batch_op:
        if "unit_concept_id" not in existing_cols:
            batch_op.add_column(
                sa.Column("unit_concept_id", sa.Integer(), nullable=True)
            )
        if "value_concept_id" not in existing_cols:
            batch_op.add_column(
                sa.Column("value_concept_id", sa.Integer(), nullable=True)
            )


def downgrade() -> None:
    """Remove unit_concept_id and value_concept_id from atomic_criteria."""
    with op.batch_alter_table("atomic_criteria") as batch_op:
        batch_op.drop_column("value_concept_id")
        batch_op.drop_column("unit_concept_id")
