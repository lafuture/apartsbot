import os
import asyncio
import argparse
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta

import dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from db import init_db, get_new_aparts
from dotenv import load_dotenv

print(f"[bot] DB_URL: {os.getenv('DB_URL')}")
print(f"[bot] TELEGRAM_TOKEN: {'установлен' if os.getenv('TELEGRAM_TOKEN') else 'НЕ установлен'}")

@dataclass
class UserState:
    """
    Хранит состояние одного пользователя бота:
    настройки фильтров и флаг активного поиска.

    :ivar waiting_for_price: Ожидается ли ввод диапазона цены.
    :type waiting_for_price: bool
    :ivar min_price: Минимальная цена фильтра, если задана.
    :type min_price: int | None
    :ivar max_price: Максимальная цена фильтра, если задана.
    :type max_price: int | None
    :ivar waiting_for_rooms: Ожидается ли ввод количества комнат.
    :type waiting_for_rooms: bool
    :ivar rooms: Список выбранных вариантов комнат (0 = студия).
    :type rooms: list[int] | None
    :ivar searching: Признак активного фонового поиска объявлений.
    :type searching: bool
    :ivar since: Метка времени, начиная с которой ищутся новые объявления.
    :type since: datetime | None
    """
    waiting_for_price: bool = False
    min_price: int | None = None
    max_price: int | None = None
    waiting_for_rooms: bool = False
    rooms: list[int] | None = None
    searching: bool = False
    since: datetime | None = None


user_states: dict[int, UserState] = {}


def get_state(chat_id: int) -> UserState:
    """
    Возвращает состояние пользователя по chat_id,
    создавая его при первом обращении.

    :param chat_id: Идентификатор чата Telegram.
    :type chat_id: int
    :returns: Объект состояния пользователя для данного чата.
    :rtype: UserState
    """
    if chat_id not in user_states:
        user_states[chat_id] = UserState()
    return user_states[chat_id]


