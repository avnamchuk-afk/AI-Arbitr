import re


PASSPORT_RE = re.compile(r"\b\d{4}[\s-]?\d{6}\b")


def contains_passport_like_data(text: str) -> bool:
    return bool(PASSPORT_RE.search(text))
