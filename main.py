# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from dotenv import load_dotenv

# ================= Загрузка окружения =================
load_dotenv()

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# ================= Логирование =================
logging.basicConfig(level=logging.INFO)

# ================= Инициализация =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= Обработчики =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Я оживляю фото 😎\n"
        "Отправь мне фотографию, и я покажу, как она оживает после оплаты 100₽."
    )

@dp.message(F.photo)  # <-- заменили content_types на F.photo
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    photo_path = "user_photo.jpg"
    await photo.download(destination_file=photo_path)
    await message.reply("Фото получено! Чтобы оживить фото, пожалуйста, оплатите 100₽.")

    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        payload = {
            "version": "model_version_id",  # Укажи ID модели Replicate
            "input": {
                "image": photo_path,  # В реальности сюда передаётся URL или base64
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

# ================= Запуск =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
