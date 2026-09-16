import httpx

from app.core.config import settings


class YandexGPTError(RuntimeError):
    pass


DEFAULT_YANDEX_GPT_MODEL = "yandexgpt-5.1"
DEFAULT_LEGAL_SYSTEM_PROMPT = (
    "Ты — юрист-аналитик с 15-летним опытом практики в гражданском и договорном праве РФ. "
    "Анализируй договоры и запросы пользователя строго по праву РФ и обычной договорной практике. "
    "Находи противоречия между условиями, риски для сторон и отсутствующие существенные или важные "
    "условия. Отвечай структурированно и простым языком. Не выдумывай факты, реквизиты, нормы и "
    "судебную практику. Если данных недостаточно, скажи прямо и задай уточняющий вопрос."
)


def build_model_uri() -> str:
    if settings.yandex_gpt_model_uri:
        return settings.yandex_gpt_model_uri
    return f"gpt://{settings.yandex_gpt_folder_id}/{DEFAULT_YANDEX_GPT_MODEL}"


def ensure_system_message(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if any(message.get("role") == "system" for message in messages):
        return messages
    return [{"role": "system", "text": DEFAULT_LEGAL_SYSTEM_PROMPT}, *messages]


def build_completion_options(include_reasoning: bool = True) -> dict:
    options = {"stream": False, "temperature": 0.2, "maxTokens": "4000"}
    if include_reasoning:
        options["reasoningOptions"] = {"mode": "ENABLED_HIDDEN"}
    return options


def is_unsupported_reasoning_response(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = response.text
    return "does not support reasoning" in message.lower()


async def ask_yandex_gpt(messages: list[dict[str, str]]) -> str:
    if not settings.yandex_gpt_api_key or not settings.yandex_gpt_folder_id:
        raise YandexGPTError("YandexGPT is not configured")

    normalized_messages = ensure_system_message(messages)
    payload = {
        "modelUri": build_model_uri(),
        "completionOptions": build_completion_options(include_reasoning=True),
        "messages": normalized_messages,
    }
    headers = {
        "Authorization": f"Api-Key {settings.yandex_gpt_api_key}",
        "Content-Type": "application/json",
        "x-folder-id": settings.yandex_gpt_folder_id,
    }

    try:
        timeout = httpx.Timeout(90.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                json=payload,
                headers=headers,
            )
            if is_unsupported_reasoning_response(response):
                payload["completionOptions"] = build_completion_options(include_reasoning=False)
                response = await client.post(
                    "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                    json=payload,
                    headers=headers,
                )
    except httpx.TimeoutException as exc:
        raise YandexGPTError("YandexGPT response timed out") from exc
    except httpx.HTTPError as exc:
        raise YandexGPTError("YandexGPT API request failed") from exc

    if response.status_code >= 400:
        raise YandexGPTError("YandexGPT API is unavailable")

    data = response.json()
    return data["result"]["alternatives"][0]["message"]["text"]
