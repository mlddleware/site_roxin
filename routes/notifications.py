from flask import Blueprint, jsonify, request
from database.connection import DatabaseConnection
from database.redis_cache import cached, cache_set, cache_get, invalidate_cache
from database.redis_config import CACHE_SETTINGS
from utils.admin_logger import AdminLogger
import traceback
import time

notifications_bp = Blueprint('notifications', __name__)

# API для получения уведомлений текущего пользователя
@notifications_bp.route("/api/notifications", methods=["GET"])
def get_notifications():
    start_time = time.time()
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 401
        
    # Ключ кэша для уведомлений этого пользователя
    cache_key = f"notifications:{user_id}"
    
    # Проверяем наличие данных в кэше
    cached_data = cache_get(cache_key)
    if cached_data:
        print(f"Уведомления получены из кэша ({time.time() - start_time:.6f} сек)")
        return jsonify(cached_data)
    
    try:
        # Используем контекстный менеджер для автоматического управления соединением
        with DatabaseConnection() as db:
            # Используем метод cursor() класса DatabaseConnection
            cursor = db.cursor()
            # Получаем уведомления пользователя
            cursor.execute(
                """
                SELECT id, title, message, severity, created_at
                FROM user_notifications
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 30
                """,
                (user_id,)
            )
            
            all_notifications = []
            for notification in cursor.fetchall():
                all_notifications.append({
                    "id": notification[0],
                    "title": notification[1],
                    "message": notification[2],
                    "severity": notification[3],
                    "created_at": notification[4].strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # Получаем общее количество непрочитанных уведомлений
            cursor.execute(
                "SELECT COUNT(*) FROM user_notifications WHERE user_id = %s AND is_read = FALSE",
                (user_id,)
            )
            notifications_count = cursor.fetchone()[0]
            
            result = {
                "notifications": all_notifications,
                "unread_count": notifications_count
            }
            
            # Сохраняем результат в кэш на 1 минуту (60 сек)
            cache_set(cache_key, result, CACHE_SETTINGS["notifications"]["ttl"])
            print(f"Уведомления сохранены в кэш ({time.time() - start_time:.6f} сек)")
            
            return jsonify(result)
    except Exception as e:
        # Логируем ошибку, но возвращаем пустые данные вместо ошибки
        print(f"Ошибка при запросе к БД в get_notifications: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "notifications": [],
            "unread_count": 0,
            "debug_info": {
                "user_id": user_id,
                "error_type": str(type(e)),
                "error_message": str(e)
            }
        })
    # Нижний блок except уже не нужен, так как мы обрабатываем все исключения 
    # в одном блоке выше, и контекстный менеджер автоматически закрывает соединения

# API для отметки уведомления как прочитанного
@notifications_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 401
        
    # Инвалидируем кэш уведомлений при отметке как прочитанного
    invalidate_cache(f"notifications:{user_id}")
    
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            # Проверяем, принадлежит ли уведомление пользователю
            cursor.execute(
                "SELECT id FROM user_notifications WHERE id = %s AND user_id = %s",
                (notification_id, user_id)
            )
            
            if not cursor.fetchone():
                return jsonify({"error": "Уведомление не найдено"}), 404
            
            # Отмечаем уведомление как прочитанное
            cursor.execute(
                "UPDATE user_notifications SET is_read = TRUE WHERE id = %s",
                (notification_id,)
            )
            
            db.commit()
            
            return jsonify({"success": True})
    except Exception as e:
        print(f"Ошибка при отметке уведомления как прочитанного: {str(e)}")
        return jsonify({"error": "Ошибка при обновлении уведомления"}), 500

# API для отметки всех уведомлений пользователя как прочитанных
@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 401
        
    # Инвалидируем кэш уведомлений при отметке всех как прочитанных
    invalidate_cache(f"notifications:{user_id}")
    
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            # Отмечаем все уведомления пользователя как прочитанные
            cursor.execute(
                "UPDATE user_notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE",
                (user_id,)
            )
            
            db.commit()
            
            # Получаем количество обновленных уведомлений
            row_count = cursor.rowcount
            
            return jsonify({"success": True, "updated_count": row_count})
    except Exception as e:
        print(f"Ошибка при отметке всех уведомлений как прочитанных: {str(e)}")
        return jsonify({"error": "Ошибка при обновлении уведомлений"}), 500
