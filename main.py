# -*- coding: utf-8 -*-
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import config
from handlers import start, payment, process

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(process.router)
dp.include_router(payment.router)

async def on_startup(app):
    await bot.set_webhook(f"{config.WEBHOOK_URL}/webhook")
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать работу"),
    ])
    logging.info("Webhook установлен ?")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Webhook удалён ?")

app = web.Application()
app["bot"] = bot

SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
setup_application(app, dp, bot=bot)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
