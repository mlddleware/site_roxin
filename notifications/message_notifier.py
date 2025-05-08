import asyncio
import logging
from datetime import datetime, timezone
from database.connection import get_db_connection, release_db_connection

# Абсолютный импорт с использованием полного пути
from notifications.telegram_bot import notify_message

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Синхронная функция-обертка для асинхронного вызова
def run_async_with_loop(coro):
    """Запускает асинхронную корутину в новом event loop"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Ошибка при выполнении асинхронной задачи: {e}")
    finally:
        loop.close()

def notify_new_message(sender_id, recipient_id, message):
    try:
        # Логирование входящих данных
        logger.info(f"🔔 Входящее уведомление:")
        logger.info(f"Отправитель (sender_id): {sender_id}")
        logger.info(f"Получатель (recipient_id): {recipient_id}")
        logger.info(f"Сообщение: {message}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем имя отправителя
        cursor.execute("SELECT username FROM users WHERE id = %s", (sender_id,))
        sender_data = cursor.fetchone()
        
        if not sender_data:
            logger.error(f"❌ Не удалось найти отправителя с ID {sender_id}")
            release_db_connection(conn)
            return
            
        sender_name = sender_data[0]
        
        # Проверяем, привязан ли Telegram
        cursor.execute("""
            SELECT telegram_id, notifications_enabled, user_id 
            FROM telegram_profiles 
            WHERE user_id = %s
        """, (recipient_id,))
        
        result = cursor.fetchone()
        
        # Расширенное логирование
        if not result:
            logger.warning(f"❌ Для пользователя {recipient_id} не найден Telegram-профиль")
            release_db_connection(conn)
            return
        
        telegram_id, notifications_enabled, profile_user_id = result
        
        logger.info(f"✅ Telegram-профиль:")
        logger.info(f"Telegram ID: {telegram_id}")
        logger.info(f"Уведомления включены: {notifications_enabled}")
        logger.info(f"User ID профиля: {profile_user_id}")
        
        if not notifications_enabled:
            logger.info(f"🚫 У пользователя {recipient_id} отключены уведомления")
            release_db_connection(conn)
            return
        
        # Используем синхронную обертку для асинхронного вызова
        run_async_with_loop(notify_message(recipient_id, sender_name, message))
        
        # Записываем информацию об отправленном уведомлении
        cursor.execute("""
            INSERT INTO notification_log 
            (user_id, notification_type, message, created_at)
            VALUES (%s, %s, %s, %s)
        """, (
            recipient_id, 
            'message', 
            f"Новое сообщение от {sender_name}", 
            datetime.now(timezone.utc)
        ))
        
        conn.commit()
        release_db_connection(conn)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке нового сообщения: {e}")
        if 'conn' in locals():
            release_db_connection(conn)