import os
import uuid
import replicate
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher
from aiogram.types import Message, ContentType
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram import Router
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import aiofiles

# =============== Настройки ===============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_PATH = "/webhook/telegram"
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")
WEBHOOK_URL = f"{WEBHOOK_DOMAIN}{WEBHOOK_PATH}"

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# =============== Модели БД ===============
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    photo_path = Column(String)
    description = Column(Text)
    payment_id = Column(String)
    payment_confirmed = Column(Boolean, default=False)
    replicate_id = Column(String, nullable=True)
    result_url = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending → paid → processing → done/failed
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

# =============== Telegram Bot ===============
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

class Form(StatesGroup):
    waiting_for_photo = State()
    waiting_for_description = State()

@router.message(Form.waiting_for_photo)
async def photo_handler(message: Message, state: FSMContext):
    if message.content_type != ContentType.PHOTO:
        await message.answer("Пожалуйста, отправьте фото.")
        return

    file = await bot.get_file(message.photo[-1].file_id)
    photo_dir = "photos"
    os.makedirs(photo_dir, exist_ok=True)
    file_path = f"{photo_dir}/{message.from_user.id}_{file.file_id}.jpg"
    
    await bot.download_file(file.file_path, file_path)

    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            user = User(telegram_id=message.from_user.id)
            session.add(user)
            session.commit()
            session.refresh(user)
        task = Task(
            user_id=user.id,
            photo_path=file_path,
            status="pending"
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id

    await state.update_data(task_id=task_id)
    await message.answer("Опишите, что должно происходить на фото (например: улыбается, машет рукой, смеётся).")
    await state.set_state(Form.waiting_for_description)

@router.message(Form.waiting_for_description)
async def description_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await message.answer("Ошибка. Начните сначала: отправьте фото.")
        return

    description = message.text
    with SessionLocal() as session:
        task = session.query(Task).filter_by(id=task_id).first()
        if not task:
            await message.answer("Ошибка задачи.")
            return
        task.description = description

        # Создаём платёж
        payment_id = str(uuid.uuid4())
        task.payment_id = payment_id

        # Формируем URL для оплаты (в реальности — YooKassa, но для демо просто текст)
        await message.answer(
            f"✅ Описание принято!\n\n"
            f"Оплатите 100 ₽, чтобы оживить фото.\n\n"
            f"👉 Для оплаты перейдите в личный кабинет YooKassa по ссылке:\n"
            f"https://yoomoney.ru/quickpay/shop-widget?account={os.getenv('YOOKASSA_ACCOUNT_ID')}"
            f"&sum=100&paymentType=AC&label={payment_id}&successURL={WEBHOOK_DOMAIN}/success"
        )
        task.status = "awaiting_payment"
        session.commit()

    await state.clear()

@router.message()
async def start_handler(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_photo)
    await message.answer("📸 Отправьте фото, которое хотите оживить!")

dp.include_router(router)

# =============== Replicate ===============
async def run_replicate(task_id: int):
    with SessionLocal() as session:
        task = session.query(Task).filter_by(id=task_id).first()
        if not task or task.status != "paid":
            return

        task.status = "processing"
        session.commit()

    try:
        output = replicate.run(
            "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9f030f893b61e0b7b2",
            input={
                "image": open(task.photo_path, "rb"),
                "cond_aug": 0.05,
                "decoding_t": 7,
                "video_length": 14
            }
        )
        result_url = output[0] if isinstance(output, list) else output

        with SessionLocal() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            task.result_url = result_url
            task.status = "done"
            session.commit()

        # Отправить пользователю
        with SessionLocal() as session:
            user = session.query(User).filter_by(id=task.user_id).first()
            if user:
                await bot.send_video(chat_id=user.telegram_id, video=result_url, caption="✨ Ваше оживлённое фото готово!")
    except Exception as e:
        with SessionLocal() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            task.status = "failed"
            session.commit()
        print(f"Replicate error: {e}")

# =============== YooKassa Webhook ===============
async def confirm_payment(task_id: int):
    with SessionLocal() as session:
        task = session.query(Task).filter_by(id=task_id).first()
        if task and not task.payment_confirmed:
            task.payment_confirmed = True
            task.status = "paid"
            session.commit()
            # Запускаем генерацию
            await run_replicate(task_id)

# =============== FastAPI App ===============
app = FastAPI()

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    return await handler.handle(request)

# YooKassa webhook
@app.post("/webhook/yookassa")
async def yookassa_webhook(request: Request):
    payload = await request.json()
    if payload.get("event") == "payment.succeeded":
        metadata = payload["object"].get("metadata", {})
        payment_id = metadata.get("payment_id")
        if payment_id:
            with SessionLocal() as session:
                task = session.query(Task).filter_by(payment_id=payment_id).first()
                if task:
                    await confirm_payment(task.id)
    return {"status": "ok"}

# Статистика
@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    with SessionLocal() as session:
        total = session.query(Task).count()
        paid = session.query(Task).filter_by(payment_confirmed=True).count()
        done = session.query(Task).filter_by(status="done").count()
        revenue = paid * 100
    return templates.TemplateResponse("stats.html", {
        "request": request,
        "total": total,
        "paid": paid,
        "done": done,
        "revenue": revenue
    })

@app.get("/")
async def root():
    return {"status": "ok", "webhook": WEBHOOK_URL}