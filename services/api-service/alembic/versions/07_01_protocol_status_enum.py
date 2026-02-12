"""add error_reason to protocol

Revision ID: 07_01_protocol_status_enum
Revises: 6bba3f92fdc1
Create Date: 2026-02-12 07:16:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07_01_protocol_status_enum"
down_revision: Union[str, None] = "47530bf7f47c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_reason column to protocol table."""
    op.add_column("protocol", sa.Column("error_reason", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove error_reason column from protocol table."""
    op.drop_column("protocol", "error_reason")
