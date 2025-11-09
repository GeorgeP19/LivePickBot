# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from yookassa import Configuration, Payment

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

if not BOT_TOKEN or not REPLICATE_API_TOKEN or not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
    raise ValueError("❌ Проверьте все переменные окружения: BOT_TOKEN, REPLICATE_API_TOKEN, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY")

# ================= Логирование =================
logging.basicConfig(level=logging.INFO)

# ================= Инициализация бота =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройки YouKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# ================= Хендлер /start =================
@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Я оживляю фото 😎\n"
        "Отправь мне фотографию, и я покажу, как она оживает после оплаты 100₽."
    )

# ================= Хендлер фото =================
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    photo = message.photo[-1]  # берём самое большое
    photo_path = f"user_photo_{message.from_user.id}.jpg"
    
    # Скачиваем фото
    await bot.download(photo.file_id, photo_path)
    await message.reply("Фото получено! Создаём счёт на оплату 100₽...")

    # Создаём платёж через YouKassa
    payment = Payment.create({
        "amount": {
            "value": "100.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/LivePicBot_bot"
        },
        "capture": True,
        "description": f"Оживление фото для {message.from_user.id}"
    })

    await message.reply(f"💳 Оплатите 100₽ по ссылке: {payment.confirmation.confirmation_url}")

    # ================= Ждём оплаты (в реальном проекте нужен webhook) =================
    await message.reply("После оплаты пришлите любое сообщение, чтобы получить результат.")

# ================= Хендлер подтверждения =================
@dp.message(F.text)
async def process_payment(message: types.Message):
    await message.reply("Проверяем оплату и оживляем фото...")

    # ================= Пример запроса к Replicate =================
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    # Пример payload — замените на вашу модель
    payload = {
        "version": "model_version_id",  # Замените на вашу модель Replicate
        "input": {
            "image": f"https://example.com/user_photo.jpg",  # В проде лучше загружать фото на сервер или S3
            "prompt": "оживи фото"
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json=payload
        ) as response:
            if response.status == 200:
                result = await response.json()
                result_url = result.get("output", [None])[0]

                if result_url:
                    await message.reply(f"Вот ваше оживлённое фото: {result_url}")
                else:
                    await message.reply("Что-то пошло не так при оживлении фото 😢")
            else:
                await message.reply("Ошибка при запросе к API Replicate.")

# ================= WebService для Render =================
async def handle_healthcheck(request):
    return web.Response(text="Bot is alive")

async def main():
    # WebService
    app = web.Application()
    app.add_routes([web.get("/", handle_healthcheck)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

    # Polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
