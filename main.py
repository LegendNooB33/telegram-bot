import os
import logging
from aiogram import Bot, Dispatcher
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
    model = genai.GenerativeModel('gemini-1.5-flash')
    logging.info("Gemini успешно настроен.")
except Exception as e:
    logging.error(f"Ошибка настройки Gemini: {e}")

@dp.message()
async def handle_message(message: Message):
    """Принимает сообщение и сразу отвечает в Telegram"""
    if not message.text:
        return
        
    try:
        # Отправляем статус "печатает..."
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Получаем ответ от Gemini напрямую
        response = model.generate_content(message.text)
        
        if response.text:
            await message.answer(response.text)
        else:
            await message.answer("Нейросеть вернула пустой ответ.")
    except Exception as e:
        logging.error(f"Ошибка при генерации текста: {e}")
        await message.answer("Извините, не удалось обработать ваш запрос.")

async def on_startup(bot: Bot):
    """Установка вебхука при старте приложения"""
    logging.info(f"Установка вебхука на URL: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

def main():
    # Регистрируем событие запуска
    dp.startup.register(on_startup)
    
    # Создаем стандартное aiohttp приложение
    app = web.Application()
    
    # Настраиваем официальный обработчик вебхуков от aiogram
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Связываем aiogram и aiohttp
    setup_application(app, dp, bot=bot)
    
    # Важно: Запускаем приложение через стандартный run_app, который идеально поддерживается Render
    logging.info(f"Запуск вебхука на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
