import logging
import asyncio
import os
import threading
import json
import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import replicate
import yookassa
from yookassa import Configuration, Payment

import psycopg2
from psycopg2.extras import RealDictCursor

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

import uvicorn

# === Логирование ===
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === Конфигурация ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

# === Инициализация БД ===
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# === FastAPI ===
app = FastAPI()
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == ADMIN_LOGIN and credentials.password == ADMIN_PASSWORD:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")

# === FastAPI для вебхука и админки ===
app = FastAPI()

# === Аутентификация ===
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == ADMIN_LOGIN and credentials.password == ADMIN_PASSWORD:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")

# === Вебхук ЮKassa ===
@app.post("/webhook")
async def yookassa_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Cloud-Signature")
    
    # Проверка подписи (опционально, но рекомендуется)
    from yookassa.domain.notification import WebhookNotification
    try:
        notification = WebhookNotification(payload, signature)
        payment = notification.object
        
        if payment.status == "succeeded":
            user_id = int(payment.metadata.get("user_id"))
            await process_animation_async(user_id, payment.id)
            # Обновить статус в БД
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE user_sessions SET status = 'succeeded' WHERE payment_id = %s",
                (payment.id,)
            )
            conn.commit()
            cur.close()
            conn.close()
            return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"error": str(e)}

# === Админ-панель ===
def format_currency(rubles: int) -> str:
    return f"{rubles} ₽"

@app.get("/admin", dependencies=[Depends(verify_admin)])
async def admin_panel():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Статистика
        cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_sessions")
        total_users = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM user_sessions WHERE status = 'succeeded'")
        successful_payments = cur.fetchone()[0] or 0

        total_revenue = successful_payments * 100  # 100 ₽ за анимацию

        # Последние 10 сессий
        cur.execute("""
            SELECT user_id, prompt, status, created_at
            FROM user_sessions
            ORDER BY created_at DESC
            LIMIT 10
        """)
        sessions = cur.fetchall()
        cur.close()
        conn.close()

        # Генерация HTML
        sessions_html = ""
        for user_id, prompt, status, created_at in sessions:
            emoji = "✅" if status == "succeeded" else "⏳"
            sessions_html += f"<tr><td>{user_id}</td><td>{prompt[:50]}...</td><td>{emoji} {status}</td><td>{created_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>📊 Админка — Telegram Bot</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
                .card {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background: #eee; }}
            </style>
        </head>
        <body>
            <h1>🤖 Админ-панель бота</h1>

            <div class="card">
                <h2>📈 Статистика</h2>
                <p><strong>Всего пользователей:</strong> {total_users}</p>
                <p><strong>Успешных оплат:</strong> {successful_payments}</p>
                <p><strong>Доход:</strong> <span style="color: green; font-weight: bold;">{format_currency(total_revenue)}</span></p>
            </div>

            <div class="card">
                <h2>📋 Последние сессии (10)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>User ID</th>
                            <th>Промпт</th>
                            <th>Статус</th>
                            <th>Дата</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sessions_html if sessions_html else "<tr><td colspan='4'>Нет данных</td></tr>"}
                    </tbody>
                </table>
            </div>

            <p><small>Обновляется в реальном времени. Обнови страницу.</small></p>
        </body>
        </html>
        """
        return HTMLResponse(html)

    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return HTMLResponse(f"<h1>Ошибка: {e}</h1>", status_code=500)

# === Асинхронная обработка анимации ===
bot_instance = None

async def process_animation_async(user_id: int, payment_id: str):
    try:
        await bot_instance.send_message(chat_id=user_id, text="🎨 Обрабатываю твоё фото... Это займёт 10–60 секунд.")

        # Получаем данные из БД
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT file_path, prompt FROM user_sessions WHERE user_id = %s AND payment_id = %s", (user_id, payment_id))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            await bot_instance.send_message(chat_id=user_id, text="❌ Данные не найдены.")
            return

        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{row['file_path']}"

        output = replicate.run(
            "cjwbw/animatediff:8793444502895298267891e27483567237301855498564957152087314028758",
            input={
                "prompt": row["prompt"],
                "input_image": image_url,
                "num_frames": 16,
                "fps": 8
            }
        )

        if isinstance(output, list) and len(output) > 0:
            animation_url = output[0]
            await bot_instance.send_animation(chat_id=user_id, animation=animation_url)
            await bot_instance.send_message(chat_id=user_id, text="🎉 Вот твоя анимация! Спасибо за оплату!")

            # Уведомление админу
            if ADMIN_USER_ID:
                await bot_instance.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"💰 Новая оплата!\nUser: {user_id}\nПромпт: {row['prompt']}\nДоход: +100 ₽"
                )
        else:
            await bot_instance.send_message(chat_id=user_id, text="❌ Не удалось получить анимацию.")

    except Exception as e:
        logger.error(f"Replicate error: {e}")
        await bot_instance.send_message(chat_id=user_id, text="❌ Ошибка при обработке. Попробуйте позже.")

# === Телеграм-бот ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Пришли мне фото и напиши, что ты хочешь увидеть (например: 'смех, ветер в волосах'), "
        "и я оживлю его за 100 ₽. После оплаты — получишь анимацию!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("📸 Пожалуйста, отправь фото.")
        return

    photo = update.message.photo[-1]
    prompt = update.message.caption.strip() if update.message.caption else "анимировать изображение"
    file = await context.bot.get_file(photo.file_id)
    file_path = file.file_path

    # Создаём платёж
    payment = Payment.create({
        "amount": {"value": "100.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": f"https://t.me/{context.bot.username}"},
        "capture": True,
        "description": f"Оживление фото для {user_id}",
        "metadata": {"user_id": str(user_id)}
    })

    # Сохраняем в БД
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_sessions (user_id, file_path, prompt, payment_id, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            file_path = EXCLUDED.file_path,
            prompt = EXCLUDED.prompt,
            payment_id = EXCLUDED.payment_id,
            status = EXCLUDED.status
    """, (user_id, file_path, prompt, payment.id, "awaiting_payment"))
    conn.commit()
    cur.close()
    conn.close()

    keyboard = [[InlineKeyboardButton("💳 Оплатить 100 ₽", url=payment.confirmation.confirmation_url)]]
    await update.message.reply_text(
        "✅ Фото получено!\n\n💰 Оплати 100 ₽ — и я сразу начну обработку!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === Запуск ===
def run_bot():
    global bot_instance
    app_bot = Application.builder().token(BOT_TOKEN).build()
    bot_instance = app_bot.bot

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app_bot.run_polling()

def run_webhook_server():
    # Render использует порт 10000 по умолчанию для web services
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    # Запускаем FastAPI на основном потоке (Render требует это для вебхука)
    # А бота — в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    run_webhook_server()
