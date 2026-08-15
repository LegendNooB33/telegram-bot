import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from flask import Flask
from threading import Thread

# Фальшивый веб-сервер для Render
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Бот работает!"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

# Запускаем веб-сервер в фоновом потоке
Thread(target=run_web).start()

# Ключи из переменных окружения
TOKEN = os.environ.get("TELEGRAM_TOKEN")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот на ChatGPT. Просто напиши мне что-нибудь :)")

async def chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": user_message}]
        )
        reply = response.choices[0].message.content
        await update.message.reply_text(reply[:4000])
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

def main():
    if not TOKEN or not os.environ.get("OPENAI_API_KEY"):
        print("Ошибка: Не найдены ключи в переменных окружения!")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt))
    print("Бот запущен на новой версии OpenAI!")
    app.run_polling()

if __name__ == "__main__":
    main()
