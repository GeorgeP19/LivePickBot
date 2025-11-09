from aiogram import Router, types
from yookassa import Configuration, Payment
import os
import uuid
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, REPLICATE_API_TOKEN
import replicate
from handlers.process import user_images

router = Router()

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

@router.message(lambda msg: msg.text and not msg.text.startswith("/"))
async def handle_prompt(message: types.Message):
    prompt = message.text
    user_id = message.from_user.id

    if user_id not in user_images:
        await message.answer("Сначала пришли фото ??")
        return

    payment_id = str(uuid.uuid4())

    payment = Payment.create({
        "amount": {"value": "100.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/LivePicBot_bot"},
        "capture": True,
        "description": f"Оживление фото пользователя {user_id}",
    })

    url = payment.confirmation.confirmation_url
    await message.answer(f"?? Оплати 100 ? по ссылке:\n{url}\n\nПосле оплаты я начну оживление ?")

# В продакшне нужно обработать webhook от ЮKassa — здесь упрощённо:
async def process_after_payment(message: types.Message, prompt: str):
    image_url = user_images[message.from_user.id]
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    await message.answer("?? Генерирую оживлённое фото, подожди немного...")

    output = client.run(
        "zsxkib/animate-anyone:latest",
        input={"image": image_url, "prompt": prompt}
    )

    if isinstance(output, list):
        for o in output:
            await message.answer_video(o)
    else:
        await message.answer_video(output)
