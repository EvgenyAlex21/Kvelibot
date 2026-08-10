import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode

from processor import process_list, get_closing_times, get_time_slots

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не задан. Укажите в .env или переменных окружения.")
    sys.exit(1)

PROXY_URL = (
    os.getenv("HTTPS_PROXY")
    or os.getenv("HTTP_PROXY")
    or os.getenv("SOCKS_PROXY")
    or os.getenv("PROXY_URL")
    or ""
).strip()

def create_bot(use_proxy: bool = True) -> Bot:
    if use_proxy and PROXY_URL:
        try:
            from aiogram.client.session.aiohttp import AiohttpSession
            session = AiohttpSession(proxy=PROXY_URL)
            logger.info("Подключение через прокси: %s", PROXY_URL.split("@")[-1])
            return Bot(token=BOT_TOKEN, session=session)
        except Exception as e:
            logger.warning("Не удалось создать сессию с прокси: %s", e)
            logger.info("Пробую без прокси...")

    logger.info("Прямое подключение (без прокси)")
    return Bot(token=BOT_TOKEN)

dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    slots = get_time_slots()
    slots_str = ", ".join(f"<b>{s}</b>" for s in slots)
    await message.answer(
        "👋 Привет! Я бот для сортировки списков развоза.\n\n"
        "Просто пришли мне НЕотсортированный список (как обычно пишете), "
        "и я верну красивый отсортированный по районам и времени.\n\n"
        f"Сейчас доступные слоты: {slots_str}.\n\n"
        "Команды:\n"
        "/start — это сообщение\n"
        "/help — подробная справка\n"
        "/times — текущие времена закрытия",
        parse_mode=ParseMode.HTML,
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = """
📋 <b>Как пользоваться</b>

1. Скопируй весь несортированный список (с именами секций: Галина, Anya, Михаил и т.д.)
2. Пришли его боту одним сообщением
3. Получи готовый список с:
   • Автоматической расстановкой «Имя - Адрес»
   • Определением района
   • Группировкой по времени
   • Подсчётом людей в каждом районе
   • Разделением по водителям
   • Богданкой у того водителя, у кого меньше людей
   • Неопределёнными адресами в самом низу

<b>Водители:</b>
1 — СЗР + ЮЗР
2 — [Богданка?] + Центр + Новый + НЧК
3 — [Богданка?] + НЮР + Кугеси

Если адрес не распознан — попадёт в «НЕОПРЕДЕЛЕНО».
"""
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(Command("times"))
async def cmd_times(message: types.Message):
    from datetime import datetime

    now = datetime.now()
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    slots = get_time_slots()
    slots_lines = "\n".join(f"• до <b>{s}</b>" for s in slots)
    await message.answer(
        f"📅 Сегодня: <b>{days[now.weekday()]}</b> {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Доступные списки:\n{slots_lines}",
        parse_mode=ParseMode.HTML,
    )

@dp.message(F.text)
async def handle_list(message: types.Message):
    raw = message.text.strip()
    if len(raw) < 20:
        await message.answer("Слишком короткий текст. Пришли полный список.")
        return

    await message.answer("⏳ Обрабатываю список...")

    try:
        result = process_list(raw)
        if len(result) > 4000:
            parts = []
            current = ""
            for line in result.splitlines():
                if len(current) + len(line) + 1 > 4000:
                    parts.append(current)
                    current = line + "\n"
                else:
                    current += line + "\n"
            if current:
                parts.append(current)
            for part in parts:
                await message.answer(f"<pre>{part}</pre>", parse_mode=ParseMode.HTML)
        else:
            await message.answer(f"<pre>{result}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.exception("Ошибка обработки")
        await message.answer(
            f"❌ Ошибка при обработке:\n<code>{e}</code>\n\n"
            "Пришли список ещё раз или проверь формат.",
            parse_mode=ParseMode.HTML,
        )

async def try_start(bot: Bot) -> bool:
    try:
        me = await bot.get_me()
        logger.info("Бот @%s подключён успешно", me.username)
        await dp.start_polling(bot)
        return True
    except Exception as e:
        logger.error("Ошибка подключения: %s", e)
        try:
            await bot.session.close()
        except Exception:
            pass
        return False

async def main():
    logger.info("Бот запускается...")

    if PROXY_URL:
        logger.info("Способ 1: подключение через прокси...")
        bot = create_bot(use_proxy=True)
        if await try_start(bot):
            return
        logger.warning("Прокси не сработал, пробую без прокси...")

    logger.info("Способ 2: прямое подключение...")
    bot = create_bot(use_proxy=False)
    if await try_start(bot):
        return

    logger.error(
        "Не удалось подключиться ни одним способом.\n"
        "Проверьте:\n"
        "  1. BOT_TOKEN в .env\n"
        "  2. Интернет / VPN\n"
        "  3. Если нужен прокси — правильный HTTPS_PROXY или SOCKS_PROXY в .env\n"
        "     Пример: HTTPS_PROXY=http://127.0.0.1:7890"
    )
    sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())