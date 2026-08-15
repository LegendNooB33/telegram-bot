import os
import logging
from aiogram import Bot, Dispatcher, F
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

# --- НАСТРОЙКА БЕЛОГО СПИСКА (СПИСОК ТЕХ, КОМУ МОЖНО) ---
# Замените числа ниже на свой ID (и ID друзей, если нужно, через запятую)
ALLOWED_USERS = [1240110156] 
# --------------------------------------------------------

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройка Gemini API
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.5-flash')
    logging.info("Gemini успешно настроен.")
except Exception as e:
    logging.error(f"Ошибка настройки Gemini: {e}")

@dp.message()
async def handle_message(message: Message):
    """Единый обработчик для текстовых сообщений и фото с проверкой доступа"""
    
    # ПРОВЕРКА: Если ID пользователя нет в списке разрешенных
    if message.from_user.id not in ALLOWED_USERS:
        logging.warning(f"Попытка доступа от постороннего! ID: {message.from_user.id}, Username: @{message.from_user.username}")
        await message.answer("Извините, этот бот приватный. У вас нет доступа к Gemini. 🔒")
        return # Останавливаем функцию, дальше код выполняться не будет

    # Дальше идет ваша стандартная рабочая логика бота...
    prompt_parts = []
    
    if message.photo:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            photo = message.photo[-1]
            photo_file = await message.bot.download(photo)
            photo_bytes = photo_file.read()
            
            prompt_parts.append({
                "mime_type": "image/jpeg",
                "data": photo_bytes
            })
            
            if message.caption:
                prompt_parts.append(message.caption)
            else:
                prompt_parts.append("Что изображено на этом фото? Опиши подробно.")
                
        except Exception as e:
            logging.error(f"Ошибка при скачивании фото: {e}")
            await message.answer("Не удалось загрузить вашу картинку.")
            return

    elif message.text:
        prompt_parts.append(message.text)
        
    else:
        await message.answer("Я умею обрабатывать только текст и фотографии! 📸")
        return

    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(prompt_parts)
        
        if response.text:
            await message.answer(response.text)
        else:
            await message.answer("Нейросеть вернула пустой ответ.")
    except Exception as e:
        logging.error(f"Ошибка при генерации текста: {e}")
        await message.answer("Извините, не удалось обработать ваш запрос к Gemini.")

async def on_startup(bot: Bot):
    logging.info(f"Установка вебхука на URL: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    logging.info(f"Запуск вебхука на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
