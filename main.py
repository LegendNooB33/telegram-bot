import os
import json
import threading
from flask import Flask
import telebot
import psycopg2
from google import genai
from google.genai import types

# 1. Инициализация Flask для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает стабильно через Supabase!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Считывание конфигурации
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# 3. Безопасное подключение к Supabase
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception:
        # Резервный ручной разбор на случай сбоя DSN парсера
        clean_url = DATABASE_URL.replace("postgresql://", "")
        auth, auth_host = clean_url.split("@")
        user, password = auth.split(":")
        host_port, dbname = auth_host.split("/")
        host, port = host_port.split(":")
        return psycopg2.connect(
            database=dbname, user=user, password=password, host=host, port=int(port)
        )

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_history (
            user_id BIGINT PRIMARY KEY,
            history_json TEXT NOT NULL
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()

def load_chat_history(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT history_json FROM user_history WHERE user_id = %s;", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return []
    try:
        raw_list = json.loads(row[0]) # Исправлено: распаковка кортежа из БД
        return [types.Content(**content_dict) for content_dict in raw_list]
    except Exception as e:
        print(f"Ошибка чтения истории: {e}")
        return []

def save_chat_history(user_id, history_objects):
    serializable_history = [content.model_dump() for content in history_objects]
    history_json = json.dumps(serializable_history)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_history (user_id, history_json)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET history_json = EXCLUDED.history_json;
    """, (user_id, history_json))
    conn.commit()
    cursor.close()
    conn.close()

# 4. Логика бота
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    save_chat_history(user_id, [])
    bot.reply_to(message, "Привет! Я бот с постоянной памятью в базе Supabase. Напиши мне свой вопрос.")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    user_id = message.from_user.id
    save_chat_history(user_id, [])
    bot.reply_to(message, "История диалога очищена.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        history = load_chat_history(user_id)
        
        chat = ai_client.chats.create(
            model=MODEL_NAME,
            history=history
        )
        response = chat.send_message(message.text)
        updated_history = chat.get_history()
        save_chat_history(user_id, updated_history)
        
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {str(e)}")

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Бот успешно запущен и слушает Telegram...")
    bot.infinity_polling()
