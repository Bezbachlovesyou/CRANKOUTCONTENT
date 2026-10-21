import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import bot
import settings


class Session(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, client, method, timeout=None):
        if isinstance(method, AnswerCallbackQuery):
            return True
        assert isinstance(method, SendMessage)
        self.sent.append(method)
        return Message(message_id=1, date=datetime.now(timezone.utc),
                       chat=Chat(id=1, type="private"), text=method.text)

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b""


class SettingsTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(settings.parse_value("posting_window", "9:00-21:00"), "09:00–21:00")
        self.assertEqual(settings.parse_value("reply_window", "23:00–01:00"), "23:00–01:00")
        self.assertEqual(settings.parse_value("posts_per_day", "0-5"), "0–5")
        for field, value in [("posting_window", "25:00–26:00"),
                             ("reply_window", "09:00–09:00"),
                             ("posts_per_day", "10–5"),
                             ("replies_per_day", "1–251"),
                             ("post_gap_minutes", "0"),
                             ("timezone", "Made/Up")]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                settings.parse_value(field, value)

    def test_keyboard(self):
        labels = [b.text for row in settings.settings_keyboard().inline_keyboard for b in row]
        self.assertEqual(len(labels), 7)
        self.assertFalse(any("Контент-план" in x or "Персона" in x for x in labels))

    def test_owner_required(self):
        with patch.dict(os.environ, {"ADMIN_TELEGRAM_ID": ""}):
            self.assertFalse(settings.is_owner(1))


class SettingsFlow(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_edit_failure_retry_and_cancel(self):
        session = Session()
        client = Bot(token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
        dispatcher = Dispatcher()
        dispatcher.include_router(bot.router)
        seq = 0

        async def feed(text=None, callback=None, user_id=1):
            nonlocal seq
            seq += 1
            user = User(id=user_id, is_bot=False, first_name="Test")
            message = Message(message_id=seq, date=datetime.now(timezone.utc),
                              chat=Chat(id=user_id, type="private"), from_user=user, text=text)
            update = (Update(update_id=seq, callback_query=CallbackQuery(
                id=str(seq), from_user=user, chat_instance="test", data=callback, message=message))
                if callback else Update(update_id=seq, message=message))
            await dispatcher.feed_update(client, update)

        with patch.dict(os.environ, {"ADMIN_TELEGRAM_ID": "1"}), \
                patch.object(settings, "load_settings", AsyncMock(return_value=settings.Settings())), \
                patch.object(settings, "save_field", AsyncMock()) as save:
            await feed("⚙️ Настройки", user_id=2)
            self.assertIn("владельцу", session.sent[-1].text)
            await feed("⚙️ Настройки")
            self.assertIn("Окно: 09:00–21:00", session.sent[-1].text)
            await feed(callback="settings:post_gap_minutes")
            await feed("0")
            save.assert_not_awaited()
            save.side_effect = RuntimeError("offline")
            await feed("60")
            self.assertIn("Не удалось сохранить", session.sent[-1].text)
            save.side_effect = None
            await feed("60")
            save.assert_awaited_with(1, "post_gap_minutes", 60)
            await feed(callback="settings:timezone")
            await feed("/start")
            await feed("Europe/Moscow")
            self.assertEqual(save.await_count, 2)
            await feed(callback="settings:timezone")
            await feed("/cancel")
            self.assertIn("отменено", session.sent[-1].text)
        await client.session.close()


if __name__ == "__main__":
    unittest.main()
