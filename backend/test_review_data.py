import unittest

from fastapi import HTTPException

from app.main import ReviewApproveRequest, apply_ephemeral_party_data, require_unified_consent


class ReviewPartyDataTest(unittest.TestCase):
    def test_unified_consent_requires_all_parts(self):
        require_unified_consent(True, True, True, "1.0")
        with self.assertRaises(HTTPException):
            require_unified_consent(True, False, True, "1.0")
        with self.assertRaises(HTTPException):
            require_unified_consent(True, True, True, "0.9")

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
            "Гражданин РФ Иванов Иван Иванович, паспорт серии 1111 № 111111, именуемый в дальнейшем «Наниматель».",
            payload,
        )

        self.assertIn("Сидоров Сергей Сергеевич", result)
        self.assertIn("паспорт серии 1234 № 567890", result)
        self.assertIn("+7 999 123-45-67", result)
        self.assertIn("party2@example.org", result)
        self.assertNotIn("Иванов Иван Иванович", result)

    def test_legacy_demo_passport_details_are_removed(self):
        payload = ReviewApproveRequest(
            party_type="individual",
            full_name="Сидоров Сергей Сергеевич",
            passport="1234 567890",
            phone="+7 999 123-45-67",
            email="party2@example.org",
            personal_data_accepted=True,
        )
        contract = (
            "Гражданин РФ Иванов Иван Иванович, паспорт серии 1111 № 111111, "
            "выдан ОВД района 01 января 2020 г., код подразделения 000-000, "
            "зарегистрированный по адресу: г. Москва, ул. Тестовая, д. 1, "
            "именуемый в дальнейшем «Наниматель»."
        )

        result = apply_ephemeral_party_data(contract, payload)

        self.assertNotIn("выдан ОВД", result)
        self.assertNotIn("зарегистрированный по адресу", result)
        self.assertIn("паспорт серии 1234 № 567890, именуемый", result)

    def test_owner_data_replaces_landlord_requisites_only(self):
        payload = ReviewApproveRequest(
            party_type="individual",
            full_name="Новый Наймодатель",
            passport="9876 543210",
            phone="+7 999 000-00-00",
            email="owner@example.org",
            personal_data_accepted=True,
        )
        contract = (
            "Гражданин РФ Старый Наймодатель, паспорт серии 1111 № 111111, именуемый в дальнейшем «Наймодатель».\n"
            "Гражданин РФ Старый Наниматель, паспорт серии 2222 № 222222, именуемый в дальнейшем «Наниматель»."
        )

        result = apply_ephemeral_party_data(contract, payload, participant_role="party_1")

        self.assertIn("Гражданин РФ Новый Наймодатель, паспорт серии 9876 № 543210", result)
        self.assertIn("Гражданин РФ Старый Наниматель, паспорт серии 2222 № 222222", result)

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
