import httpx

from app.core.config import settings


class YandexGPTError(RuntimeError):
    pass


async def ask_yandex_gpt(messages: list[dict[str, str]]) -> str:
    if not settings.yandex_gpt_api_key or not settings.yandex_gpt_folder_id:
        return (
            "YandexGPT пока не настроен. Добавьте YANDEX_GPT_API_KEY и "
            "YANDEX_GPT_FOLDER_ID в .env."
        )

    model_uri = settings.yandex_gpt_model_uri or f"gpt://{settings.yandex_gpt_folder_id}/yandexgpt/latest"
    payload = {
        "modelUri": model_uri,
        "completionOptions": {"stream": False, "temperature": 0.2, "maxTokens": "4000"},
        "messages": messages,
    }
    headers = {"Authorization": f"Api-Key {settings.yandex_gpt_api_key}"}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            json=payload,
            headers=headers,
        )

    if response.status_code >= 400:
        raise YandexGPTError("YandexGPT API is unavailable")

    data = response.json()
    return data["result"]["alternatives"][0]["message"]["text"]
