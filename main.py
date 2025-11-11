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

# === Аутентификация ===
security = HTTPBasic()
async def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == ADMIN_LOGIN and credentials.password == ADMIN_PASSWORD:
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")

# === Корень / для проверки ===
@app.get("/")
async def root():
    return {"status": "ok", "message": "Бот и сервер FastAPI работают!"}

# === Вебхук ЮKassa ===
@app.post("/yookassa_webhook")
async def yookassa_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Cloud-Signature")

    from yookassa.domain.notification import WebhookNotification

    try:
        notification = WebhookNotification(payload.decode("utf-8"), signature)
        payment = notification.object

        if payment.status == "succeeded":
            user_id = payment.metadata.get("user_id")
            if user_id:
                await process_animation_async(int(user_id), payment.id)

                # Синхронная БД
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE user_sessions SET status = 'succeeded' WHERE payment_id = %s",
                    (payment.id,)
                )
                conn.commit()
                cur.close()
                conn.close()
            else:
                logger.error("User ID not found in payment metadata.")
    except Exception as e:
        logger.error(f"Webhook error: {e}")

    return {"status": "ok"}

# === Админка ===
def format_currency(rubles: int) -> str:
    return f"{rubles} ₽"

@app.get("/admin", dependencies=[Depends(verify_admin)])
async def admin_panel():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_sessions")
        total_users = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM user_sessions WHERE status = 'succeeded'")
        successful_payments = cur.fetchone()[0] or 0

        total_revenue = successful_payments * 100

        cur.execute("""
            SELECT user_id, prompt, status, created_at
            FROM user_sessions
            ORDER BY created_at DESC
            LIMIT 10
        """)
        sessions = cur.fetchall()
        cur.close()
        conn.close()

        sessions_html = ""
        for user_id, prompt, status, created_at in sessions:
            emoji = "✅" if status == "succeeded" else "⏳"
            sessions_html += f"<tr><td>{user_id}</td><td>{prompt[:50]}...</td><td>{emoji} {status}</td><td>{created_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>Админка</title></head>
        <body>
            <h1>🤖 Админ-панель</h1>
            <p>Всего пользователей: {total_users or 0}</p>
            <p>Успешных оплат: {successful_payments or 0}</p>
            <p>Доход: {format_currency(total_revenue)}</p>
            <table border="1">
                <tr><th>User ID</th><th>Промпт</th><th>Статус</th><th>Дата</th></tr>
                {sessions_html if sessions_html else "<tr><td colspan='4'>Нет данных</td></tr>"}
            </table>
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
    if not bot_instance:
        logger.error("bot_instance is not set. Unable to send messages.")
        return

    try:
        await bot_instance.send_message(chat_id=user_id, text="🎨 Обрабатываю твоё фото...")

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