import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai

# Ключи теперь берутся из переменных окружения (безопасно!)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот на ChatGPT. Просто напиши мне что-нибудь :)")

async def chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": user_message}]
        )
        reply = response.choices[0].message.content
        await update.message.reply_text(reply[:4000])
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

def main():
    if not TOKEN or not openai.api_key:
        print("Ошибка: Не найдены ключи в переменных окружения!")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt))
    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
