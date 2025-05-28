import os
import logging
from database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

def init_database():
    """Инициализация базы данных с выполнением всех схем"""
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                # Список SQL файлов для выполнения в правильном порядке
                sql_files = [
                    'database/init_schema.sql',
                    'database/support_tables.sql',
                    'database/admin_panel_schema.sql',
                    'database/user_bans_schema.sql',
                    'database/password_reset_schema.sql'
                ]
                
                for sql_file in sql_files:
                    if os.path.exists(sql_file):
                        logger.info(f"Выполняю {sql_file}...")
                        with open(sql_file, 'r', encoding='utf-8') as f:
                            sql_content = f.read()
                            # Разделяем по точке с запятой и выполняем каждый запрос отдельно
                            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
                            for statement in statements:
                                try:
                                    cursor.execute(statement)
                                except Exception as e:
                                    # Игнорируем ошибки "already exists"
                                    if "already exists" not in str(e).lower():
                                        logger.warning(f"Ошибка в запросе: {e}")
                        logger.info(f"✅ {sql_file} выполнен")
                    else:
                        logger.warning(f"⚠️ Файл {sql_file} не найден")
                
                conn.commit()
                logger.info("🎉 База данных успешно инициализирована!")
                
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации базы данных: {e}")
        raise

if __name__ == "__main__":
    init_database() 