"""
Скрипт для выполнения SQL-схемы из файла.
Выполняет SQL-запросы из файла password_reset_schema.sql
"""

import os
import sys
from connection import get_db_connection

def execute_sql_file(file_path):
    """Выполняет SQL-запросы из указанного файла"""
    # Проверяем существование файла
    if not os.path.exists(file_path):
        print(f"Ошибка: Файл {file_path} не найден")
        return False
        
    # Читаем содержимое SQL-файла
    with open(file_path, 'r', encoding='utf-8') as file:
        sql_commands = file.read()
    
    # Получаем соединение с базой данных
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Выполняем SQL-запросы
        cursor.execute(sql_commands)
        
        # Фиксируем изменения
        conn.commit()
        
        print(f"SQL-запросы из файла {file_path} успешно выполнены")
        
        # Закрываем соединение
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Ошибка при выполнении SQL-запросов: {str(e)}")
        return False

if __name__ == "__main__":
    # Путь к SQL-файлу
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_file = os.path.join(script_dir, "password_reset_schema.sql")
    
    # Выполняем SQL-файл
    success = execute_sql_file(sql_file)
    
    # Устанавливаем код возврата
    sys.exit(0 if success else 1)
