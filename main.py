# -*- coding: utf-8 -*-
import os
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from yookassa import Configuration, Payment

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например: https://your-app.onrender.com/webhook

if not all([BOT_TOKEN, REPLICATE_API_TOKEN, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, WEBHOOK_URL]):
    raise ValueError("❌ Проверьте все переменные окружения!")

# ================= Логирование =================
logging.basicConfig(level=logging.INFO)

# ================= Инициализация бота =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= Глобальная aiohttp сессия =================
session = aiohttp.ClientSession()

# ================= YouKassa =================
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# ================= Хендлеры Telegram =================

@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Я оживляю фото 😎\n"
        "Отправь мне фотографию, и я покажу, как она оживает после оплаты 100₽."
    )

@dp.message(types.Message.photo)
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    photo_path = f"user_photo_{message.from_user.id}.jpg"
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
            "return_url": WEBHOOK_URL
        },
        "capture": True,
        "description": f"Оживление фото для {message.from_user.id}"
    })

    await message.reply(f"💳 Оплатите 100₽ по ссылке: {payment.confirmation.confirmation_url}")

# ================= Webhook YouKassa =================
async def handle_payment_webhook(request):
    data = await request.json()
    logging.info(f"Получен вебхук YouKassa: {data}")
    return web.Response(text="OK")

# ================= Healthcheck =================
async def handle_healthcheck(request):
    return web.Response(text="Bot is alive")

# ================= WebService =================
app = web.Application()
app.add_routes([
    web.get("/", handle_healthcheck),
    web.post("/webhook", bot.webhook_handler()),
    web.post("/payment", handle_payment_webhook)
])

# Закрытие сессий при завершении
async def on_cleanup(app):
    await session.close()
    await bot.session.close()

app.on_cleanup.append(on_cleanup)

# ================= Запуск =================
if __name__ == "__main__":
    import asyncio
    import logging

    logging.info("✅ Запуск бота через WebService на Render")
    
    # Telegram Webhook
    async def setup_webhook():
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_webhook())
    
    # Запуск aiohttp сервера
    web.run_app(app, host="0.0.0.0", port=10000)
