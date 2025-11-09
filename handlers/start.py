from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("?? Привет! Отправь мне фото, и я помогу его оживить ??")
