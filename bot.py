import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from flask import Flask
from threading import Thread

# ===== Веб-сервер для Render =====
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Бот на Gemini работает!"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

Thread(target=run_web).start()

# ===== Ключи =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")  # Твой ключ AQ.Ab8...

if not TOKEN or not GEMINI_KEY:
    print("❌ Ошибка: Проверьте переменные TELEGRAM_TOKEN и GEMINI_API_KEY")
    exit(1)

# Инициализация клиента Gemini
client = genai.Client(api_key=GEMINI_KEY)

# ===== Команда /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот на **Gemini 3.6 Flash**.\n"
        "Задавай любые вопросы — я отвечу!"
    )

# ===== Текст =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        # Используем ТОЧНО ТАКОЙ ЖЕ вызов, как в примере продавца
        interaction = client.interactions.create(
            model="gemini-3.6-flash",
            input=user_text
        )
        reply = interaction.output_text
        await update.message.reply_text(reply[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ===== Запуск =====
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ Бот на Gemini 3.6 Flash запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
