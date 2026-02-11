"""Add user model.

Revision ID: 6bba3f92fdc1
Revises: 91004fffe85d
Create Date: 2026-02-11 20:45:04.869672

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bba3f92fdc1"
down_revision: Union[str, Sequence[str], None] = "91004fffe85d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user",
        sa.Column(
            "id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "picture_url",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_email"), ["email"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_email"))

    op.drop_table("user")
