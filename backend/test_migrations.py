import tempfile
import unittest
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, ForeignKey, MetaData, String, Table, Uuid, create_engine, inspect, text


BASELINE_REVISION = "20260927_0001"
HEAD_REVISION = "20260927_0002"
NEW_SESSION_COLUMNS = {
    "relationship_state",
    "product_surface",
    "intent_text",
    "understanding_summary",
    "based_on_agreement_id",
    "state_version",
}
NEW_TABLES = {
    "agreement_terms",
    "agreement_term_confirmations",
    "performance_events",
    "performance_event_confirmations",
    "agreement_disputes",
    "dispute_positions",
    "settlements",
    "settlement_confirmations",
}


def create_legacy_schema(database_url: str) -> None:
    metadata = MetaData()
    Table("users", metadata, Column("id", Uuid(), primary_key=True), Column("email", String(320), nullable=False))
    Table(
        "sessions",
        metadata,
        Column("id", Uuid(), primary_key=True),
        Column("owner_user_id", Uuid(), ForeignKey("users.id"), nullable=False),
        Column("title", String(120), nullable=False),
    )
    Table(
        "contract_participants",
        metadata,
        Column("id", Uuid(), primary_key=True),
        Column("session_id", Uuid(), ForeignKey("sessions.id"), nullable=False),
        Column("user_id", Uuid(), ForeignKey("users.id"), nullable=True),
        Column("role", String(32), nullable=False),
    )
    metadata.create_all(create_engine(database_url))


class MigrationSmokeTest(unittest.TestCase):
    def test_baseline_then_additive_upgrade(self):
        backend_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "legacy.db"
            database_url = f"sqlite:///{database_path}"
            create_legacy_schema(database_url)

            engine = create_engine(database_url)
            inspector = inspect(engine)
            legacy_columns = {column["name"] for column in inspector.get_columns("sessions")}
            self.assertTrue(NEW_SESSION_COLUMNS.isdisjoint(legacy_columns))
            self.assertTrue(NEW_TABLES.isdisjoint(set(inspector.get_table_names())))
            engine.dispose()

            config = Config(str(backend_dir / "alembic.ini"))
            config.set_main_option("script_location", str(backend_dir / "alembic"))
            config.set_main_option("sqlalchemy.url", database_url)
            config.attributes["use_config_url"] = True
            command.stamp(config, BASELINE_REVISION)
            command.upgrade(config, "head")

            engine = create_engine(database_url)
            inspector = inspect(engine)
            upgraded_columns = {column["name"] for column in inspector.get_columns("sessions")}
            self.assertTrue(NEW_SESSION_COLUMNS.issubset(upgraded_columns))
            self.assertTrue(NEW_TABLES.issubset(set(inspector.get_table_names())))

            user_id = uuid.uuid4()
            session_id = uuid.uuid4()
            with engine.begin() as connection:
                current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                self.assertEqual(current_revision, HEAD_REVISION)
                connection.execute(
                    text("INSERT INTO users (id, email) VALUES (:id, :email)"),
                    {"id": user_id.hex, "email": "migration-test@ai-arbitr.online"},
                )
                connection.execute(
                    text("INSERT INTO sessions (id, owner_user_id, title) VALUES (:id, :owner_id, :title)"),
                    {"id": session_id.hex, "owner_id": user_id.hex, "title": "Legacy session"},
                )
                defaults = connection.execute(
                    text("SELECT product_surface, state_version FROM sessions WHERE id = :id"),
                    {"id": session_id.hex},
                ).one()
                self.assertEqual(defaults.product_surface, "ai_arbitr")
                self.assertEqual(defaults.state_version, 1)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
