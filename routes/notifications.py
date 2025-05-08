from flask import Blueprint, jsonify, request
from database.connection import get_db_connection, release_db_connection
from utils.admin_logger import AdminLogger
import traceback

notifications_bp = Blueprint('notifications', __name__)

# API для получения уведомлений текущего пользователя
@notifications_bp.route("/api/notifications", methods=["GET"])
def get_notifications():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 401
    
    try:
        # Вместо возможного возникновения ошибки, давайте вернем пустой список уведомлений
        # и добавим диагностическую информацию для отладки
        conn = None  # Инициализируем переменную, чтобы использовать в блоке finally
        cursor = None
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
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
            
            return jsonify({
                "notifications": all_notifications,
                "unread_count": notifications_count
            })
        except Exception as db_error:
            # Логируем ошибку, но возвращаем пустые данные вместо ошибки
            print(f"Ошибка при запросе к БД в get_notifications: {str(db_error)}")
            traceback.print_exc()
            return jsonify({
                "notifications": [],
                "unread_count": 0,
                "debug_info": {
                    "user_id": user_id,
                    "error_type": str(type(db_error)),
                    "error_message": str(db_error)
                }
            })
    except Exception as e:
        print(f"Общая ошибка в get_notifications: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "notifications": [],
            "unread_count": 0,
            "error": "Ошибка при получении уведомлений",
            "debug_info": {
                "user_id": user_id,
                "error_type": str(type(e)),
                "error_message": str(e)
            }
        })
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

# API для отметки уведомления как прочитанного
@notifications_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        conn.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Ошибка при отметке уведомления как прочитанного: {str(e)}")
        return jsonify({"error": "Ошибка при обновлении уведомления"}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

# API для отметки всех уведомлений пользователя как прочитанных
@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Отмечаем все уведомления пользователя как прочитанные
        cursor.execute(
            "UPDATE user_notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE",
            (user_id,)
        )
        
        conn.commit()
        
        # Получаем количество обновленных уведомлений
        row_count = cursor.rowcount
        
        return jsonify({"success": True, "updated_count": row_count})
    except Exception as e:
        print(f"Ошибка при отметке всех уведомлений как прочитанных: {str(e)}")
        return jsonify({"error": "Ошибка при обновлении уведомлений"}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)
