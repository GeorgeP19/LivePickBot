# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command  # <-- правильный импорт
from dotenv import load_dotenv

# ================= Загрузка окружения =================
load_dotenv()

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

    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    # ⚙️ Асинхронный запрос к Replicate
    async with aiohttp.ClientSession() as session:
        payload = {
            "version": "model_version_id",  # вставь ID модели Replicate
            "input": {
                "image": photo_path,  # должен быть URL или base64
                "prompt": "оживи фото"
            }
        }

        async with session.post("https://api.replicate.com/v1/predictions",
                                headers=headers, json=payload) as response:
            if response.status == 200:
                result = await response.json()
                result_url = result.get("output", [None])[0]
                if result_url:
                    await message.reply(f"Вот ваше оживлённое фото: {result_url}")
                else:
                    await message.reply("Что-то пошло не так при оживлении фото 😢")
            else:
                text = await response.text()
                await message.reply(f"Ошибка Replicate: {response.status}\n{text}")

# ================= Запуск бота =================
async def main():
    await dp.start_polling(bot)  # <-- нужно передавать bot в polling

if __name__ == "__main__":
    asyncio.run(main())
