"""Add grounding_system and grounding_error to Entity.

Revision ID: 40_01_entity_grounding_cols
Revises: 33_01_add_batch_is_archived
Create Date: 2026-02-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "40_01_entity_grounding_cols"
down_revision: Union[str, None] = "33_01_add_batch_is_archived"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add grounding_system and grounding_error columns to entity table.

    Uses IF NOT EXISTS guard for PostgreSQL since these columns may have been
    added outside of Alembic (e.g., by a Docker container startup script).
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("entity")}

    with op.batch_alter_table("entity") as batch_op:
        if "grounding_system" not in existing:
            batch_op.add_column(
                sa.Column("grounding_system", sa.String(), nullable=True)
            )
        if "grounding_error" not in existing:
            batch_op.add_column(
                sa.Column("grounding_error", sa.String(), nullable=True)
            )


def downgrade() -> None:
    """Remove grounding_system and grounding_error from entity table."""
    with op.batch_alter_table("entity") as batch_op:
        batch_op.drop_column("grounding_error")
        batch_op.drop_column("grounding_system")
