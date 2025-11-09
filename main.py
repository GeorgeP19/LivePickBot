# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # если используем webhook

# ================= Логирование =================
logging.basicConfig(level=logging.INFO)

# ================= Инициализация бота =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= Обработчики =================

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Я оживляю фото 😎\n"
        "Отправь мне фотографию, и я покажу, как она оживает после оплаты 100₽."
    )

# Обработка фото
@dp.message(content_types=types.ContentType.PHOTO)
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    photo_path = "user_photo.jpg"
    await photo.download(destination_file=photo_path)
    await message.reply("Фото получено! Чтобы оживить фото, пожалуйста, оплатите 100₽.")

    # ================= Пример запроса к Replicate =================
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    with open(photo_path, "rb") as f:
        image_bytes = f.read()

    data = {
        "version": "model_version_id",  # Замените на вашу модель Replicate
        "input": {
            "image": image_bytes.hex(),
            "prompt": "оживи фото"
        }
    }

    try:
        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        result_url = response.json().get("output", [None])[0]

        if result_url:
            await message.reply(f"Вот ваше оживлённое фото: {result_url}")
        else:
            await message.reply("Что-то пошло не так при оживлении фото 😢")

    except Exception as e:
        await message.reply(f"Произошла ошибка при обработке фото: {e}")

# ================= Запуск бота =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
