import unittest

from app.catalogs.contracts import (
    CONTRACT_TYPES,
    build_contract_from_catalog,
    contract_catalog,
    identify_contract_type,
)


class ContractCatalogTests(unittest.TestCase):
    def test_recognizes_supported_requests(self):
        cases = {
            "Составь договор найма квартиры": "housing_rent",
            "Нужен договор на разработку сайта": "website_development",
            "Подготовь договор на разработку SaaS продукта": "saas_development",
            "Договор строительного подряда": "construction_work",
            "Договор оказания клининговых услуг": "services",
            "Договор поставки оборудования": "supply",
            "Подготовь условия поставок товара": "supply",
            "Договор займа между физлицами": "loan",
            "Учредительный договор для ООО": "llc_founders",
            "Подготовь договор страхования": "insurance",
        }
        for request, expected in cases.items():
            with self.subTest(request=request):
                self.assertEqual(identify_contract_type(request).id, expected)

    def test_housing_request_uses_fixed_template(self):
        contract_type, content = build_contract_from_catalog("аренда жилья", "https://ai-arbitr.example")
        self.assertEqual(contract_type.id, "housing_rent")
        self.assertTrue(contract_type.has_fixed_template)
        self.assertIn("ДОГОВОР НАЙМА ЖИЛОГО ПОМЕЩЕНИЯ", content)
        self.assertIn("https://ai-arbitr.example", content)

    def test_universal_type_has_no_fixed_template(self):
        contract_type, content = build_contract_from_catalog("необычная смешанная сделка", "https://example.test")
        self.assertEqual(contract_type.id, "universal")
        self.assertIsNone(content)

    def test_catalog_identifiers_are_unique_and_complete(self):
        ids = [item.id for item in CONTRACT_TYPES]
        self.assertEqual(len(ids), len(set(ids)))
        for item in CONTRACT_TYPES:
            self.assertEqual(len(item.roles), 2)
            self.assertTrue(item.legal_title)
            self.assertTrue(item.template_id)
            self.assertTrue(item.card_fields)

        serialized = contract_catalog()
        self.assertEqual(len(serialized["types"]), len(CONTRACT_TYPES))

    def test_contextual_roles_for_llc_and_insurance(self):
        self.assertEqual(
            identify_contract_type("Учредительный договор ООО").roles,
            ("Сооснователь 1", "Сооснователь 2"),
        )
        self.assertEqual(
            identify_contract_type("Договор страхования").roles,
            ("Страхователь", "Страховщик"),
        )


if __name__ == "__main__":
    unittest.main()
