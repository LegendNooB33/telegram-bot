import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from google import genai

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

# Корректная инициализация для ключей Vertex AI (начинающихся на AQ...)
# Если у вас корпоративный аккаунт Google Cloud, укажите ваш Project ID и локацию (например, us-central1)
try:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY,
        # location="us-central1" # Раскомментируйте и укажите регион, если Vertex выдаст ошибку локации
    )
    logging.info("Gemini Client успешно инициализирован.")
except Exception as e:
    logging.error(f"Ошибка инициализации Gemini Client: {e}")

@dp.message()
async def handle_message(message: Message):
    """
    Обработчик сообщений. Запросы к API вынесены в фоновую задачу,
    чтобы бот мгновенно отвечал Telegram '200 OK' и не дублировал сообщения.
    """
    if not message.text:
        return

    # Запускаем генерацию ответа асинхронно в фоне
    asyncio.create_task(generate_and_send_response(message))

async def generate_and_send_response(message: Message):
    try:
        # Отправляем статус "печатает...", чтобы пользователь видел активность
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Запрос к актуальной быстрой модели
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=message.text,
        )
        
        if response.text:
            await message.answer(response.text)
        else:
            await message.answer("Нейросеть вернула пустой ответ.")
            
    except Exception as e:
        logging.error(f"Ошибка при генерации текста: {e}")
        await message.answer("Извините, не удалось обработать ваш запрос к Gemini.")

async def on_startup(bot: Bot):
    """Действие при запуске сервера: регистрируем вебхук в Telegram"""
    logging.info(f"Установка вебхука на URL: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def main():
    dp.startup.register(on_startup)
    app = web.Application()
    
    # Конфигурируем обработчик вебхуков
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
