import os
import json
import threading
from urllib.parse import urlparse
from flask import Flask
import telebot
import psycopg2
from google import genai
from google.genai import types

# 1. Инициализация Flask-сервера для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот Gemini активен и подключен к Supabase через пулер!", 200

def run_web_server():
    # Render передает необходимый порт в переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Считывание конфигурации из переменных окружения Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# 3. Безопасное подключение к Supabase
def get_db_connection():
    """Подключение к БД с автоматическим парсингом URL для обхода проблем с сокетами."""
    try:
        # Пробуем стандартное прямое подключение
        return psycopg2.connect(DATABASE_URL)
    except Exception:
        # Резервный разбор ссылки, если psycopg2 не смог распарсить параметры пулера автоматически
        try:
            result = urlparse(DATABASE_URL)
            
            # Отсекаем имя базы данных от параметров типа ?sslmode=...
            dbname = result.path.lstrip('/')
            if '?' in dbname:
                dbname = dbname.split('?')[0]
                
            return psycopg2.connect(
                database=dbname,
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port or 5432
            )
        except Exception as e:
            raise RuntimeError(f"Критическая ошибка разбора DATABASE_URL: {e}")

def init_db():
    """Создание таблицы для хранения истории диалогов, если её нет."""
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
        # Извлекаем JSON-строку из кортежа результата БД
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
        # Отправляем анимацию "Бот печатает..."
        bot.send_chat_action(message.chat.id, 'typing')
        
        # Шаг 1: Загружаем прошлые реплики из базы данных
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
    
    # Запускаем Flask веб-сервер в фоновом потоке для прохождения проверок Render Порта
    threading.Thread(target=run_web_server, daemon=True).start()
    
    print("Бот успешно запущен и слушает Telegram...")
    # Старт бесконечного опроса Telegram
    bot.infinity_polling()
