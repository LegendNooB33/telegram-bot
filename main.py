import os
import json
import base64
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
    return "Бот Gemini активен, подключен к Supabase, баг байтов исправлен!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Настройки Telegram и Gemini
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3.7-flash"

# ИСПРАВЛЕНИЕ: Кастомный кодировщик для обхода бага bytes в Gemini 3
class GeminiJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            # Если находим байты (thought_signature), безопасно кодируем их в строку Base64
            return base64.b64encode(obj).decode('utf-8')
        return super().default(obj)

# ИСПРАВЛЕНИЕ: Функция восстановления байтов при чтении из БД
def bytes_decoder(dct):
    for key, value in dct.items():
        if isinstance(value, str) and key == "thought_signature":
            try:
                dct[key] = base64.b64decode(value.encode('utf-8'))
            except Exception:
                pass
    return dct

# 3. Подключение к Supabase
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST"),
        port=int(os.environ.get("DB_PORT", 6543)),
        database=os.environ.get("DB_NAME", "postgres"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD")
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
    
    if not row or not row[0]:
        return []
        
    try:
        # ИСПРАВЛЕНО: Читаем строку из кортежа и декодируем Base64 обратно в байты
        raw_list = json.loads(row[0], object_hook=bytes_decoder)
        return [types.Content(**content_dict) for content_dict in raw_list]
    except Exception as e:
        print(f"Ошибка парсинга истории для пользователя {user_id}: {e}")
        return []

def save_chat_history(user_id, history_objects):
    serializable_history = [content.model_dump() for content in history_objects]
    # ИСПРАВЛЕНО: Используем наш кастомный кодировщик GeminiJsonEncoder
    history_json = json.dumps(serializable_history, cls=GeminiJsonEncoder)
    
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

# 4. Команды бота
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    save_chat_history(user_id, [])
    bot.reply_to(message, "Привет! Я бот на базе Gemini 3.7. Баг с памятью полностью исправлен. Спроси меня о чём-нибудь!")

@bot.message_handler(commands=['clear'])
def clear_memory(message):
    user_id = message.from_user.id
    save_chat_history(user_id, [])
    bot.reply_to(message, "История нашего общения успешно очищена!")

# 5. Обработка сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        
        # 1. Загружаем историю
        history = load_chat_history(user_id)
        
        # 2. Создаем сессию чата
        chat = ai_client.chats.create(
            model=MODEL_NAME,
            history=history
        )
        
        # 3. Отправляем сообщение
        response = chat.send_message(message.text)
        
        # 4. Сохраняем обновленную историю
        updated_history = chat.get_history()
        save_chat_history(user_id, updated_history)
        
        bot.reply_to(message, response.text)
        
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка при обработке нейросетью: {str(e)}")

# 6. Старт
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    
    print("Удаляем конфликтующие вебхуки Telegram...")
    bot.delete_webhook(drop_pending_updates=True)
    
    print("Бот успешно запущен на модели Gemini 3.7 и слушает Telegram...")
    bot.infinity_polling()
