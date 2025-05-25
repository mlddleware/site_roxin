"""
Скрипт для создания таблицы банов пользователей в базе данных.
"""

import os
from connection import get_db_connection

def create_user_bans_table():
    """Создает таблицу банов пользователей в базе данных"""
    # Путь к SQL-файлу со схемой
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file = os.path.join(script_dir, "user_bans_schema.sql")
    
    # Проверяем существование файла
    if not os.path.exists(sql_file):
        print(f"Ошибка: Файл {sql_file} не найден")
        return False
        
    # Читаем содержимое SQL-файла
    with open(sql_file, 'r', encoding='utf-8') as file:
        sql_commands = file.read()
    
    # Получаем соединение с базой данных
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Выполняем SQL-запросы
        cursor.execute(sql_commands)
        
        # Фиксируем изменения
        conn.commit()
        
        print("Таблица банов пользователей успешно создана")
        
        # Закрываем соединение
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Ошибка при создании таблицы банов: {str(e)}")
        return False

if __name__ == "__main__":
    create_user_bans_table()
