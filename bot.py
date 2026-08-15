import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== ТВОИ КЛЮЧИ (берутся из переменных окружения Render) =====
TOKEN = os.environ.get("TELEGRAM_TOKEN")
PROXY_KEY = os.environ.get("PROXY_API_KEY")
PROXY_URL = os.environ.get("PROXY_URL")  # Например: https://api.proxy-gemini.com

if not TOKEN or not PROXY_KEY or not PROXY_URL:
    print("❌ Ошибка: Проверьте переменные окружения")
    exit(1)

# ===== КОМАНДА /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот. Задай мне любой вопрос.")

# ===== ОБРАБОТЧИК ТЕКСТА (без дублей) =====
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

# ===== ЗАПУСК БОТА (ТОЛЬКО POLLING, БЕЗ ВЕБХУКОВ) =====
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен и слушает сообщения...")
    app.run_polling()  # <-- Только polling, без Flask!

if __name__ == "__main__":
    main()
