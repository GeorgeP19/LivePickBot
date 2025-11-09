# -*- coding: utf-8 -*-
import os
import logging
from aiogram import Bot, Dispatcher, types
import requests
import asyncio

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(commands=["start"])
async def start(message: types.Message):
    await message.reply("Привет! Отправь фото, и я его оживлю после оплаты 100₽.")

# Обработка фото
@dp.message(content_types=['photo'])
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    photo_path = "user_photo.jpg"
    await photo.download(destination_file=photo_path)

    await message.reply("Чтобы оживить фото, пожалуйста, оплатите 100₽.")

    # Пример запроса к Replicate (замени на свою модель)
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    with open(photo_path, "rb") as f:
        image_bytes = f.read()

    data = {
        "version": "model_version_id",
        "input": {
            "image": image_bytes.hex(),
            "prompt": "оживи фото"
        }
    }

    response = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json=data
    )

    result_url = response.json().get("output", [None])[0]
    if result_url:
        await message.reply(f"Вот ваше оживлённое фото: {result_url}")
    else:
        await message.reply("Что-то пошло не так при оживлении фото 😢")


# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
