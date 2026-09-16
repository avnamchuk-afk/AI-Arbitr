import httpx

from app.core.config import settings


class YandexGPTError(RuntimeError):
    pass


DEFAULT_YANDEX_GPT_MODEL = "yandexgpt-5.1"
SUPPORTED_MODELS = {
    "yandexgpt": DEFAULT_YANDEX_GPT_MODEL,
    "qwen": "qwen2.5-7b-instruct",
}
DEFAULT_LEGAL_SYSTEM_PROMPT = (
    "Ты — юрист-аналитик с 15-летним опытом практики в гражданском и договорном праве РФ. "
    "Анализируй договоры и запросы пользователя строго по праву РФ и обычной договорной практике. "
    "Находи противоречия между условиями, риски для сторон и отсутствующие существенные или важные "
    "условия. Отвечай структурированно и простым языком. Не выдумывай факты, реквизиты, нормы и "
    "судебную практику. Если данных недостаточно, скажи прямо и задай уточняющий вопрос."
)


def build_model_uri(model: str | None = None) -> str:
    model_key = (model or "yandexgpt").strip().lower()
    if model_key == "yandexgpt" and settings.yandex_gpt_model_uri:
        return settings.yandex_gpt_model_uri
    model_name = SUPPORTED_MODELS.get(model_key, DEFAULT_YANDEX_GPT_MODEL)
    return f"gpt://{settings.yandex_gpt_folder_id}/{model_name}"


def ensure_system_message(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if any(message.get("role") == "system" for message in messages):
        return messages
    return [{"role": "system", "text": DEFAULT_LEGAL_SYSTEM_PROMPT}, *messages]


def build_completion_options(include_reasoning: bool = True) -> dict:
    options = {"stream": False, "temperature": 0.2, "maxTokens": "4000"}
    if include_reasoning:
        options["reasoningOptions"] = {"mode": "ENABLED_HIDDEN"}
    return options


def get_error_message(response: httpx.Response) -> str:
    try:
        return response.json().get("error", {}).get("message", "")
    except ValueError:
        return response.text


def is_unsupported_reasoning_response(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    message = get_error_message(response)
    return "does not support reasoning" in message.lower()


def is_unavailable_model_response(response: httpx.Response) -> bool:
    if response.status_code not in {400, 403, 404}:
        return False
    message = get_error_message(response).lower()
    return any(marker in message for marker in ("model", "not found", "not supported", "permission", "access"))


async def ask_yandex_gpt(messages: list[dict[str, str]], model: str | None = None) -> str:
    if not settings.yandex_gpt_api_key or not settings.yandex_gpt_folder_id:
        raise YandexGPTError("YandexGPT is not configured")

    requested_model = (model or "yandexgpt").strip().lower()
    normalized_messages = ensure_system_message(messages)
    payload = {
        "modelUri": build_model_uri(requested_model),
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
            if requested_model != "yandexgpt" and is_unavailable_model_response(response):
                payload["modelUri"] = build_model_uri("yandexgpt")
                payload["completionOptions"] = build_completion_options(include_reasoning=True)
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
