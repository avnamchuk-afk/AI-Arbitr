"""Add the shared Agreement domain foundation.

Revision ID: 20260927_0002
Revises: 20260927_0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260927_0002"
down_revision: Union[str, None] = "20260927_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("relationship_state", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("product_surface", sa.String(length=32), server_default="ai_arbitr", nullable=False)
        )
        batch_op.add_column(sa.Column("intent_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("understanding_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("based_on_agreement_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("state_version", sa.Integer(), server_default="1", nullable=False))
        batch_op.create_foreign_key(
            "fk_sessions_based_on_agreement_id_sessions",
            "sessions",
            ["based_on_agreement_id"],
            ["id"],
        )
        batch_op.create_index("ix_sessions_based_on_agreement_id", ["based_on_agreement_id"])
        batch_op.create_index("ix_sessions_relationship_state", ["relationship_state"])
        batch_op.create_index("ix_sessions_product_surface", ["product_surface"])

    op.create_table(
        "agreement_terms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("semantic_key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("display_value", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), server_default="additional", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="proposed", nullable=False),
        sa.Column("proposed_by_participant_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["proposed_by_participant_id"], ["contract_participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "semantic_key", "revision"),
    )
    op.create_index("ix_agreement_terms_session_id", "agreement_terms", ["session_id"])
    op.create_index("ix_agreement_terms_semantic_key", "agreement_terms", ["semantic_key"])
    op.create_index("ix_agreement_terms_status", "agreement_terms", ["status"])

    op.create_table(
        "agreement_term_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("term_revision", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["contract_participants.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["agreement_terms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "participant_id", "term_revision"),
    )
    op.create_index(
        "ix_agreement_term_confirmations_term_id", "agreement_term_confirmations", ["term_id"]
    )
    op.create_index(
        "ix_agreement_term_confirmations_participant_id",
        "agreement_term_confirmations",
        ["participant_id"],
    )

    op.create_table(
        "performance_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="claimed", nullable=False),
        sa.Column("actor_participant_id", sa.Uuid(), nullable=True),
        sa.Column("subject_participant_id", sa.Uuid(), nullable=True),
        sa.Column("term_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_participant_id"], ["contract_participants.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["subject_participant_id"], ["contract_participants.id"]),
        sa.ForeignKeyConstraint(["term_id"], ["agreement_terms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_performance_events_session_id", "performance_events", ["session_id"])
    op.create_index("ix_performance_events_event_type", "performance_events", ["event_type"])
    op.create_index("ix_performance_events_status", "performance_events", ["status"])

    op.create_table(
        "performance_event_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["performance_events.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["contract_participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "participant_id"),
    )
    op.create_index(
        "ix_performance_event_confirmations_event_id",
        "performance_event_confirmations",
        ["event_id"],
    )
    op.create_index(
        "ix_performance_event_confirmations_participant_id",
        "performance_event_confirmations",
        ["participant_id"],
    )

    op.create_table(
        "agreement_disputes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("opened_by_participant_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="collecting_positions", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opened_by_participant_id"], ["contract_participants.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agreement_disputes_session_id", "agreement_disputes", ["session_id"])
    op.create_index("ix_agreement_disputes_status", "agreement_disputes", ["status"])

    op.create_table(
        "dispute_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dispute_id"], ["agreement_disputes.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["contract_participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispute_id", "participant_id", "revision"),
    )
    op.create_index("ix_dispute_positions_dispute_id", "dispute_positions", ["dispute_id"])
    op.create_index("ix_dispute_positions_participant_id", "dispute_positions", ["participant_id"])

    op.create_table(
        "settlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="proposed", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dispute_id"], ["agreement_disputes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_settlements_dispute_id", "settlements", ["dispute_id"])
    op.create_index("ix_settlements_status", "settlements", ["status"])

    op.create_table(
        "settlement_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("settlement_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["contract_participants.id"]),
        sa.ForeignKeyConstraint(["settlement_id"], ["settlements.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settlement_id", "participant_id"),
    )
    op.create_index(
        "ix_settlement_confirmations_settlement_id", "settlement_confirmations", ["settlement_id"]
    )
    op.create_index(
        "ix_settlement_confirmations_participant_id",
        "settlement_confirmations",
        ["participant_id"],
    )


def downgrade() -> None:
    op.drop_table("settlement_confirmations")
    op.drop_table("settlements")
    op.drop_table("dispute_positions")
    op.drop_table("agreement_disputes")
    op.drop_table("performance_event_confirmations")
    op.drop_table("performance_events")
    op.drop_table("agreement_term_confirmations")
    op.drop_table("agreement_terms")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_product_surface")
        batch_op.drop_index("ix_sessions_relationship_state")
        batch_op.drop_index("ix_sessions_based_on_agreement_id")
        batch_op.drop_constraint("fk_sessions_based_on_agreement_id_sessions", type_="foreignkey")
        batch_op.drop_column("state_version")
        batch_op.drop_column("based_on_agreement_id")
        batch_op.drop_column("understanding_summary")
        batch_op.drop_column("intent_text")
        batch_op.drop_column("product_surface")
        batch_op.drop_column("relationship_state")
