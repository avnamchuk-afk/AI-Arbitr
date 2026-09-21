from dataclasses import dataclass
from typing import Callable

from app.services.contract_templates import (
    build_ai_store_assistant_contract,
    build_housing_rent_contract,
    build_website_development_contract,
)


TemplateBuilder = Callable[[str], str]


@dataclass(frozen=True)
class CardField:
    key: str
    label: str
    markers: tuple[str, ...]


@dataclass(frozen=True)
class ContractType:
    id: str
    category: str
    legal_title: str
    short_title: str
    request_markers: tuple[str, ...]
    content_markers: tuple[str, ...]
    roles: tuple[str, str]
    template_id: str
    template_version: str
    card_fields: tuple[CardField, ...]
    request_marker_groups: tuple[tuple[str, ...], ...] = ()
    template_builder: TemplateBuilder | None = None

    @property
    def has_fixed_template(self) -> bool:
        return self.template_builder is not None


STANDARD_CARD_FIELDS = (
    CardField("subject", "Предмет", ("предмет договора", "предметом договора")),
    CardField("price", "Цена", ("цена договора", "стоимость услуг", "стоимость работ")),
    CardField("term", "Срок", ("срок действия", "срок выполнения", "срок оказания")),
    CardField("payment", "Оплата", ("порядок оплаты", "оплата производится", "оплачивает")),
    CardField("disputes", "Споры", ("ai-arbitr",)),
)

HOUSING_CARD_FIELDS = (
    CardField("object", "Объект", ("жилое помещение", "квартира", "комната", "жилой дом")),
    CardField("monthly_payment", "Оплата в месяц", ("ежемесячная плата",)),
    CardField("utilities", "ЖКУ", ("коммунальные платежи",)),
    CardField("term", "Срок", ("срок действия", "дата окончания договора")),
    CardField("auto_prolongation", "Автопролонгация", ("автоматически продлен",)),
    CardField("children", "Дети", ("несовершеннолет", "проживающих")),
    CardField("pets", "Животные", ("домашних животных",)),
    CardField("deposit", "Депозит", ("обеспечительный платеж", "депозит")),
    CardField("disputes", "Споры", ("ai-arbitr",)),
)


def _housing_builder(service_url: str) -> str:
    return build_housing_rent_contract(service_url)


def _website_builder(_: str) -> str:
    return build_website_development_contract()


def _ai_store_builder(_: str) -> str:
    return build_ai_store_assistant_contract()


