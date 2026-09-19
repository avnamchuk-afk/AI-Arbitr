APP_VERSION = "0.5.12-beta"

HOUSING_RENT_TEMPLATE_ID = "housing-rent-ru"
HOUSING_RENT_TEMPLATE_VERSION = "1.0"
WEBSITE_DEVELOPMENT_TEMPLATE_ID = "website-development-ru"
WEBSITE_DEVELOPMENT_TEMPLATE_VERSION = "1.0"
UNIVERSAL_TEMPLATE_ID = "universal-contract-ru"
UNIVERSAL_TEMPLATE_VERSION = "1.0"


def identify_contract_template(content: str) -> tuple[str, str]:
    normalized = content.upper()
    if "ДОГОВОР НАЙМА ЖИЛОГО ПОМЕЩЕНИЯ" in normalized:
        return HOUSING_RENT_TEMPLATE_ID, HOUSING_RENT_TEMPLATE_VERSION
    if "РАЗРАБОТ" in normalized and ("САЙТ" in normalized or "ПРОГРАМ" in normalized):
        return WEBSITE_DEVELOPMENT_TEMPLATE_ID, WEBSITE_DEVELOPMENT_TEMPLATE_VERSION
    return UNIVERSAL_TEMPLATE_ID, UNIVERSAL_TEMPLATE_VERSION
