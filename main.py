import os
import json
import threading
from flask import Flask
import telebot
import psycopg2
from google import genai
from google.genai import types

# 1. Инициализация Flask-сервера для прохождения проверок порта Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот Gemini активен и подключен к Supabase напрямую!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Считывание конфигурации Telegram и Gemini
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# 3. Прямое подключение к Supabase по отдельным параметрам
def get_db_connection():
    """Подключение к базе данных без использования строки URL."""
    return psycopg2.connect(
        host=os.environ.get("DB_HOST"),
        port=int(os.environ.get("DB_PORT", 6543)),
        database=os.environ.get("DB_NAME", "postgres"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD")
    )

def init_db():
    """Создание таблицы для хранения истории диалогов, если её нет в Supabase."""
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
    """Загрузка истории из Supabase и преобразование в объекты типов Gemini SDK."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT history_json FROM user_history WHERE user_id = %s;", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        return []
        
    try:
        # Извлекаем JSON-строку из кортежа результата БД (строка лежит в первом элементе)
        raw_list = json.loads(row[0])
        # Восстанавливаем объекты Content, необходимые для работы чата Gemini
        return [types.Content(**content_dict) for content_dict in raw_list]
    except Exception as e:
        print(f"Ошибка парсинга истории для пользователя {user_id}: {e}")
        return []

def save_chat_history(user_id, history_objects):
    """Преобразование объектов Gemini в JSON-строку и сохранение в Supabase."""
    # model_dump() переводит Pydantic-объекты Google SDK в обычные словари Python
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

# 4. Обработчики команд Telegram бота
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    # Очищаем историю принудительно при старте нового диалога
    save_chat_history(user_id, [])
    bot.reply_to(message, "Привет! Я бот с бесконечной памятью диалога в базе Supabase. Напиши мне любой вопрос.")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    user_id = message.from_user.id
    save_chat_history(user_id, [])
    bot.reply_to(message, "История нашего общения успешно очищена из базы данных!")

# 5. Обработка всех текстовых сообщений (Диалог с памятью)
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    try:
        # Показываем анимацию "Бот печатает..."
        bot.send_chat_action(message.chat.id, 'typing')
        
        # Шаг 1: Загружаем прошлые реплики из базы данных Supabase
        history = load_chat_history(user_id)
        
        # Шаг 2: Инициализируем сессию чата Gemini с подгруженной историей
        chat = ai_client.chats.create(
            model=MODEL_NAME,
            history=history
        )
        
        # Шаг 3: Отправляем новое сообщение модели
        response = chat.send_message(message.text)
        
        # Шаг 4: Получаем от Gemini обновленную полную историю реплик
        updated_history = chat.get_history()
        
        # Шаг 5: Сохраняем обновленный контекст обратно в Supabase
        save_chat_history(user_id, updated_history)
        
        # Отвечаем пользователю в Telegram
        bot.reply_to(message, response.text)
        
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при обработке: {str(e)}")

# 6. Главная точка входа приложения
if __name__ == "__main__":
    # Проверяем и создаем структуру таблиц в Supabase
    init_db()
    
    # Запускаем Flask веб-сервер в фоновом потоке
    threading.Thread(target=run_web_server, daemon=True).start()
    
    print("Бот успешно запущен и слушает Telegram...")
    # Старт бесконечного опроса Telegram
    bot.infinity_polling()
