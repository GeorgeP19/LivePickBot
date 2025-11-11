import os
import threading
import time
import requests
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Конфигурация (будет брать из переменных окружения)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
YUKASSA_API_TOKEN = os.environ.get('YUKASSA_API_TOKEN')
REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN')
REPLICATE_MODEL_VERSION_ID = os.environ.get('REPLICATE_MODEL_VERSION_ID')
WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST')  # публичный HTTPS адрес, например, https://abc.ngrok.io
WEBHOOK_PATH = '/webhook'
PORT = int(os.environ.get('PORT', 8443))

app = Flask(__name__)
application = None  # глобально

# Временные хранилища
USERS = {}  # user_id: {'photo_path', 'prompt'}
PAYMENTS = {}  # payment_id: {'user_id', 'status'}

# --- ЮKassa API ---
def create_yookassa_payment(amount_rub, description, user_id):
    url = "https://api.yookassa.ru/v3/payments"
    headers = {
        "Authorization": f"Bearer {YUKASSA_API_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "amount": {
            "value": f"{amount_rub:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://your-return-url"
        },
        "capture": True,
        "metadata": {
            "user_id": str(user_id)
        }
    }
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code == 201:
        return resp.json()
    else:
        print("Yookassa create error:", resp.text)
        return None

def check_yookassa_payment(payment_id):
    url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
    headers = {
        "Authorization": f"Bearer {YUKASSA_API_TOKEN}"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    else:
        print("Yookassa check error:", resp.text)
        return None

# --- Replicate ---
def process_image_with_replicate(image_path, prompt):
    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}"
    }
    # отправляем запрос
    json_data = {
        "version": REPLICATE_MODEL_VERSION_ID,
        "input": {
            "prompt": prompt
        }
    }
    with open(image_path, 'rb') as img:
        files = {'file': (os.path.basename(image_path), img, 'application/octet-stream')}
        resp = requests.post(url, headers=headers, json=json_data)
        if resp.status_code == 201:
            pred = resp.json()
            pred_id = pred['id']
            # Ожидание результата
            for _ in range(10):
                time.sleep(3)
                status_res = requests.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=headers)
                if status_res.json().get('status') == 'succeeded':
                    return status_res.json().get('output')
            return None
        else:
            print("Replicate error:", resp.text)
            return None

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправьте фотографию, а затем напишите описание для обработки.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    photo = update.message.photo[-1]
    filename = f"{user_id}_photo.jpg"
    await photo.get_file().download_to_drive(filename)
    USERS[user_id] = {'photo_path': filename}
    await update.message.reply_text("Теперь напишите описание (промпт) для обработки этого изображения.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in USERS or 'photo_path' not in USERS[user_id]:
        await update.message.reply_text("Пожалуйста, отправьте фото сначала.")
        return
    prompt = update.message.text
    USERS[user_id]['prompt'] = prompt

    # Создаем оплату
    payment = create_yookassa_payment(100, "Обработка изображения", user_id)
    if payment:
        payment_id = payment['id']
        PAYMENTS[payment_id] = {'user_id': user_id, 'status': 'pending'}
        confirmation_url = payment['confirmation']['confirmation_url']
        keyboard = [[InlineKeyboardButton("Оплатить 100 ₽", url=confirmation_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Пожалуйста, оплатите 100 ₽", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Ошибка при создании платежа.")

# --- Webhook для уведомлений ---
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    data = request.json
    payment_id = data.get('id')
    status = data.get('status')
    if payment_id in PAYMENTS:
        PAYMENTS[payment_id]['status'] = status
        user_id = PAYMENTS[payment_id]['user_id']
        if status == 'succeeded':
            # запустим обработку
            threading.Thread(target=lambda: asyncio.run(_process_payment(user_id))).start()
    return jsonify({'status': 'ok'})

import asyncio
async def _process_payment(user_id):
    bot = application.bot
    user_data = USERS.get(user_id)
    if not user_data:
        return
    await bot.send_message(user_id, "Платёж подтверждён! Обрабатываю изображение...")
    prompt = user_data['prompt']
    photo_path = user_data['photo_path']
    result_url = process_image_with_replicate(photo_path, prompt)
    if result_url:
        await bot.send_photo(user_id, result_url)
    else:
        await bot.send_message(user_id, "Ошибка обработки.")

# --- Основной запуск ---
async def main():
    global application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Setting webhook
    webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    await application.bot.set_webhook(webhook_url)
    print(f"Webhook установлено: {webhook_url}")

    # Запуск Flask в отдельном потоке
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT)).start()

    await application.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
