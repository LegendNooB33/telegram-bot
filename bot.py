import os
import base64
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from flask import Flask
from threading import Thread
from collections import defaultdict
import time

# ===== Веб-сервер для Render =====
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Бот на Gemini работает!"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

Thread(target=run_web).start()

# ===== КЛЮЧИ =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TOKEN or not GEMINI_API_KEY:
    print("❌ Ошибка: Проверьте переменные TELEGRAM_TOKEN и GEMINI_API_KEY")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# ===== СПИСОК МОДЕЛЕЙ ДЛЯ АВТОПОИСКА =====
MODELS_TO_TRY = [
    "gemini-3-flash",
    "gemini-3.0-flash",
    "gemini-3-flash-exp",
    "gemini-2.5-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
]

# ===== ФУНКЦИЯ ПОИСКА РАБОЧЕЙ МОДЕЛИ =====
def find_working_model():
    for model_name in MODELS_TO_TRY:
        try:
            test_model = genai.GenerativeModel(model_name)
            test_model.generate_content("test")
            print(f"✅ Найдена рабочая модель: {model_name}")
            return test_model
        except Exception:
            print(f"❌ Модель {model_name} не работает, пробуем следующую...")
            continue
    print("❌ Ни одна модель не сработала!")
    return None

model = find_working_model()

if not model:
    print("❌ Ошибка: Не удалось найти рабочую модель. Проверьте ключ.")
    exit(1)

# ===== ЗАЩИТА ОТ ДУБЛИРОВАНИЯ =====
# Храним последние 5 сообщений от каждого пользователя
user_last_messages = defaultdict(lambda: {"text": "", "time": 0})

def is_duplicate(update: Update) -> bool:
    user_id = update.effective_user.id
    current_text = update.message.text or ""
    current_time = time.time()
    
    # Если это команда /start — пропускаем защиту
    if current_text.startswith("/start"):
        return False
    
    # Проверяем, не было ли такого же текста от этого пользователя за последние 2 секунды
    last = user_last_messages[user_id]
    if last["text"] == current_text and (current_time - last["time"]) < 2:
        return True
    
    # Обновляем последнее сообщение
    user_last_messages[user_id] = {"text": current_text, "time": current_time}
    return False

# ===== КОМАНДА /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Привет! Я бот на **Gemini**.\n"
        f"✅ Работает с моделью: `{model.model_name}`\n\n"
        "📝 Отвечаю на любые вопросы.\n"
        "🖼️ Могу анализировать фото.\n"
        "⚡ Защита от дублирования включена!"
    )

# ===== ТЕКСТ (с защитой от дублей) =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем на дублирование
    if is_duplicate(update):
        return  # Молча игнорируем повторное сообщение
    
    try:
        response = model.generate_content(update.message.text)
        await update.message.reply_text(response.text[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ===== ФОТО (с защитой от дублей) =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем на дублирование
    if is_duplicate(update):
        return
    
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = file.file_path
        response = requests.get(file_path)
        image_data = base64.b64encode(response.content).decode("utf-8")

        caption = update.message.caption or "Что на фото?"
        prompt = f"{caption}\n\nПодробно опиши, что изображено на фото."

        image_part = {"mime_type": "image/jpeg", "data": image_data}
        result = model.generate_content([prompt, image_part])
        await update.message.reply_text(result.text[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ===== ЗАПУСК =====
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print(f"✅ Бот запущен! Модель: {model.model_name}")
    print("✅ Защита от дублирования включена!")
    app.run_polling()

if __name__ == "__main__":
    main()
