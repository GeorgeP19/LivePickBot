from aiogram import Router, types

router = Router()
user_images = {}  # временное хранилище

@router.message(lambda msg: msg.photo)
async def handle_photo(message: types.Message, bot):
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = file.file_path
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
    user_images[message.from_user.id] = file_url
    await message.answer("? ‘ото получено! “еперь напиши, как ты хочешь его оживить ??")
