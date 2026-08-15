import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import google.generativeai as genai

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 8080))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройка Gemini API
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Используем модель gemini-2.5-flash
    model = genai.GenerativeModel('gemini-2.5-flash')
    logging.info("Gemini успешно настроен.")
except Exception as e:
    logging.error(f"Ошибка настройки Gemini: {e}")

@dp.message()
async def handle_message(message: Message):
    """Мгновенно принимает сообщение, чтобы избежать дубликатов от Telegram"""
    if not message.text:
        return
    # Передаем обработку в фоновую задачу
    asyncio.create_task(generate_and_send_response(message))

async def generate_and_send_response(message: Message):
    try:
        # Показываем статус "печатает..."
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Запрос к нейросети (выполняется асинхронно в потоке, чтобы не вешать сервер)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, model.generate_content, message.text)
        
        if response.text:
            await message.answer(response.text)
        else:
            await message.answer("Нейросеть прислала пустой ответ.")
    except Exception as e:
        logging.error(f"Ошибка при генерации текста: {e}")
        await message.answer("Не удалось получить ответ от нейросети.")

async def on_startup(bot: Bot):
    logging.info(f"Установка вебхука на URL: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def main():
    dp.startup.register(on_startup)
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(app, "0.0.0.0", PORT)
    await site.start()
    
    logging.info(f"Бот успешно запущен на порту {PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
