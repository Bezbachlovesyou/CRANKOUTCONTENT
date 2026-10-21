"""Threads Copilot: Telegram menu entry point."""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

POSTING = "▶️ Постинг"
AUTOREPLY = "▶️ Автоответ"
STATISTICS = "📊 Статистика"
SETTINGS = "⚙️ Настройки"

router = Router()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=POSTING), KeyboardButton(text=AUTOREPLY)],
            [KeyboardButton(text=STATISTICS), KeyboardButton(text=SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие в меню",
    )


@router.message(Command("start", "menu"))
async def show_menu(message: Message) -> None:
    await message.answer(
        "Threads Copilot\nВыберите действие в меню ниже.", reply_markup=main_menu()
    )


@router.message(F.text == POSTING)
async def posting(message: Message) -> None:
    await message.answer(
        "▶️ Постинг\nНастроим запуск публикаций на следующем этапе.",
        reply_markup=main_menu(),
    )


@router.message(F.text == AUTOREPLY)
async def autoreply(message: Message) -> None:
    await message.answer(
        "▶️ Автоответ\nНастроим автоматические ответы на следующем этапе.",
        reply_markup=main_menu(),
    )


@router.message(F.text == STATISTICS)
async def statistics(message: Message) -> None:
    await message.answer(
        "📊 Статистика\nЭтот раздел пока в разработке.", reply_markup=main_menu()
    )


@router.message(F.text == SETTINGS)
async def settings(message: Message) -> None:
    await message.answer(
        "⚙️ Настройки\nЭтот раздел пока в разработке.", reply_markup=main_menu()
    )


async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN before starting the bot")
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    async with Bot(token=token) as bot:
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
