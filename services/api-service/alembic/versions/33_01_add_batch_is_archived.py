"""Add is_archived to CriteriaBatch.

Revision ID: 33_01_add_batch_is_archived
Revises: 07_01_protocol_status_enum
Create Date: 2026-02-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "33_01_add_batch_is_archived"
down_revision: Union[str, None] = "07_01_protocol_status_enum"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_archived column to criteriabatch table.

    Uses batch_alter_table for SQLite compatibility (render_as_batch=True in
    env.py handles both SQLite and PostgreSQL). The batch approach avoids
    SQLite's limited ALTER TABLE support.

    On PostgreSQL: renders as standard ADD COLUMN + NOT NULL + index.
    On SQLite: creates a new temp table with the column, copies data, drops old.

    The server_default=sa.false() ensures existing rows get is_archived=False,
    satisfying the NOT NULL constraint without a separate backfill step.
    """
    with op.batch_alter_table("criteriabatch") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_archived",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_index(
            "ix_criteriabatch_is_archived",
            ["is_archived"],
            unique=False,
        )


def downgrade() -> None:
    """Remove is_archived column from criteriabatch table."""
    with op.batch_alter_table("criteriabatch") as batch_op:
        batch_op.drop_index("ix_criteriabatch_is_archived")
        batch_op.drop_column("is_archived")
