from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort
from flask import session, current_app
from datetime import datetime, timezone
import uuid
import logging
import time
from database.connection import get_db_connection, release_db_connection
from security.access_control import require_role, UserRole

settings_bp = Blueprint('settings', __name__)

@settings_bp.route("/settings")
@require_role(UserRole.USER)
def settings():
    """Отображение страницы настроек пользователя"""
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Получаем информацию о пользователе
            cursor.execute("""
                SELECT u.username, u.status, u.avatar,
                       tp.telegram_id, tp.telegram_username, tp.notifications_enabled
                FROM users u
                LEFT JOIN telegram_profiles tp ON u.id = tp.user_id
                WHERE u.id = %s
            """, (user_id,))
            
            user_data = cursor.fetchone()
            
            if not user_data:
                return redirect(url_for('logout.logout'))
            
            username, status, avatar, telegram_id, telegram_username, notifications_enabled = user_data
            
            # Получаем количество заказов (как в profile.py)
            orders_count = 0
            if status == "admin":
                cursor.execute("SELECT COUNT(*) FROM order_status")
                orders_count = cursor.fetchone()[0]
                
            # Генерируем уникальную ссылку для привязки Telegram
            if not telegram_id:
                # Создаем временный токен для привязки
                token = str(uuid.uuid4())
                
                # Сохраняем токен в базе данных
                cursor.execute("""
                    INSERT INTO telegram_tokens (user_id, token, created_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET token = %s, created_at = %s
                """, (user_id, token, datetime.now(timezone.utc), token, datetime.now(timezone.utc)))
                
                conn.commit()
                
                # Формируем ссылку на телеграм-бота
                telegram_bot_link = f"https://t.me/roxin_smart_bot?start={token}"
            else:
                telegram_bot_link = None
            
            return render_template(
                "settings.html",
                username=username,
                status=status,
                avatar=avatar or "user.png",
                orders_count=orders_count,
                telegram_connected=telegram_id is not None,
                telegram_username=telegram_username,
                notifications_enabled=notifications_enabled or False,
                telegram_bot_link=telegram_bot_link
            )
    
    except Exception as e:
        logging.error(f"Ошибка при загрузке настроек: {e}")
        return jsonify({"error": "Ошибка при загрузке настроек"}), 500
    
    finally:
        if conn:
            release_db_connection(conn)

@settings_bp.route("/settings/notifications", methods=["POST"])
@require_role(UserRole.USER)
def toggle_notifications():
    """API для включения/отключения уведомлений в Telegram"""
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "Необходима авторизация"}), 401
    
    try:
        data = request.get_json()
        enabled = data.get('enabled', False)
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Проверяем, привязан ли Telegram
            cursor.execute("SELECT telegram_id FROM telegram_profiles WHERE user_id = %s", (user_id,))
            telegram_data = cursor.fetchone()
            
            if not telegram_data:
                return jsonify({
                    "success": False, 
                    "error": "Telegram не привязан"
                }), 400
            
            # Обновляем настройки уведомлений
            cursor.execute("""
                UPDATE telegram_profiles 
                SET notifications_enabled = %s 
                WHERE user_id = %s
            """, (enabled, user_id))
            
            conn.commit()
            
            return jsonify({
                "success": True,
                "enabled": enabled
            })
            
    except Exception as e:
        logging.error(f"Ошибка при обновлении настроек уведомлений: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500
        
    finally:
        if conn:
            release_db_connection(conn)

@settings_bp.route("/settings/unlink_telegram", methods=["GET"])
@require_role(UserRole.USER)
def unlink_telegram():
    """Отвязка Telegram-аккаунта"""
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Удаляем привязку Telegram
            cursor.execute("DELETE FROM telegram_profiles WHERE user_id = %s", (user_id,))
            # Удаляем токены привязки
            cursor.execute("DELETE FROM telegram_tokens WHERE user_id = %s", (user_id,))
            
            conn.commit()
            
        return redirect(url_for('settings.settings'))
    
    except Exception as e:
        logging.error(f"Ошибка при отвязке Telegram: {e}")
        return jsonify({"error": "Ошибка при отвязке Telegram"}), 500
    
    finally:
        if conn:
            release_db_connection(conn)