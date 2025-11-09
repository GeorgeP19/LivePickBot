# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yookassa import Configuration, Payment

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например: https://your-app.onrender.com/webhook

if not all([BOT_TOKEN, REPLICATE_API_TOKEN, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, WEBHOOK_URL]):
    raise ValueError("❌ Проверьте все переменные окружения!")

# ================= Логирование =================
logging.basicConfig(level=logging.INFO)

# ================= Инициализация бота =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= Глобальная сессия aiohttp =================
session = aiohttp.ClientSession()

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
    photo = message.photo[-1]  # самое большое фото
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

# ================= Хендлер подтверждения оплаты =================
# В реальном проекте нужно настроить webhook YouKassa, который будет POST на /payment
async def handle_payment_webhook(request):
    data = await request.json()
    logging.info(f"Получен вебхук YouKassa: {data}")
    return web.Response(text="OK")

# ================= Хендлер здоровья =================
async def handle_healthcheck(request):
    return web.Response(text="Bot is alive")

# ================= WebService для Render =================
async def main():
    # Установка webhook для Telegram
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

    app = web.Application()
    app.add_routes([
        web.get("/", handle_healthcheck),
        web.post("/webhook", bot.webhook_handler()),  # Telegram отправляет апдейты сюда
        web.post("/payment", handle_payment_webhook)  # YouKassa вебхук
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)  # порт Render
    await site.start()

    logging.info("✅ Bot is running via webhook on Render")
    
    try:
        while True:
            await asyncio.sleep(3600)  # держим приложение живым
    finally:
        await session.close()  # ✅ Закрываем глобальную сессию при завершении
        await bot.session.close()  # Закрываем сессию бота

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
