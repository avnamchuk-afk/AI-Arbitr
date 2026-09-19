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


def model_fallback_order(model: str | None = None) -> tuple[str, ...]:
    requested = (model or "yandexgpt").strip().lower()
    if requested not in SUPPORTED_MODELS:
        requested = "yandexgpt"
    alternate = "qwen" if requested == "yandexgpt" else "yandexgpt"
    return requested, alternate


def should_try_fallback(response: httpx.Response) -> bool:
    return response.status_code in {408, 429} or response.status_code >= 500 or is_unavailable_model_response(response)


async def ask_yandex_gpt(messages: list[dict[str, str]], model: str | None = None) -> str:
    if not settings.yandex_gpt_api_key or not settings.yandex_gpt_folder_id:
        raise YandexGPTError("YandexGPT is not configured")

    normalized_messages = ensure_system_message(messages)
    headers = {
        "Authorization": f"Api-Key {settings.yandex_gpt_api_key}",
        "Content-Type": "application/json",
        "x-folder-id": settings.yandex_gpt_folder_id,
    }

    timeout = httpx.Timeout(90.0, connect=10.0)
    last_error: Exception | None = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for index, model_key in enumerate(model_fallback_order(model)):
                payload = {
                    "modelUri": build_model_uri(model_key),
                    "completionOptions": build_completion_options(include_reasoning=True),
                    "messages": normalized_messages,
                }
                try:
                    response = await client.post(
                        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                        json=payload,
                        headers=headers,
                    )
                except (httpx.TimeoutException, httpx.HTTPError) as exc:
                    last_error = exc
                    if index == 0:
                        continue
                    break
                if is_unsupported_reasoning_response(response):
                    payload["completionOptions"] = build_completion_options(include_reasoning=False)
                    try:
                        response = await client.post(
                            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                            json=payload,
                            headers=headers,
                        )
                    except (httpx.TimeoutException, httpx.HTTPError) as exc:
                        last_error = exc
                        if index == 0:
                            continue
                        break
                if response.status_code < 400:
                    try:
                        data = response.json()
                        return data["result"]["alternatives"][0]["message"]["text"]
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        last_error = exc
                        if index == 0:
                            continue
                        break
                if index == 0 and should_try_fallback(response):
                    continue
                break
    except httpx.TimeoutException as exc:
        last_error = exc
    except httpx.HTTPError as exc:
        last_error = exc

    raise YandexGPTError("All configured language models are unavailable") from last_error
