"""Add unit_ucum_code to atomic_criteria.

Stores the UCUM code returned by normalize_unit() that was previously
discarded. Enables correct FHIR Quantity coding in exports.

Revision ID: 46_01_unit_ucum_code
Revises: 45_01_normalize_field_mappings
Create Date: 2026-02-24 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "46_01_unit_ucum_code"
down_revision: Union[str, None] = "45_01_normalize_field_mappings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unit_ucum_code column to atomic_criteria."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("atomic_criteria")}

    if "unit_ucum_code" not in existing_cols:
        with op.batch_alter_table("atomic_criteria") as batch_op:
            batch_op.add_column(sa.Column("unit_ucum_code", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove unit_ucum_code from atomic_criteria."""
    with op.batch_alter_table("atomic_criteria") as batch_op:
        batch_op.drop_column("unit_ucum_code")
