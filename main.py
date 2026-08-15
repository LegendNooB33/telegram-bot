import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import google.generativeai as genai
from io import BytesIO

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
    # Используем модель, которая отлично понимает и текст, и картинки
    model = genai.GenerativeModel('gemini-3.5-flash')
    logging.info("Gemini успешно настроен.")
except Exception as e:
    logging.error(f"Ошибка настройки Gemini: {e}")

@dp.message()
async def handle_message(message: Message):
    """Единый обработчик для текстовых сообщений и фото"""
    # Собираем запрос к Gemini
    prompt_parts = []
    
    # 1. Если пользователь прикрепил фото
    if message.photo:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            
            # Берем самое лучшее качество фотографии (последний элемент в списке)
            photo = message.photo[-1]
            
            # Скачиваем фото в память как массив байт (BytesIO)
            photo_file = await message.bot.download(photo)
            photo_bytes = photo_file.read()
            
            # Добавляем изображение в структуру запроса для Gemini
            prompt_parts.append({
                "mime_type": "image/jpeg",
                "data": photo_bytes
            })
            
            # Если к фото прикреплен текст вопроса
            if message.caption:
                prompt_parts.append(message.caption)
            else:
                prompt_parts.append("Что изображено на этом фото? Опиши подробно.")
                
        except Exception as e:
            logging.error(f"Ошибка при скачивании фото: {e}")
            await message.answer("Не удалось загрузить вашу картинку.")
            return

    # 2. Если это обычное текстовое сообщение
    elif message.text:
        prompt_parts.append(message.text)
        
    else:
        # Если пользователь отправил стикер, аудио или файл, которые мы пока не обрабатываем
        await message.answer("Я умею обрабатывать только текст и фотографии! 📸")
        return

    # Отправляем запрос в нейросеть
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Передаем массив данных (там может быть и картинка, и текст вместе)
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
