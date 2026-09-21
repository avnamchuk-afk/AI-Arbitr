import re


CONTRACT_UPDATE_PREFIX = "ДОПОЛНИТЬ ДОГОВОР:"

ADDITION_PATTERNS = (
    r"^(?:пожалуйста,?\s*)?(?:добавь|добавить|включи|включить|дополни|дополнить|предусмотри|предусмотреть)\b",
    r"^(?:измени|изменить|перепиши|переписать|скорректируй|скорректировать)\s+(?:пункт|условие|положение)\b",
    r"^(?:нужно|хочу|надо)\s+(?:добавить|включить|предусмотреть)\b",
)

AGREEMENT_PHRASES = {
    "нет",
    "нет вопросов",
    "вопросов нет",
    "все понятно",
    "все ясно",
    "переходим к согласованию",
    "перейдем к согласованию",
    "давайте согласовывать",
    "направляем на согласование",
    "направить на согласование",
    "согласовать версию",
}

SHOW_CONTRACT_PHRASES = {
    "покажи договор",
    "покажи полный текст",
    "полный текст",
    "полный текст договора",
    "покажи текущую версию",
    "текущая версия",
    "текущую версию",
}

ROLLBACK_PHRASES = {
    "верни предыдущую версию",
    "вернуться к предыдущей версии",
    "откати изменение",
    "отмени последнее изменение",
}

OFF_TOPIC_EXACT_PHRASES = {
    "привет",
    "здравствуй",
    "здравствуйте",
    "как дела",
    "как ты",
    "что ты умеешь",
    "поговори со мной",
}

OFF_TOPIC_ACTION_PATTERNS = (
    r"\b(?:расскажи|придумай)\s+(?:анекдот|шутку|сказку|историю)\b",
    r"\b(?:напиши|сочини|сгенерируй)\s+(?:стих|песню|эссе|реферат|код|программу|скрипт|рецепт)\b",
    r"\b(?:посоветуй|порекомендуй)\s+(?:фильм|сериал|книгу|ресторан|игру)\b",
)

OFF_TOPIC_SUBJECT_PATTERNS = (
    r"\b(?:рецепт|погода|гороскоп|курс валют|результат матча|новости спорта|президент|политик|"
    r"столица|музык|знаменитост|космос|футбол|хоккей)\b",
)

CONTRACT_CONTEXT_PATTERN = (
    r"\b(?:договор|услови|пункт|положени|сторон|обязательств|оплат|платеж|срок|найм|аренд|"
    r"неустой|штраф|закон|кодекс|гк|подряд|услуг|исполнен|расторжен|депозит|обеспечительн)"
)

CONTRACT_CREATION_PATTERN = (
    r"\b(?:состав|подготов|созда|разработ|нужен|нужна|нужно)\w*\s+(?:проект\s+)?(?:догов|соглашен|оферт)|"
    r"\b(?:догов|соглашен|оферт|найм|аренд|подряд|оказан\w*\s+услуг|поставк|займ|лизинг|купл|продаж)"
)

PROMPT_ABUSE_PATTERNS = (
    r"\bигнорируй\s+(?:все\s+)?(?:предыдущие|системные)\s+(?:инструкции|правила|промты)\b",
    r"\b(?:покажи|раскрой|выведи)\s+(?:системный\s+)?промт\b",
    r"\bты\s+теперь\s+(?:не|другая|другой|свободная|свободный)\b",
    r"\b(?:developer|system)\s*(?:message|prompt)\b",
)


def detect_contract_message_intent(text: str) -> str:
    normalized = " ".join(text.lower().replace("ё", "е").split())
    if normalized.rstrip(".!?") in SHOW_CONTRACT_PHRASES:
        return "show_contract"
    if normalized.rstrip(".!?") in ROLLBACK_PHRASES:
        return "rollback"
    if any(re.search(pattern, normalized) for pattern in ADDITION_PATTERNS):
        return "addition"
    if normalized.rstrip(".!?") in AGREEMENT_PHRASES:
        return "agreement"
    return "question"


def strip_addition_command(text: str) -> str:
    cleaned = text.removeprefix(CONTRACT_UPDATE_PREFIX).strip()
    cleaned = re.sub(
        r"^(?:пожалуйста,?\s*)?(?:добавь|добавить|включи|включить|дополни|дополнить|предусмотри|предусмотреть)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned or text.strip()


def is_clearly_unrelated_to_contract(text: str) -> bool:
    normalized = " ".join(text.lower().replace("ё", "е").split()).strip(" .!?")
    if normalized in OFF_TOPIC_EXACT_PHRASES:
        return True
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in PROMPT_ABUSE_PATTERNS):
        return True
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in OFF_TOPIC_ACTION_PATTERNS):
        return True
    if re.search(CONTRACT_CONTEXT_PATTERN, normalized, re.IGNORECASE):
        return False
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in OFF_TOPIC_SUBJECT_PATTERNS)


def is_contract_creation_request(text: str) -> bool:
    normalized = " ".join(text.lower().replace("ё", "е").split())
    return bool(re.search(CONTRACT_CREATION_PATTERN, normalized, re.IGNORECASE))
