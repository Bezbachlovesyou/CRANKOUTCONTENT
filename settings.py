"""Settings UI. Persistent values are stored in PostgreSQL, per Telegram owner."""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    posting_window: str = "09:00–21:00"
    posts_per_day: str = "5–10"
    post_gap_minutes: int = 40
    reply_window: str = "09:00–23:00"
    replies_per_day: str = "10–20"
    timezone: str = "Europe/Moscow"


FIELDS = {
    "posting_window": ("🕘 Изменить окно постинга", "Введите часы постинга, например 09:00–21:00."),
    "posts_per_day": ("🔢 Изменить постов в день", "Введите диапазон постов в день, например 5–10."),
    "post_gap_minutes": ("⏱ Изменить зазор между постами", "Введите минимальный интервал в минутах, например 40."),
    "reply_window": ("💬 Изменить часы автоответа", "Введите часы автоответа, например 09:00–23:00."),
    "replies_per_day": ("📈 Изменить лимит автоответа", "Введите диапазон автоответов в день, например 10–20."),
    "timezone": ("🌍 Изменить часовой пояс", "Введите часовой пояс, например Europe/Moscow."),
}


class EditSettings(StatesGroup):
    value = State()


def is_owner(user_id: int) -> bool:
    return str(user_id) == os.environ.get("ADMIN_TELEGRAM_ID", "").strip()


async def connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return await asyncpg.connect(url, timeout=10, command_timeout=10)


async def load_settings(owner_id: int) -> Settings:
    conn = await connection()
    try:
        value = await conn.fetchval(
            "SELECT values_json FROM copilot_settings WHERE owner_id=$1", owner_id
        )
        return Settings(**json.loads(value)) if value else Settings()
    finally:
        await conn.close()


async def save_field(owner_id: int, field: str, value) -> None:
    if field not in FIELDS:
        raise ValueError("Unknown setting")
    conn = await connection()
    try:
        # Merge the edited field atomically so concurrent edits keep other values.
        await conn.execute(
            """INSERT INTO copilot_settings(owner_id, values_json)
               VALUES ($1, $2::jsonb || $3::jsonb)
               ON CONFLICT (owner_id) DO UPDATE
               SET values_json=copilot_settings.values_json || $3::jsonb,
                   updated_at=now()""",
            owner_id, json.dumps(asdict(Settings())), json.dumps({field: value}),
        )
    finally:
        await conn.close()


def parse_value(field: str, text: str):
    text = text.strip()
    if field in {"posting_window", "reply_window"}:
        match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})", text)
        if not match:
            raise ValueError("Нужен формат 09:00–21:00.")
        h1, m1, h2, m2 = map(int, match.groups())
        if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59 or (h1, m1) == (h2, m2):
            raise ValueError("Укажите разные корректные часы от 00:00 до 23:59.")
        return f"{h1:02}:{m1:02}–{h2:02}:{m2:02}"
    if field in {"posts_per_day", "replies_per_day"}:
        match = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", text)
        if not match:
            raise ValueError("Нужен диапазон, например 5–10; для фиксированного числа — 5–5.")
        low, high = map(int, match.groups())
        if not 0 <= low <= high <= 250:
            raise ValueError("Нужен диапазон от 0 до 250, по возрастанию.")
        return f"{low}–{high}"
    if field == "post_gap_minutes":
        if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= 1440:
            raise ValueError("Введите целое число от 1 до 1440 минут.")
        return int(text)
    if field == "timezone":
        try:
            ZoneInfo(text)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Неизвестный часовой пояс. Пример: Europe/Moscow.") from None
        return text
    raise ValueError("Неизвестная настройка.")


def settings_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔌 Аккаунт для постинга", callback_data="settings:account")]]
    rows.extend(
        [InlineKeyboardButton(text=label, callback_data=f"settings:{field}")]
        for field, (label, _) in FIELDS.items()
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_settings(value: Settings, saved: bool) -> str:
    return (
        "⚙️ Настройки\n\n"
        f"Постинг\n🕘 Окно: {value.posting_window}\n"
        f"🔢 Постов в день: {value.posts_per_day}\n"
        f"⏱ Зазор: от {value.post_gap_minutes} мин\n\n"
        f"Автоответ\n💬 Часы: {value.reply_window}\n"
        f"📈 Лимит: {value.replies_per_day} в день\n\n"
        "Общее\n🔌 Аккаунт: подключение пока не настроено\n"
        f"🌍 Часовой пояс: {value.timezone}\n\n"
        + ("Публикации и автоответы пока не запущены."
           if saved else "Показаны значения по умолчанию. Хранилище недоступно; изменения не сохраняются.")
    )


@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id) or message.chat.type != "private":
        await message.answer("Настройки доступны владельцу бота в личном чате.")
        return
    await state.clear()
    try:
        value = await load_settings(message.from_user.id)
        saved = True
    except (RuntimeError, OSError, asyncpg.PostgresError):
        logger.warning("Settings storage unavailable")
        value, saved = Settings(), False
    await message.answer(render_settings(value, saved), reply_markup=settings_keyboard())


@router.callback_query(F.data.startswith("settings:"))
async def edit_setting(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id) or not isinstance(callback.message, Message) or callback.message.chat.type != "private":
        await callback.answer("Доступно только владельцу в личном чате.", show_alert=True)
        return
    await callback.answer()
    field = callback.data.split(":", 1)[1]
    if field == "account":
        await state.clear()
        await callback.message.answer("Подключение Threads через Zernio добавим отдельно.")
    elif field in FIELDS:
        await state.set_state(EditSettings.value)
        await state.update_data(field=field)
        await callback.message.answer(FIELDS[field][1] + "\nОтмена: /cancel.")


@router.message(EditSettings.value, Command("cancel", "start", "menu"))
async def cancel_edit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Изменение отменено. Выберите раздел в нижнем меню.")


@router.message(EditSettings.value, F.text.in_({"▶️ Постинг", "▶️ Автоответ", "📊 Статистика"}))
async def leave_edit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Изменение отменено. Нажмите выбранный раздел ещё раз.")


@router.message(EditSettings.value)
async def receive_value(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id) or message.chat.type != "private":
        await state.clear()
        return
    field = (await state.get_data())["field"]
    try:
        value = parse_value(field, message.text or "")
    except ValueError as error:
        await message.answer(str(error) + "\nПовторите ввод или /cancel.")
        return
    try:
        await save_field(message.from_user.id, field, value)
    except (RuntimeError, OSError, asyncpg.PostgresError):
        logger.warning("Cannot persist settings")
        await message.answer("Не удалось сохранить: хранилище недоступно. Повторите позже или /cancel.")
        return
    await state.clear()
    await show_settings(message, state)
