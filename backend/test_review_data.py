import unittest

from app.main import ReviewApproveRequest, apply_ephemeral_party_data


class ReviewPartyDataTest(unittest.TestCase):
    def test_individual_data_replaces_demo_requisites(self):
        payload = ReviewApproveRequest(
            party_type="individual",
            full_name="Сидоров Сергей Сергеевич",
            passport="1234 567890",
            phone="+7 999 123-45-67",
            email="party2@example.org",
            personal_data_accepted=True,
        )

        result = apply_ephemeral_party_data(
            "Наниматель Иванов Иван Иванович, паспорт 1111 111111.",
            payload,
        )

        self.assertIn("Сидоров Сергей Сергеевич", result)
        self.assertIn("1234 567890", result)
        self.assertIn("+7 999 123-45-67", result)
        self.assertIn("party2@example.org", result)
        self.assertNotIn("Иванов Иван Иванович", result)

    def test_business_data_is_added_to_contract(self):
        payload = ReviewApproveRequest(
            party_type="business",
            full_name="Петров Петр Петрович",
            organization_name='ООО "Пример"',
            inn="7701234567",
            ogrn="1234567890123",
            phone="+7 999 123-45-67",
            email="company@example.org",
            personal_data_accepted=True,
        )

        result = apply_ephemeral_party_data("ДОГОВОР", payload)

        self.assertIn('ООО "Пример"', result)
        self.assertIn("7701234567", result)
        self.assertIn("1234567890123", result)
        self.assertIn("Петров Петр Петрович", result)


if __name__ == "__main__":
    unittest.main()
