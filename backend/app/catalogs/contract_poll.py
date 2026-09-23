CONTRACT_TYPE_POLL_OPTIONS = (
    ("housing", "Найм и аренда"),
    ("ai_saas", "Разработка AI / SaaS"),
    ("services", "Услуги и фриланс"),
    ("work", "Подряд и ремонт"),
    ("sale_supply", "Купля-продажа и поставка"),
    ("other", "Другой тип договора"),
    ("universal", "Универсальной генерации достаточно"),
)

CONTRACT_TYPE_POLL_IDS = frozenset(option_id for option_id, _ in CONTRACT_TYPE_POLL_OPTIONS)
