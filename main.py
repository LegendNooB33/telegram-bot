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
    return "Бот-мультимодель активен (Gemini + Groq)!", 200

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
MODEL_GROQ = "llama-3.3-70b-versatile"  # Можно заменить на "deepseek-r1-distill-llama-70b"

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
    # Создаем таблицу с поддержкой выбора модели
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
    """Возвращает (выбранная_модель, история_списком)"""
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
    btn_gemini = telebot.types.KeyboardButton("🤖 Использовать Gemini 3.5")
    btn_groq = telebot.types.KeyboardButton("⚡ Использовать Groq (Llama 3.3)")
    btn_clear = telebot.types.KeyboardButton("🗑️ Очистить память")
    markup.add(btn_gemini, btn_groq)
    markup.add(btn_clear)
    return markup

# 4. Обработчики команд
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    save_user_profile(user_id, 'gemini', [])
    bot.reply_to(
        message, 
        "Привет! Я бот-мультимодель.\nС помощью меню ниже ты можешь переключаться между Gemini и Groq (Llama) прямо на лету!", 
        reply_markup=get_model_menu()
    )

# 5. Обработка системных кнопок меню
@bot.message_handler(func=lambda message: message.text in ["🤖 Использовать Gemini 3.5", "⚡ Использовать Groq (Llama 3.3)", "🗑️ Очистить память"])
def handle_menu_buttons(message):
    user_id = message.from_user.id
    current_model, history = get_user_profile(user_id)
    
    if message.text == "🤖 Использовать Gemini 3.5":
        save_user_profile(user_id, 'gemini', history)
        bot.reply_to(message, "Успешно переключено на модель Gemini 3.5 Flash! Промпты будут отправляться в Google.", reply_markup=get_model_menu())
    
    elif message.text == "⚡ Использовать Groq (Llama 3.3)":
        save_user_profile(user_id, 'groq', history)
        bot.reply_to(message, "Успешно переключено на сверхбыструю Llama 3.3 через Groq LPU!", reply_markup=get_model_menu())
        
    elif message.text == "🗑️ Очистить память":
        save_user_profile(user_id, current_model, [])
        bot.reply_to(message, f"Память для текущей модели ({current_model}) успешно очищена!", reply_markup=get_model_menu())

# 6. Основная логика диалога
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Шаг А: Узнаем, какую модель выбрал юзер и какая у него история
    chosen_model, history = get_user_profile(user_id)
    
    # Добавляем реплику пользователя в общую историю
    history.append({"role": "user", "content": message.text})
    
    try:
        if chosen_model == 'gemini':
            # Конвертируем нашу чистую историю в формат объектов Google SDK
            gemini_history = []
            for msg in history[:-1]: # Передаем всё, кроме последнего сообщения
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
            
            chat = gemini_client.chats.create(model=MODEL_GEMINI, history=gemini_history)
            response = chat.send_message(message.text)
            ai_text = response.text
            
        else:
            # Отправка запроса в Groq (Llama)
            # Формат истории Groq совпадает с нашим базовым списком словарей
            completion = groq_client.chat.completions.create(
                model=MODEL_GROQ,
                messages=history
            )
            ai_text = completion.choices[0].message.content
        
        # Добавляем ответ нейросети в историю и сохраняем в Supabase
        history.append({"role": "assistant", "content": ai_text})
        save_user_profile(user_id, chosen_model, history)
        
        bot.reply_to(message, ai_text, reply_markup=get_model_menu())
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка модели {chosen_model}: {str(e)}", reply_markup=get_model_menu())

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.delete_webhook(drop_pending_updates=True)
    print("Мультимодельный бот успешно запущен...")
    bot.infinity_polling()
