# Найти строчку с вызовом DATABASE_URL и заменить блок функций работы с БД:

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Безопасное подключение к БД с поддержкой парсинга строки или прямых параметров."""
    try:
        # Пробуем подключиться напрямую по строке
        return psycopg2.connect(DATABASE_URL)
    except Exception:
        # Если не вышло (ошибка парсинга), разбираем строку вручную
        # Пример: postgresql://user:pass@host:port/dbname
        try:
            clean_url = DATABASE_URL.replace("postgresql://", "")
            auth, auth_host = clean_url.split("@")
            user, password = auth.split(":")
            host_port, dbname = auth_host.split("/")
            host, port = host_port.split(":")
            
            return psycopg2.connect(
                database=dbname,
                user=user,
                password=password,
                host=host,
                port=int(port)
            )
        except Exception as e:
            raise RuntimeError(f"Критическая ошибка конфигурации DATABASE_URL: {e}")

def init_db():
    """Создание таблицы для хранения истории, если её нет."""
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
    """Загрузка истории из БД и преобразование в объекты типов Gemini."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT history_json FROM user_history WHERE user_id = %s;", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        return []
        
    try:
        raw_list = json.loads(row[0]) # Исправлено: берем первый элемент кортежа row
        return [types.Content(**content_dict) for content_dict in raw_list]
    except Exception as e:
        print(f"Ошибка парсинга истории для {user_id}: {e}")
        return []

def save_chat_history(user_id, history_objects):
    """Преобразование объектов Gemini в JSON и сохранение в БД."""
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
