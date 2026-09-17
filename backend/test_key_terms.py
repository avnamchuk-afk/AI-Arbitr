import unittest

from app.main import build_key_terms
from app.services.contract_templates import build_housing_rent_contract


class KeyTermsTest(unittest.TestCase):
    def test_housing_object_and_term_keep_leading_numbers(self):
        terms = {
            term["label"]: term["value"]
            for term in build_key_terms(build_housing_rent_contract("http://localhost"))
        }

        self.assertEqual(terms["Объект"], "1-комнатная квартира в Москве")
        self.assertEqual(terms["Срок"], "11 месяцев")


if __name__ == "__main__":
    unittest.main()
