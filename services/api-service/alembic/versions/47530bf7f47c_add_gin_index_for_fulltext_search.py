"""add_gin_index_for_fulltext_search

Revision ID: 47530bf7f47c
Revises: 6bba3f92fdc1
Create Date: 2026-02-11 20:51:47.753262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47530bf7f47c'
down_revision: Union[str, Sequence[str], None] = '6bba3f92fdc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only create GIN index on PostgreSQL
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_criteria_text_search "
            "ON criteria USING GIN (to_tsvector('english', text))"
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Only drop index on PostgreSQL
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_criteria_text_search")
