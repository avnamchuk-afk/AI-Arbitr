import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.yandex_gpt import ask_yandex_gpt, model_fallback_order


class AiGatewayTests(unittest.TestCase):
    def test_yandex_falls_back_to_qwen(self):
        self.assertEqual(model_fallback_order("yandexgpt"), ("yandexgpt", "qwen"))

    def test_qwen_falls_back_to_yandex(self):
        self.assertEqual(model_fallback_order("qwen"), ("qwen", "yandexgpt"))

    def test_unknown_model_uses_supported_pair(self):
        self.assertEqual(model_fallback_order("unknown"), ("yandexgpt", "qwen"))


class AiGatewayFallbackTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.yandex_gpt.settings")
    @patch("app.services.yandex_gpt.httpx.AsyncClient")
    async def test_quota_error_tries_alternate_model(self, async_client, settings):
        settings.yandex_gpt_api_key = "test-key"
        settings.yandex_gpt_folder_id = "folder"
        settings.yandex_gpt_model_uri = ""

        quota_response = MagicMock(status_code=429)
        quota_response.json.return_value = {"error": {"message": "quota exceeded"}}
        success_response = MagicMock(status_code=200)
        success_response.json.return_value = {
            "result": {"alternatives": [{"message": {"text": "Готово"}}]}
        }
        client = AsyncMock()
        client.post.side_effect = [quota_response, success_response]
        async_client.return_value.__aenter__.return_value = client

        answer = await ask_yandex_gpt([{"role": "user", "text": "Запрос"}], model="yandexgpt")

        self.assertEqual(answer, "Готово")
        self.assertEqual(client.post.await_count, 2)
        first_payload = client.post.await_args_list[0].kwargs["json"]
        second_payload = client.post.await_args_list[1].kwargs["json"]
        self.assertIn("yandexgpt-5.1", first_payload["modelUri"])
        self.assertIn("qwen2.5-7b-instruct", second_payload["modelUri"])


if __name__ == "__main__":
    unittest.main()
