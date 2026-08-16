import os
import json
import threading
from flask import Flask
import telebot
import psycopg2
from google import genai
from google.genai import types

# 1. Инициализация Flask-сервера для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот Gemini запущен и подключен к Supabase!", 200

def run_web_server():
    # На бесплатном тарифе Render обязан слушать порт
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Считывание конфигурации из переменных окружения
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# 3. Функции для работы с базой данных Supabase
def init_db():
    """Создает таблицу в Supabase, если она еще не создана."""
    conn = psycopg2.connect(DATABASE_URL)
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
    """Извлекает JSON историю из БД и конвертирует её в объекты типов Gemini."""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT history_json FROM user_history WHERE user_id = %s;", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        return []
        
    try:
        # row[0] содержит строку JSON
        raw_list = json.loads(row[0])
        # Восстанавливаем типы Content, необходимые для SDK google-genai
        return [types.Content(**content_dict) for content_dict in raw_list]
    except Exception as e:
        print(f"Ошибка чтения истории из БД для {user_id}: {e}")
        return []

def save_chat_history(user_id, history_objects):
    """Конвертирует историю Gemini в JSON строку и сохраняет/обновляет запись в Supabase."""
    # model_dump() переводит Pydantic объекты Gemini в обычные словари Python
    serializable_history = [content.model_dump() for content in history_objects]
    history_json = json.dumps(serializable_history)
    
    conn = psycopg2.connect(DATABASE_URL)
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

# 4. Обработчики команд Telegram
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    # Очищаем историю переписки при старте
    save_chat_history(user_id, [])
    bot.reply_to(message, "Привет! Я бот с постоянной памятью в базе Supabase. Напиши мне что угодно!")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    user_id = message.from_user.id
    save_chat_history(user_id, [])
    bot.reply_to(message, "История нашего диалога успешно стерта из базы данных!")

# 5. Обработчик всех текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    try:
        # Показываем статус, что бот думает/пишет
        bot.send_chat_action(message.chat.id, 'typing')
        
        # Шаг А: Загружаем предыдущие реплики из Supabase
        history = load_chat_history(user_id)
        
        # Шаг Б: Инициализируем сессию чата Gemini с подгруженной историей
        chat = ai_client.chats.create(
            model=MODEL_NAME,
            history=history
        )
        
        # Шаг В: Отправляем новое сообщение в контексте диалога
        response = chat.send_message(message.text)
        
        # Шаг Г: Получаем от Gemini обновленную историю (включая этот новый вопрос и ответ)
        updated_history = chat.get_history()
        
        # Шаг Д: Перезаписываем обновленный список в Supabase
        save_chat_history(user_id, updated_history)
        
        # Отправляем ответ пользователю
        bot.reply_to(message, response.text)
        
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при обработке: {str(e)}")

# 6. Точка входа приложения
if __name__ == "__main__":
    # Сначала проверяем/создаем таблицу в облаке Supabase
    init_db()
    
    # Запускаем Flask-сервер в фоновом потоке, чтобы Render не закрывал приложение
    threading.Thread(target=run_web_server, daemon=True).start()
    
    print("Бот успешно инициализирован и слушает Telegram...")
    # Запускаем бесконечный опрос серверов Telegram
    bot.infinity_polling()
