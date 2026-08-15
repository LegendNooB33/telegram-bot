import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# ===== Веб-сервер для Render =====
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Бот работает!"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

Thread(target=run_web).start()

# ===== Ключи из переменных окружения =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
PROXY_KEY = os.environ.get("PROXY_API_KEY")
PROXY_URL = os.environ.get("PROXY_URL")  # URL продавца

if not TOKEN or not PROXY_KEY or not PROXY_URL:
    print("❌ Ошибка: Проверьте переменные окружения")
    exit(1)

# ===== Команда /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот через прокси-сервер.\n"
        "Задавай любые вопросы — я отвечу!"
    )

# ===== Текст =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        response = requests.post(
            f"{PROXY_URL}/chat/completions",
            headers={"Authorization": f"Bearer {PROXY_KEY}"},
            json={
                "model": "gemini-2.0-flash-exp",
                "messages": [{"role": "user", "content": user_text}]
            },
            timeout=30
        )
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"]
            await update.message.reply_text(reply[:4000])
        else:
            await update.message.reply_text(f"❌ Ошибка API: {response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ===== Запуск =====
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
