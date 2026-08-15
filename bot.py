import os
import base64
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from flask import Flask
from threading import Thread

# ===== Веб-сервер для Render =====
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Бот на Gemini (официальный ключ) работает!"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

Thread(target=run_web).start()

# ===== КЛЮЧИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # Сюда вставишь AQ.Ab8...

if not TOKEN or not GEMINI_API_KEY:
    print("❌ Ошибка: Проверьте переменные TELEGRAM_TOKEN и GEMINI_API_KEY")
    exit(1)

# ===== НАСТРОЙКА GEMINI (работает с AIza и AQ) =====
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-exp")  # Или gemini-1.5-flash

# ===== КОМАНДА /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот на **Gemini 2.0 Flash** (официальный ключ).\n\n"
        "📝 Отвечаю на любые вопросы.\n"
        "🖼️ Могу анализировать фото."
    )

# ===== ТЕКСТ =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = model.generate_content(update.message.text)
        await update.message.reply_text(response.text[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ===== ФОТО (если ключ поддерживает) =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    print("✅ Бот на официальном Gemini запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
