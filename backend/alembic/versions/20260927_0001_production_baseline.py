"""Mark the schema that existed before managed migrations.

Revision ID: 20260927_0001
Revises: None
"""
from typing import Sequence, Union


revision: str = "20260927_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing installations stamp this revision after schema verification.
    pass


def downgrade() -> None:
    pass
