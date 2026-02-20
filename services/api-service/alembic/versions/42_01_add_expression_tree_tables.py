"""Add expression tree tables and structured_criterion column.

Phase 2: atomic_criteria, composite_criteria, criterion_relationships tables
and structured_criterion JSONB column on criteria.

Revision ID: 42_01_expression_tree
Revises: 41_01_entity_omop_cols
Create Date: 2026-02-19 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "42_01_expression_tree"
down_revision: Union[str, None] = "41_01_entity_omop_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add structured_criterion column and create expression tree tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Add structured_criterion JSONB column to criteria table
    existing_cols = {c["name"] for c in inspector.get_columns("criteria")}
    if "structured_criterion" not in existing_cols:
        with op.batch_alter_table("criteria") as batch_op:
            batch_op.add_column(
                sa.Column("structured_criterion", sa.JSON(), nullable=True)
            )

    # Create atomic_criteria table
    if "atomic_criteria" not in existing_tables:
        op.create_table(
            "atomic_criteria",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "criterion_id",
                sa.String(),
                sa.ForeignKey("criteria.id"),
                nullable=False,
            ),
            sa.Column(
                "protocol_id",
                sa.String(),
                sa.ForeignKey("protocol.id"),
                nullable=False,
            ),
            sa.Column("inclusion_exclusion", sa.String(), nullable=False),
            sa.Column("entity_concept_id", sa.String(), nullable=True),
            sa.Column("entity_concept_system", sa.String(), nullable=True),
            sa.Column("omop_concept_id", sa.String(), nullable=True),
            sa.Column("entity_domain", sa.String(), nullable=True),
            sa.Column("relation_operator", sa.String(), nullable=True),
            sa.Column("value_numeric", sa.Float(), nullable=True),
            sa.Column("value_text", sa.String(), nullable=True),
            sa.Column("unit_text", sa.String(), nullable=True),
            sa.Column("negation", sa.Boolean(), default=False),
            sa.Column("temporal_constraint", sa.JSON(), nullable=True),
            sa.Column("original_text", sa.String(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("human_verified", sa.Boolean(), default=False),
            sa.Column("human_modified", sa.Boolean(), default=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_atomic_criterion_id", "atomic_criteria", ["criterion_id"])
        op.create_index("ix_atomic_protocol_id", "atomic_criteria", ["protocol_id"])
        op.create_index(
            "ix_atomic_entity_concept_id", "atomic_criteria", ["entity_concept_id"]
        )
        op.create_index(
            "ix_atomic_omop_concept_id", "atomic_criteria", ["omop_concept_id"]
        )
        op.create_index(
            "ix_atomic_proto_incl",
            "atomic_criteria",
            ["protocol_id", "inclusion_exclusion"],
        )

    # Create composite_criteria table
    if "composite_criteria" not in existing_tables:
        op.create_table(
            "composite_criteria",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "criterion_id",
                sa.String(),
                sa.ForeignKey("criteria.id"),
                nullable=False,
            ),
            sa.Column(
                "protocol_id",
                sa.String(),
                sa.ForeignKey("protocol.id"),
                nullable=False,
            ),
            sa.Column("inclusion_exclusion", sa.String(), nullable=False),
            sa.Column("logic_operator", sa.String(), nullable=False),
            sa.Column("parent_criterion_id", sa.String(), nullable=True),
            sa.Column("original_text", sa.String(), nullable=True),
            sa.Column("human_verified", sa.Boolean(), default=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_composite_criterion_id", "composite_criteria", ["criterion_id"]
        )
        op.create_index(
            "ix_composite_protocol_id", "composite_criteria", ["protocol_id"]
        )
        op.create_index(
            "ix_composite_parent_id", "composite_criteria", ["parent_criterion_id"]
        )

    # Create criterion_relationships table
    if "criterion_relationships" not in existing_tables:
        op.create_table(
            "criterion_relationships",
            sa.Column(
                "parent_criterion_id",
                sa.String(),
                sa.ForeignKey("composite_criteria.id"),
                primary_key=True,
            ),
            # child_criterion_id intentionally has no FK constraint: it is a
            # polymorphic reference that may point to atomic_criteria.id OR
            # composite_criteria.id depending on child_type. Standard FK
            # constraints cannot express this polymorphic relationship.
            sa.Column("child_criterion_id", sa.String(), primary_key=True),
            sa.Column(
                "child_type",
                sa.String(),
                nullable=False,
                comment="atomic|composite — target table for child_criterion_id",
            ),
            sa.Column("child_sequence", sa.Integer(), default=0, nullable=False),
        )


def downgrade() -> None:
    """Remove expression tree tables and structured_criterion column."""
    op.drop_table("criterion_relationships")
    op.drop_table("composite_criteria")
    op.drop_table("atomic_criteria")
    with op.batch_alter_table("criteria") as batch_op:
        batch_op.drop_column("structured_criterion")
