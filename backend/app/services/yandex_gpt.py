import httpx

from app.core.config import settings


class YandexGPTError(RuntimeError):
    pass


async def ask_yandex_gpt(messages: list[dict[str, str]]) -> str:
    if not settings.yandex_gpt_api_key or not settings.yandex_gpt_folder_id:
        raise YandexGPTError("YandexGPT is not configured")

    model_uri = settings.yandex_gpt_model_uri or f"gpt://{settings.yandex_gpt_folder_id}/yandexgpt/latest"
    payload = {
        "modelUri": model_uri,
        "completionOptions": {"stream": False, "temperature": 0.2, "maxTokens": "4000"},
        "messages": messages,
    }
    headers = {"Authorization": f"Api-Key {settings.yandex_gpt_api_key}"}

    try:
        timeout = httpx.Timeout(90.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
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