CONTRACT_TYPES: tuple[ContractType, ...] = (
    ContractType(
        id="housing_rent",
        category="housing_rent",
        legal_title="Договор найма жилого помещения",
        short_title="Договор найма",
        request_markers=("договор найма", "найм жил", "наймодатель", "наниматель"),
        content_markers=("наймодатель", "наниматель", "жилое помещение"),
        roles=("Наймодатель", "Наниматель"),
        template_id="housing-rent-ru",
        template_version="1.0",
        card_fields=HOUSING_CARD_FIELDS,
        request_marker_groups=(("аренд", "жиль"), ("аренд", "квартир"), ("снять", "квартир"), ("сда", "квартир")),
        template_builder=_housing_builder,
    ),
    ContractType(
        id="ai_store_assistant",
        category="digital_development",
        legal_title="Договор подряда на разработку программного обеспечения",
        short_title="Договор AI-помощника",
        request_markers=("ai-помощник", "ai помощник", "ии-помощник", "ии помощник"),
        content_markers=("ai-помощника для интернет-магазина", "поиск ответов по переданному заказчиком каталогу"),
        roles=("Заказчик", "Подрядчик"),
        template_id="ai-store-assistant-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
        template_builder=_ai_store_builder,
    ),
    ContractType(
        id="website_development",
        category="digital_development",
        legal_title="Договор на разработку сайта",
        short_title="Договор на сайт",
        request_markers=("лендинг", "landing"),
        content_markers=("разработка сайта", "создание сайта", "техническое задание"),
        roles=("Заказчик", "Исполнитель"),
        template_id="website-development-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
        request_marker_groups=(("разработ", "сайт"), ("создан", "сайт"), ("сделать", "сайт")),
        template_builder=_website_builder,
    ),
    ContractType(
        id="saas_development",
        category="digital_development",
        legal_title="Договор на разработку программного обеспечения",
        short_title="Договор SaaS",
        request_markers=("saas", "саас", "программ обеспеч", "разработк по"),
        content_markers=("программное обеспечение", "исключительные права", "исходный код"),
        roles=("Заказчик", "Исполнитель"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="construction_work",
        category="construction",
        legal_title="Договор подряда",
        short_title="Договор подряда",
        request_markers=("подряд", "ремонт", "строитель"),
        content_markers=("подрядчик", "результат работ", "приемка работ"),
        roles=("Заказчик", "Подрядчик"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="services",
        category="services",
        legal_title="Договор возмездного оказания услуг",
        short_title="Договор услуг",
        request_markers=("оказан услуг", "договор услуг", "клининг", "уборк", "юридическ услуг"),
        content_markers=("исполнитель", "заказчик", "оказать услуги"),
        roles=("Заказчик", "Исполнитель"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="supply",
        category="goods",
        legal_title="Договор поставки",
        short_title="Договор поставки",
        request_markers=("постав", "поставщик"),
        content_markers=("поставщик", "покупатель", "поставить товар"),
        roles=("Поставщик", "Покупатель"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="sale",
        category="goods",
        legal_title="Договор купли-продажи",
        short_title="Договор купли-продажи",
        request_markers=("купл-продаж", "купли-продаж", "продать", "покупк"),
        content_markers=("продавец", "покупатель", "передать товар"),
        roles=("Продавец", "Покупатель"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="llc_founders",
        category="corporate",
        legal_title="Договор об учреждении общества с ограниченной ответственностью",
        short_title="Договор об учреждении ООО",
        request_markers=("учредительный договор", "учреждении ооо", "создать ооо", "соосновател"),
        content_markers=("сооснователь 1", "сооснователь 2", "уставный капитал", "учреждении общества"),
        roles=("Сооснователь 1", "Сооснователь 2"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
        request_marker_groups=(("договор", "ооо"), ("участник", "уставный капитал")),
    ),
    ContractType(
        id="insurance",
        category="insurance",
        legal_title="Договор страхования",
        short_title="Договор страхования",
        request_markers=("страхован", "страховой договор", "страховщик", "страхователь"),
        content_markers=("страхователь", "страховщик", "страховой случай"),
        roles=("Страхователь", "Страховщик"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="loan",
        category="loan",
        legal_title="Договор займа",
        short_title="Договор займа",
        request_markers=("договор займ", "дать в долг", "заем", "займ"),
        content_markers=("займодавец", "заемщик", "сумма займа"),
        roles=("Займодавец", "Заемщик"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
    ContractType(
        id="nda",
        category="confidentiality",
        legal_title="Соглашение о конфиденциальности",
        short_title="NDA",
        request_markers=("nda", "нда", "соглашен о конфиденциальност", "неразглашен"),
        content_markers=("конфиденциальная информация", "неразглашение"),
        roles=("Раскрывающая сторона", "Получающая сторона"),
        template_id="universal-contract-ru",
        template_version="1.0",
        card_fields=STANDARD_CARD_FIELDS,
    ),
)

UNIVERSAL_CONTRACT = ContractType(
    id="universal",
    category="other_contract",
    legal_title="Договор",
    short_title="Новый договор",
    request_markers=(),
    content_markers=(),
    roles=("Заказчик", "Исполнитель"),
    template_id="universal-contract-ru",
    template_version="1.0",
    card_fields=STANDARD_CARD_FIELDS,
)

CONTRACT_TYPES_BY_ID = {contract_type.id: contract_type for contract_type in CONTRACT_TYPES}


def normalize_lookup_text(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def identify_contract_type(value: str, *, content: bool = False) -> ContractType:
    normalized = normalize_lookup_text(value)
    marker_attribute = "content_markers" if content else "request_markers"
    for contract_type in CONTRACT_TYPES:
        markers = getattr(contract_type, marker_attribute)
        direct_match = any(marker in normalized for marker in markers)
        grouped_match = not content and any(
            all(marker in normalized for marker in marker_group)
            for marker_group in contract_type.request_marker_groups
        )
        if direct_match or grouped_match:
            return contract_type
    if content:
        for contract_type in CONTRACT_TYPES:
            if any(marker in normalized for marker in contract_type.request_markers):
                return contract_type
    return UNIVERSAL_CONTRACT


def build_contract_from_catalog(value: str, service_url: str) -> tuple[ContractType, str | None]:
    contract_type = identify_contract_type(value)
    if contract_type.template_builder is None:
        return contract_type, None
    return contract_type, contract_type.template_builder(service_url)


def describe_contract_type(contract_type: ContractType) -> dict:
    return {
        "id": contract_type.id,
        "category": contract_type.category,
        "legal_title": contract_type.legal_title,
        "short_title": contract_type.short_title,
        "roles": list(contract_type.roles),
        "template_id": contract_type.template_id,
        "template_version": contract_type.template_version,
        "has_fixed_template": contract_type.has_fixed_template,
        "card_fields": [
            {"key": field.key, "label": field.label}
            for field in contract_type.card_fields
        ],
    }


def contract_catalog() -> dict:
    return {
        "types": [describe_contract_type(contract_type) for contract_type in CONTRACT_TYPES],
        "fallback": describe_contract_type(UNIVERSAL_CONTRACT),
    }
