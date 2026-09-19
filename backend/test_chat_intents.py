import unittest

from app.catalogs.chat_intents import detect_contract_message_intent, strip_addition_command


class ChatIntentTests(unittest.TestCase):
    def test_recognizes_contract_additions(self):
        additions = (
            "Добавь положение о запрете курения",
            "включи условие о рассрочке депозита",
            "Хочу добавить право посещать квартиру",
            "Измени пункт об оплате",
        )
        for message in additions:
            with self.subTest(message=message):
                self.assertEqual(detect_contract_message_intent(message), "addition")

    def test_recognizes_transition_to_agreement(self):
        for message in ("нет", "Вопросов нет", "Все понятно", "Переходим к согласованию"):
            with self.subTest(message=message):
                self.assertEqual(detect_contract_message_intent(message), "agreement")

    def test_treats_remaining_messages_as_questions(self):
        self.assertEqual(
            detect_contract_message_intent("Может ли наймодатель повысить плату?"),
            "question",
        )

    def test_strips_natural_addition_command(self):
        self.assertEqual(
            strip_addition_command("Добавь положение о запрете курения"),
            "положение о запрете курения",
        )


if __name__ == "__main__":
    unittest.main()