def main_keyboard(state: UserState) -> InlineKeyboardMarkup:
    """
    Строит основную inline-клавиатуру с текущими настройками фильтров.
    Клавиатура включает кнопки для установки диапазона цены, выбора
    количества комнат и запуска поиска.

    :param state: Текущее состояние пользователя.
    :type state: UserState
    :returns: Объект inline-клавиатуры для главного меню.
    :rtype: InlineKeyboardMarkup
    """
    if state.min_price or state.max_price:
        parts = []
        if state.min_price:
            parts.append(f"от {state.min_price}")
        if state.max_price:
            parts.append(f"до {state.max_price}")
        price_text = "💲 Цена: " + " ".join(parts)
    else:
        price_text = "💲 Установить цену"

    if state.rooms:
        rooms_str = ", ".join(
            ["студия" if r == 0 else f"{r}" for r in state.rooms]
        )
        rooms_text = "🏠 Комнаты: " + rooms_str
    else:
        rooms_text = "🏠 Установить комнаты"

    kb = [
        [InlineKeyboardButton(text=price_text, callback_data="set_price")],
        [InlineKeyboardButton(text=rooms_text, callback_data="set_rooms")],
        [InlineKeyboardButton(text="▶️ Запустить поиск", callback_data="start_search")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def stop_keyboard() -> InlineKeyboardMarkup:
    """
    Строит inline-клавиатуру с одной кнопкой для остановки поиска.

    :returns: Клавиатура с кнопкой «Остановить поиск».
    :rtype: InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⛔ Остановить поиск", callback_data="stop_search")]
        ]
    )


async def cmd_start(message: Message):
    """
    Обрабатывает команду /start и отправляет приветственное сообщение
    с инструкциями и основной клавиатурой.

    :param message: Входящее сообщение с командой /start.
    :type message: Message
    """
    try:
        state = get_state(message.chat.id)
        text = (
            "Привет! Я бот, который шлёт новые объявления о недвижимости с Авито.\n\n"
            "Настрой фильтры и запусти поиск!"
        )
        await message.answer(text, reply_markup=main_keyboard(state))
    except Exception as e:
        print(f"[cmd_start] Ошибка: {e}")
        try:
            await message.answer("Произошла ошибка. Попробуйте позже.")
        except Exception:
            pass


async def on_callback(callback: CallbackQuery, bot: Bot):
    """
    Обрабатывает нажатия на inline-кнопки в основном меню бота.
    В зависимости от callback_data переводит пользователя в режим
    ввода цены или комнат, запускает или останавливает поиск.

    :param callback: Объект callback-запроса от Telegram.
    :type callback: CallbackQuery
    :param bot: Экземпляр бота для отправки сообщений.
    :type bot: Bot
    """
    try:
        chat_id = callback.message.chat.id
        state = get_state(chat_id)

        if callback.data == "set_price":
            state.waiting_for_price = True
            state.waiting_for_rooms = False
            await callback.message.answer(
                "Введи диапазон цены, например:\n"
                "30000-60000\n"
                "Или только минимум, например:\n"
                "40000"
            )
            await callback.answer()
            return

        if callback.data == "set_rooms":
            state.waiting_for_rooms = True
            state.waiting_for_price = False
            await callback.message.answer(
                "Введи список комнат через запятую.\n"
                "Примеры:\n"
                "студия и 1-2к: 0,1,2\n"
                "только 2 и 3к: 2,3"
            )
            await callback.answer()
            return

        if callback.data == "start_search":
            if state.searching:
                await callback.answer("Поиск уже запущен", show_alert=True)
                return

            state.searching = True
            state.since = datetime.now(UTC) - timedelta(minutes=1)
            await callback.message.answer(
                "Поиск запущен.\n"
                "Будут приходить новые объявления.",
                reply_markup=stop_keyboard()
            )
            await callback.answer()
            asyncio.create_task(search_loop(bot, chat_id))
            return

        if callback.data == "stop_search":
            if not state.searching:
                await callback.answer("Поиск уже остановлен")
                return

            state.searching = False
            await callback.message.answer("Поиск остановлен.")
            await callback.answer()
            return

        await callback.answer("Неизвестная команда")

    except Exception as e:
        print(f"[on_callback] Ошибка: {e}")
        try:
            await callback.answer("Произошла ошибка", show_alert=True)
        except Exception:
            pass


async def on_message(message: Message):
    """
    Обрабатывает входящие текстовые сообщения пользователей.
    В зависимости от текущего состояния пользователя воспринимает
    сообщение как ввод цены, комнат или команду /start.

    :param message: Входящее текстовое сообщение от пользователя.
    :type message: Message
    """
    try:
        chat_id = message.chat.id
        state = get_state(chat_id)

        if message.text == "/start":
            await cmd_start(message)
            return

        if state.waiting_for_price:
            try:
                raw = message.text.replace(" ", "")
                min_p = None
                max_p = None

                if "-" in raw:
                    left, right = raw.split("-", maxsplit=1)
                    if left:
                        try:
                            min_p = int(left)
                        except ValueError:
                            min_p = None
                    if right:
                        try:
                            max_p = int(right)
                        except ValueError:
                            max_p = None
                else:
                    try:
                        min_p = int(raw)
                    except ValueError:
                        min_p = None

                state.min_price = min_p
                state.max_price = max_p
                state.waiting_for_price = False

                await message.answer(
                    f"Фильтр по цене обновлён.\n"
                    f"Минимум: {state.min_price or '—'}\n"
                    f"Максимум: {state.max_price or '—'}",
                    reply_markup=main_keyboard(state),
                )
            except Exception as e:
                print(f"[on_message] Ошибка обработки цены: {e}")
                await message.answer("Ошибка обработки. Попробуйте снова.")
            return

        if state.waiting_for_rooms:
            try:
                raw = message.text.replace(" ", "")
                rooms_list: list[int] = []

                if raw:
                    for part in raw.split(","):
                        if not part:
                            continue
                        try:
                            val = int(part)
                            rooms_list.append(val)
                        except ValueError:
                            continue

                state.rooms = rooms_list or None
                state.waiting_for_rooms = False

                if state.rooms:
                    rooms_str = ", ".join(
                        ["студия" if r == 0 else f"{r}" for r in state.rooms]
                    )
                    txt = f"Фильтр по комнатам обновлён.\nКомнаты: {rooms_str}"
                else:
                    txt = "Фильтр по комнатам сброшен."

                await message.answer(txt, reply_markup=main_keyboard(state))
            except Exception as e:
                print(f"[on_message] Ошибка обработки комнат: {e}")
                await message.answer("Ошибка обработки. Попробуйте снова.")
            return

        await message.answer("Используй /start для начала.")

    except Exception as e:
        print(f"[on_message] Критическая ошибка: {e}")
        try:
            await message.answer("Произошла ошибка. Попробуйте /start")
        except Exception:
            pass


async def search_loop(bot: Bot, chat_id: int):
    """
    Цикл фонового поиска новых объявлений для конкретного пользователя.
    Периодически опрашивает базу данных на наличие новых объявлений,
    соответствующих фильтрам пользователя, и отправляет их в чат.

    :param bot: Экземпляр бота для отправки сообщений.
    :type bot: Bot
    :param chat_id: Идентификатор чата пользователя.
    :type chat_id: int
    """
    state = get_state(chat_id)

    try:
        if state.since is None:
            state.since = datetime.now(UTC)
        elif state.since.tzinfo is None:
            state.since = state.since.replace(tzinfo=UTC)

        print(f"[search_loop] СТАРТ для чата {chat_id}, since={state.since!r}")
        print(f"[search_loop] Фильтры: min={state.min_price}, max={state.max_price}, rooms={state.rooms}")

        while state.searching:
            try:
                ads = get_new_aparts(
                    min_price=state.min_price,
                    max_price=state.max_price,
                    rooms=state.rooms,
                    since=state.since,
                    limit=100,
                )

                print(f"[search_loop] since={state.since!r}, найдено {len(ads)} объявлений")

                if len(ads) == 100:
                    print(f"[WARNING] Достигнут лимит 100! Возможно есть еще объявления!")

                if ads:
                    for ad in ads:
                        try:
                            text = (
                                f"Цена: {ad['price']} ₽\n"
                                f"Комнат: {ad['rooms']}\n"
                                f"{ad['title']}\n"
                                f"{ad['link']}"
                            )
                            await bot.send_message(chat_id, text, reply_markup=stop_keyboard())
                        except Exception as e:
                            print(f"[search_loop] Ошибка отправки сообщения: {e}")

                    max_created_at = max(ad["created_at"] for ad in ads)
                    if max_created_at.tzinfo is None:
                        max_created_at = max_created_at.replace(tzinfo=UTC)
                    state.since = max_created_at
                    print(f"[search_loop] обновлен since до {state.since!r}")

                await asyncio.sleep(int(os.getenv("PARSE_INTERVAL", "300")))

            except Exception as e:
                print(f"[search_loop] ошибка в итерации для чата {chat_id}: {e}")
                await asyncio.sleep(int(os.getenv("PARSE_INTERVAL", "300")))

        print(f"[search_loop] выход из цикла для чата {chat_id}")

    except Exception as e:
        print(f"[search_loop] критическая ошибка для чата {chat_id}: {e}")
        try:
            await bot.send_message(
                chat_id,
                "Произошла критическая ошибка в поиске. Перезапустите поиск."
            )
        except Exception:
            pass


async def main():
    """
    Точка входа бота: инициализирует БД, создаёт бота и диспетчер
    и запускает long polling.

    :raises RuntimeError: Если переменная окружения TELEGRAM_TOKEN не задана.
    """
    try:
        init_db()

        bot = Bot(str(os.getenv("TELEGRAM_TOKEN")))
        dp = Dispatcher()

        dp.message.register(cmd_start, Command("start"))
        dp.callback_query.register(
            on_callback,
            F.data.in_({"set_price", "set_rooms", "start_search", "stop_search"}),
        )
        dp.message.register(on_message, F.text)

        print("[bot] Запуск polling...")
        await dp.start_polling(bot)

    except Exception as e:
        print(f"[bot] Критическая ошибка: {e}")
        raise RuntimeError(f"Не удалось запустить бота: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[bot] Бот остановлен пользователем")
    except Exception as e:
        print(f"\n[bot] Фатальная ошибка: {e}")
        exit(1)
