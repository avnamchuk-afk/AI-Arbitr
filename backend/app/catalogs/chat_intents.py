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


def detect_contract_message_intent(text: str) -> str:
    normalized = " ".join(text.lower().replace("ё", "е").split())
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
