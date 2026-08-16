import os
import json
import threading
from flask import Flask
import telebot
import psycopg2
from google import genai
from google.genai import types
from groq import Groq

# 1. Инициализация серверов и клиентов
app = Flask(__name__)

@app.route('/')
def home():
    return "Приватный мультимодельный бот Gemini + Llama + DeepSeek активен и исправлен!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Считывание токенов и ID администратора из настроек Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
except ValueError:
    ADMIN_ID = 0

bot = telebot.TeleBot(TELEGRAM_TOKEN)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

# Названия моделей
MODEL_GEMINI = "gemini-3.5-flash"
MODEL_LLAMA = "openai/gpt-oss-120b"
MODEL_DEEPSEEK = "qwen/qwen3.6-27b"


# Функция-фильтр для проверки, что пишет именно создатель бота
def is_admin(message):
    return message.from_user.id == ADMIN_ID

# 2. База данных Supabase
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
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id BIGINT PRIMARY KEY,
            current_model TEXT DEFAULT 'gemini',
            history_json TEXT DEFAULT '[]'
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()

def get_user_profile(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_model, history_json FROM user_profiles WHERE user_id = %s;", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return 'gemini', []
    return row[0], json.loads(row[1])

def save_user_profile(user_id, model_name, history_list):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_profiles (user_id, current_model, history_json)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET current_model = EXCLUDED.current_model, history_json = EXCLUDED.history_json;
    """, (user_id, model_name, json.dumps(history_list)))
    conn.commit()
    cursor.close()
    conn.close()

# 3. Кнопки меню Telegram
def get_model_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_gemini = telebot.types.KeyboardButton("🤖 Gemini 3.5")
    btn_llama = telebot.types.KeyboardButton("⚡ Llama 3.3")
    btn_deepseek = telebot.types.KeyboardButton("🧠 DeepSeek R1")
    btn_clear = telebot.types.KeyboardButton("🗑️ Очистить память")
    markup.add(btn_gemini, btn_llama, btn_deepseek)
    markup.add(btn_clear)
    return markup

# --- ЗАЩИТА: Обработчик для посторонних пользователей ---
@bot.message_handler(func=lambda message: not is_admin(message))
def handle_unauthorized(message):
    reply_markup = telebot.types.ReplyKeyboardRemove()
    bot.reply_to(message, "🔒 Извините, этот бот является приватным. Доступ заблокирован.", reply_markup=reply_markup)

# 4. Обработчики команд (Только для админа)
@bot.message_handler(commands=['start', 'help'], func=is_admin)
def send_welcome(message):
    user_id = message.from_user.id
    save_user_profile(user_id, 'gemini', [])
    bot.reply_to(
        message, 
        "Добро пожаловать, Хозяин! Вы зашли в режим управления приватным мультимодельным ботом. Меню переключения активно 👇", 
        reply_markup=get_model_menu()
    )

# 5. Обработка системных кнопок меню (Только для админа)
@bot.message_handler(func=lambda message: message.text in ["🤖 Gemini 3.5", "⚡ Llama 3.3", "🧠 DeepSeek R1", "🗑️ Очистить память"] and is_admin(message))
def handle_menu_buttons(message):
    user_id = message.from_user.id
    current_model, history = get_user_profile(user_id)
    
    if message.text == "🤖 Gemini 3.5":
        save_user_profile(user_id, 'gemini', history)
        bot.reply_to(message, "Включен Gemini 3.5 (Google) 🤖", reply_markup=get_model_menu())
    
    elif message.text == "⚡ Llama 3.3":
        save_user_profile(user_id, 'llama', history)
        bot.reply_to(message, "Включена сверхбыстрая Llama 3.3 (Meta через Groq) ⚡", reply_markup=get_model_menu())
        
    elif message.text == "🧠 DeepSeek R1":
        save_user_profile(user_id, 'deepseek', history)
        bot.reply_to(message, "Включен мыслящий DeepSeek R1 (через Groq) 🧠\nОн думает над шагами решения чуть дольше.", reply_markup=get_model_menu())
        
    elif message.text == "🗑️ Очистить память":
        save_user_profile(user_id, current_model, [])
        bot.reply_to(message, f"Память для текущей модели успешно очищена!", reply_markup=get_model_menu())

# 6. Основная логика диалога (Только для админа)
@bot.message_handler(func=is_admin)
def handle_message(message):
    user_id = message.from_user.id
    bot.send_chat_action(message.chat.id, 'typing')
    
    chosen_model, history = get_user_profile(user_id)
    history.append({"role": "user", "content": message.text})
    
    try:
        if chosen_model == 'gemini':
            gemini_history = []
            for msg in history[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
            
            chat = gemini_client.chats.create(model=MODEL_GEMINI, history=gemini_history)
            response = chat.send_message(message.text)
            ai_text = response.text
            
        elif chosen_model == 'llama':
            completion = groq_client.chat.completions.create(
                model=MODEL_LLAMA,
                messages=history
            )
            # ФИКС: Добавлен индекс [0] для правильного извлечения ответа из списка
            ai_text = completion.choices[0].message.content
            
        elif chosen_model == 'deepseek':
            completion = groq_client.chat.completions.create(
                model=MODEL_DEEPSEEK,
                messages=history
            )
            # ФИКС: Добавлен индекс [0] для правильного извлечения ответа из списка
            ai_text = completion.choices[0].message.content
        
        history.append({"role": "assistant", "content": ai_text})
        save_user_profile(user_id, chosen_model, history)
        
        bot.reply_to(message, ai_text, reply_markup=get_model_menu())
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка модели {chosen_model}: {str(e)}", reply_markup=get_model_menu())

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.delete_webhook(drop_pending_updates=True)
    print("Приватный мультимодельный бот успешно запущен...")
    bot.infinity_polling()
