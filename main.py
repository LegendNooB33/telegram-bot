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
    return "Бот-мультимодель активен (Gemini + Llama + DeepSeek)!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Считывание токенов
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

# Названия моделей
MODEL_GEMINI = "gemini-3.5-flash"
MODEL_LLAMA = "llama-3.3-70b-versatile"
MODEL_DEEPSEEK = "deepseek-r1-distill-llama-70b"  # Тот самый DeepSeek R1 на мощностях Groq!

# 2. База данных Supabase (Универсальная история)
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

# 3. Кнопки меню Telegram (Теперь 3 модели!)
def get_model_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_gemini = telebot.types.KeyboardButton("🤖 Gemini 3.5")
    btn_llama = telebot.types.KeyboardButton("⚡ Llama 3.3")
    btn_deepseek = telebot.types.KeyboardButton("🧠 DeepSeek R1")
    btn_clear = telebot.types.KeyboardButton("🗑️ Очистить память")
    # Красиво размещаем кнопки в два ряда
    markup.add(btn_gemini, btn_llama, btn_deepseek)
    markup.add(btn_clear)
    return markup

# 4. Обработчики команд
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    save_user_profile(user_id, 'gemini', [])
    bot.reply_to(
        message, 
        "Привет! Переключайся между тремя нейросетями прямо на лету с помощью меню 👇", 
        reply_markup=get_model_menu()
    )

# 5. Обработка системных кнопок меню
@bot.message_handler(func=lambda message: message.text in ["🤖 Gemini 3.5", "⚡ Llama 3.3", "🧠 DeepSeek R1", "🗑️ Очистить память"])
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
        bot.reply_to(message, "Включен мыслящий DeepSeek R1 (через Groq) 🧠\nОн может отвечать чуть дольше, так как сначала обдумывает шаги решения.", reply_markup=get_model_menu())
        
    elif message.text == "🗑️ Очистить память":
        save_user_profile(user_id, current_model, [])
        bot.reply_to(message, f"Память для текущей модели успешно очищена!", reply_markup=get_model_menu())

# 6. Основная логика диалога
@bot.message_handler(func=lambda message: True)
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
            ai_text = completion.choices.message.content
            
        elif chosen_model == 'deepseek':
            # Отправляем тот же запрос в Groq, но запрашиваем "мозги" DeepSeek R1
            completion = groq_client.chat.completions.create(
                model=MODEL_DEEPSEEK,
                messages=history
            )
            ai_text = completion.choices.message.content
        
        history.append({"role": "assistant", "content": ai_text})
        save_user_profile(user_id, chosen_model, history)
        
        bot.reply_to(message, ai_text, reply_markup=get_model_menu())
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка модели {chosen_model}: {str(e)}", reply_markup=get_model_menu())

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.delete_webhook(drop_pending_updates=True)
    print("Бот на 3 модели успешно запущен...")
    bot.infinity_polling()
