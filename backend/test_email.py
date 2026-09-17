import unittest
from unittest.mock import patch

from app.services.email import send_contract_invite


class ContractInviteEmailTest(unittest.TestCase):
    @patch("app.services.email.smtp_is_configured", return_value=True)
    @patch("app.services.email._send_message")
    def test_sender_gets_separate_confirmation(self, send_message, _smtp_configured):
        send_contract_invite(
            "party2@example.org",
            "https://app.example.org/review/token",
            "Договор оказания услуг",
            "https://app.example.org/review/token.pdf",
            copy_to="party1@example.org",
        )

        self.assertEqual(send_message.call_count, 2)
        invite = send_message.call_args_list[0].args[0]
        confirmation = send_message.call_args_list[1].args[0]

        self.assertEqual(invite["To"], "party2@example.org")
        self.assertIn("Вам направлен на согласование", invite.get_content())
        self.assertEqual(confirmation["To"], "party1@example.org")
        self.assertIn("Вы направили проект договора", confirmation.get_content())
        self.assertIn("party2@example.org", confirmation.get_content())
        self.assertNotIn("/review/token", confirmation.get_content())


if __name__ == "__main__":
    unittest.main()
