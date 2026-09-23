import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import ContractSession, ContractVersion, Message, MessageRole


CONSENT = {
    "personal_data_accepted": True,
    "service_rules_accepted": True,
    "cookies_accepted": True,
    "consent_version": "1.0",
}


class LifecycleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.smtp_patches = [
            patch("app.main.send_contract_invite", return_value=None),
            patch("app.main.send_signature_progress_notice", return_value=None),
            patch("app.main.send_contract_signed_notice", return_value=None),
            patch("app.main.send_dispute_notice", return_value=None),
            patch("app.main.smtp_is_configured", return_value=True),
        ]
        for smtp_patch in self.smtp_patches:
            smtp_patch.start()
            self.addCleanup(smtp_patch.stop)
        self.llm_patch = patch(
            "app.main.ask_yandex_gpt",
            new=AsyncMock(return_value=(
                "ФАКТЫ: обязательство просрочено.\n\n"
                "ЗАКЛЮЧЕНИЕ AI-АРБИТРА: нарушение подтверждено.\n\n"
                "РЕКОМЕНДАЦИИ СТОРОНАМ: исполнить обязательство.\n\n"
                "ПРАВОВОЙ ДИСКЛЕЙМЕР: заключение носит рекомендательный характер."
            )),
        )
        self.llm_patch.start()
        self.addCleanup(self.llm_patch.stop)
        self.a = TestClient(app)
        self.b = TestClient(app)
        self.outsider = TestClient(app)

    def register_guest(self, client, email):
        self.assertEqual(client.post("/auth/guest").status_code, 200)
        response = client.post("/auth/quick-register", json={"email": email, **CONSENT})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["is_guest"])

    def signing_payload(self, email, name, passport):
        return {
            "party_type": "individual",
            "full_name": name,
            "passport": passport,
            "phone": "+7 900 000-00-01",
            "email": email,
            **CONSENT,
        }

    def create_contract(self):
        self.register_guest(self.a, "test-party-a@ai-arbitr.online")
        response = self.a.post("/sessions")
        self.assertEqual(response.status_code, 200, response.text)
        session_id = response.json()["id"]
        response = self.a.post(
            f"/sessions/{session_id}/messages",
            json={"content": "Составь договор найма жилого помещения", "model": "qwen"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.a.get(f"/sessions/{session_id}").json()
        self.assertEqual(detail["workflow"]["stage"], "ready_to_invite")
        self.assertEqual(len(detail["versions"]), 1)
        return session_id

    def invite(self, session_id):
        response = self.a.post(
            f"/sessions/{session_id}/invite",
            json={
                "email": "test-party-b@ai-arbitr.online",
                "creator_legal_role": "Наймодатель",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["invite_link"].rsplit("/", 1)[-1]
        self.assertEqual(response.json()["email_delivery"]["status"], "sent")
        return token

    def finalize_contract(self):
        session_id = self.create_contract()
        first_token = self.invite(session_id)
        review = self.b.get(f"/review/{first_token}")
        self.assertEqual(review.status_code, 200, review.text)

        changes = self.b.post(
            f"/review/{first_token}/request-changes",
            json={"content": "Разрешить использование кальяна в квартире."},
        )
        self.assertEqual(changes.status_code, 200, changes.text)
        self.assertEqual(self.b.get(f"/review/{first_token}").status_code, 404)

        detail = self.a.get(f"/sessions/{session_id}").json()
        self.assertEqual(detail["workflow"]["stage"], "ready_to_invite")
        self.assertTrue(any("Разрешить использование кальяна" in item["content"] for item in detail["messages"]))

        options = self.a.post(
            f"/sessions/{session_id}/messages",
            json={"content": "Добавь условие: разрешить использование кальяна в квартире"},
        )
        self.assertEqual(options.status_code, 200, options.text)
        saved = self.a.post(f"/sessions/{session_id}/messages", json={"content": "краткая"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["contract_saved"])

        second_token = self.invite(session_id)
        self.assertNotEqual(first_token, second_token)
        b_sign = self.b.post(
            f"/review/{second_token}/approve",
            json=self.signing_payload("test-party-b@ai-arbitr.online", "Петров Петр Петрович", "2222 222222"),
        )
        self.assertEqual(b_sign.status_code, 200, b_sign.text)
        self.assertTrue(b_sign.json()["authenticated"])
        self.assertEqual(b_sign.json()["session_id"], session_id)
        self.assertEqual(self.b.get(f"/review/{second_token}").status_code, 404)

        b_sessions = self.b.get("/sessions")
        self.assertEqual(b_sessions.status_code, 200, b_sessions.text)
        self.assertIn(session_id, {item["id"] for item in b_sessions.json()})

        a_sign = self.a.post(
            f"/sessions/{session_id}/approve",
            json=self.signing_payload("test-party-a@ai-arbitr.online", "Иванов Иван Иванович", "1111 111111"),
        )
        self.assertEqual(a_sign.status_code, 200, a_sign.text)
        self.assertTrue(a_sign.json()["finalized"])

        detail = self.a.get(f"/sessions/{session_id}").json()
        self.assertEqual(detail["workflow"]["stage"], "active")
        self.assertTrue(detail["session"]["final_content_hash"])
        self.assertEqual(sum(1 for item in detail["versions"] if item["is_final"]), 1)
        self.assertTrue(all(item["signed_at"] for item in detail["participants"]))
        self.assertEqual(self.b.get(f"/sessions/{session_id}").status_code, 200)
        self.assertEqual(self.a.get(f"/sessions/{session_id}/contract.pdf").status_code, 200)
        self.assertEqual(self.b.get(f"/sessions/{session_id}/contract.pdf").status_code, 200)
        self.outsider.post("/auth/guest")
        self.assertEqual(self.outsider.get(f"/sessions/{session_id}/contract.pdf").status_code, 403)
        return session_id

    def test_successful_contract_lifecycle(self):
        session_id = self.finalize_contract()
        first = self.a.post(f"/sessions/{session_id}/complete")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["completed"])
        second = self.b.post(f"/sessions/{session_id}/complete")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()["completed"])
        detail = self.a.get(f"/sessions/{session_id}").json()
        self.assertEqual(detail["workflow"]["stage"], "completed")
        self.assertTrue(detail["session"]["is_completed"])

    def test_invite_is_saved_when_email_delivery_fails(self):
        session_id = self.create_contract()
        with patch("app.main.send_contract_invite", side_effect=OSError("smtp unavailable")):
            response = self.a.post(
                f"/sessions/{session_id}/invite",
                json={"email": "test-party-b@ai-arbitr.online", "creator_legal_role": "Наймодатель"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email_delivery"]["status"], "failed")
        token = response.json()["invite_link"].rsplit("/", 1)[-1]
        self.assertEqual(self.b.get(f"/review/{token}").status_code, 200)
        detail = self.a.get(f"/sessions/{session_id}").json()
        self.assertEqual(detail["workflow"]["stage"], "awaiting_counterparty")

    def test_dispute_lifecycle(self):
        session_id = self.finalize_contract()
        opened = self.a.post(
            f"/sessions/{session_id}/messages",
            json={"content": "СПОР: Наниматель просрочил платеж."},
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        responded = self.b.post(
            f"/sessions/{session_id}/messages",
            json={"content": "ОТВЕТ: Платеж направлен частично."},
        )
        self.assertEqual(responded.status_code, 200, responded.text)
        decision = self.a.post(
            f"/sessions/{session_id}/messages",
            json={"content": "СПОР: Сформируй решение с учетом ответа второй стороны."},
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        state = self.a.get(f"/sessions/{session_id}").json()["dispute"]
        self.assertTrue(state["opened"])
        self.assertTrue(state["responded"])
        self.assertTrue(state["decision_issued"])

        accepted_a = self.a.post(f"/sessions/{session_id}/dispute/accept", json={"accepted": True})
        self.assertEqual(accepted_a.status_code, 200, accepted_a.text)
        self.assertFalse(accepted_a.json()["closed"])
        accepted_b = self.b.post(f"/sessions/{session_id}/dispute/accept", json={"accepted": True})
        self.assertEqual(accepted_b.status_code, 200, accepted_b.text)
        self.assertTrue(accepted_b.json()["closed"])

        with self.Session() as db:
            session = db.get(ContractSession, uuid.UUID(session_id))
            self.assertTrue(session.is_completed)
            markers = {
                row[0].split("|", 1)[0]
                for row in db.query(Message.content)
                .filter(Message.session_id == uuid.UUID(session_id), Message.role == MessageRole.system)
                .all()
            }
            self.assertTrue({
                "DISPUTE_OPENED",
                "DELAY_NOTICE",
                "DELAY_RESPONSE",
                "BREACH_NOTICE",
                "DISPUTE_DECISION",
                "DISPUTE_ACCEPTED",
                "DISPUTE_CLOSED",
            }.issubset(markers))
            final_version = (
                db.query(ContractVersion)
                .filter(ContractVersion.session_id == uuid.UUID(session_id), ContractVersion.is_final.is_(True))
                .one()
            )
            self.assertTrue(final_version.content)


if __name__ == "__main__":
    unittest.main()
