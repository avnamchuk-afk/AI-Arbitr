APP_VERSION = "0.9.0-beta"


def identify_contract_template(content: str) -> tuple[str, str]:
    from app.catalogs.contracts import identify_contract_type

    contract_type = identify_contract_type(content, content=True)
    return contract_type.template_id, contract_type.template_version
