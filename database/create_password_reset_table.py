import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_db_connection

def create_password_reset_table():
    """
    Создает таблицу для хранения токенов сброса пароля.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Чтение SQL-файла
        script_path = os.path.join(os.path.dirname(__file__), 'password_reset_schema.sql')
        with open(script_path, 'r') as f:
            sql_script = f.read()
        
        # Выполнение SQL-скрипта
        cursor.execute(sql_script)
        conn.commit()
        print("Таблица password_reset_tokens успешно создана!")
        
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании таблицы: {str(e)}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    create_password_reset_table()
