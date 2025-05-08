from flask import Blueprint, render_template, request, jsonify, session, abort, redirect, url_for
from flask import Blueprint, render_template, redirect, url_for, request, abort, jsonify
from database.connection import get_db_connection, release_db_connection
from utils.logging import logger
from utils.admin_logger import AdminLogger
from security.password_utils import hash_password, check_password
from datetime import datetime, timedelta
import secrets
import re
import json
import logging
import traceback
from functools import wraps
import uuid

# Настройка логгера
logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

# Декоратор для проверки прав администратора
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.cookies.get('user_id')
        if not user_id:
            return redirect(url_for('login.login'))
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user or user[0] != 'admin':
                abort(403)  # Доступ запрещен
                
            return f(*args, **kwargs)
        except Exception as e:
            AdminLogger.error('admin', f"Ошибка при проверке прав администратора: {str(e)}")
            abort(500)
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if 'conn' in locals() and conn:
                release_db_connection(conn)
    
    return decorated_function

# Главная страница админ-панели
@admin_bp.route("/admin", methods=["GET"])
@admin_required
def admin_dashboard():
    user_id = request.cookies.get('user_id')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные о текущем пользователе (для navbar)
        cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")
        
        # Устанавливаем дефолтный аватар для текущего пользователя
        current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")
        
        # Получаем статистику
        cursor.execute("""
            SELECT COUNT(*) FROM users WHERE status = 'user';
        """)
        total_users = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM users WHERE status = 'coder';
        """)
        total_coders = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM order_status;
        """)
        total_orders = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM order_status WHERE status = 'completed';
        """)
        completed_orders = cursor.fetchone()[0]
        
        # Получаем данные о регистрациях пользователей за последние 6 месяцев
        cursor.execute("""
            SELECT 
                DATE_TRUNC('month', created_at) as month,
                COUNT(*) as count
            FROM 
                users
            WHERE 
                created_at >= NOW() - INTERVAL '6 months'
            GROUP BY 
                DATE_TRUNC('month', created_at)
            ORDER BY 
                month ASC
        """)
        
        months = []
        registrations = []
        
        for row in cursor.fetchall():
            month = row[0].strftime('%B %Y')  # Формат "Месяц Год"
            months.append(month)
            registrations.append(row[1])
            
        # Если данных меньше 6 месяцев, добавляем нулевые данные
        if len(months) < 6:
            current_date = datetime.now()
            for i in range(6 - len(months)):
                past_date = current_date - timedelta(days=30*i)
                months.append(past_date.strftime('%B %Y'))
                registrations.append(0)
                
        # Получаем статистику по статусам заказов
        cursor.execute("""
            SELECT 
                status, 
                COUNT(*) as count
            FROM 
                order_status
            GROUP BY 
                status
        """)
        
        order_statuses = {}
        for row in cursor.fetchall():
            order_statuses[row[0]] = row[1]
            
        # Определяем стандартные статусы, даже если их нет в БД
        status_mapping = {
            'created': 'Создан',
            'in_progress': 'В работе',
            'revision_requested': 'Требует доработки',
            'completed': 'Завершен',
            'cancelled': 'Отменен',
            'pending': 'Ожидает'
        }
        
        order_status_labels = []
        order_status_data = []
        order_status_colors_bg = []
        order_status_colors_border = []
        
        # Дефолтные цвета для разных статусов
        colors = {
            'created': ['rgba(245, 158, 11, 0.8)', 'rgba(245, 158, 11, 1)'],  # Оранжевый
            'in_progress': ['rgba(79, 70, 229, 0.8)', 'rgba(79, 70, 229, 1)'],  # Синий
            'revision_requested': ['rgba(139, 92, 246, 0.8)', 'rgba(139, 92, 246, 1)'],  # Фиолетовый
            'completed': ['rgba(16, 185, 129, 0.8)', 'rgba(16, 185, 129, 1)'],  # Зеленый
            'cancelled': ['rgba(239, 68, 68, 0.8)', 'rgba(239, 68, 68, 1)'],  # Красный
            'pending': ['rgba(107, 114, 128, 0.8)', 'rgba(107, 114, 128, 1)']  # Серый
        }
        
        # Добавляем данные для каждого статуса
        for status, label in status_mapping.items():
            count = order_statuses.get(status, 0)
            if count > 0 or status == 'completed':  # Всегда добавляем completed для совместимости
                order_status_labels.append(label)
                order_status_data.append(count)
                if status in colors:
                    order_status_colors_bg.append(colors[status][0])
                    order_status_colors_border.append(colors[status][1])
                else:
                    # Дефолтные цвета для неизвестных статусов
                    order_status_colors_bg.append('rgba(107, 114, 128, 0.8)')
                    order_status_colors_border.append('rgba(107, 114, 128, 1)')
        
        # Получаем последние 10 логов
        cursor.execute("""
            SELECT level, source, message, created_at 
            FROM system_logs 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        recent_logs = cursor.fetchall()

        # Получаем непрочитанные уведомления
        cursor.execute("""
            SELECT id, title, message, severity, created_at 
            FROM admin_notifications 
            WHERE admin_id = %s AND is_read = FALSE
            ORDER BY created_at DESC
        """, (user_id,))
        notifications = cursor.fetchall()
        
        # Получаем количество непрочитанных уведомлений
        unread_notifications = len(notifications)
        
        # Преобразуем данные для передачи в шаблон
        months_json = json.dumps(months)
        registrations_json = json.dumps(registrations)
        order_status_labels_json = json.dumps(order_status_labels)
        order_status_data_json = json.dumps(order_status_data)
        order_status_colors_bg_json = json.dumps(order_status_colors_bg)
        order_status_colors_border_json = json.dumps(order_status_colors_border)
        
        return render_template(
            "admin/dashboard.html",
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar,
            current_user_status=current_user_status,
            total_users=total_users,
            total_coders=total_coders,
            total_orders=total_orders,
            completed_orders=completed_orders,
            months=months_json,
            registrations=registrations_json,
            order_status_labels=order_status_labels_json,
            order_status_data=order_status_data_json,
            order_status_colors_bg=order_status_colors_bg_json,
            order_status_colors_border=order_status_colors_border_json,
            recent_logs=recent_logs,
            notifications=notifications,
            unread_notifications=unread_notifications
        )
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при загрузке админ-панели: {str(e)}")
        return jsonify({"error": "Ошибка при загрузке админ-панели"}), 500
    finally:
        cursor.close()
        conn.close()

# API для получения системных логов
@admin_bp.route("/api/admin/logs", methods=["GET"])
@admin_required
def get_logs():
    try:
        level = request.args.get('level')
        source = request.args.get('source')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Базовый запрос
        query = """
            SELECT id, level, source, message, ip_address, user_id, created_at
            FROM system_logs
            WHERE 1=1
        """
        params = []
        
        # Применяем фильтры
        if level:
            query += " AND level = %s"
            params.append(level)
        
        if source:
            query += " AND source = %s"
            params.append(source)
        
        if start_date:
            query += " AND created_at >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND created_at <= %s"
            params.append(end_date)
        
        # Добавляем сортировку и пагинацию
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        logs = cursor.fetchall()
        
        # Форматируем результаты
        result = []
        for log in logs:
            log_id, level, source, message, ip_address, user_id, created_at = log
            result.append({
                'id': log_id,
                'level': level,
                'source': source,
                'message': message,
                'ip_address': ip_address,
                'user_id': user_id,
                'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # Получаем общее количество логов для пагинации
        count_query = """
            SELECT COUNT(*) FROM system_logs WHERE 1=1
        """
        count_params = []
        
        if level:
            count_query += " AND level = %s"
            count_params.append(level)
        
        if source:
            count_query += " AND source = %s"
            count_params.append(source)
        
        if start_date:
            count_query += " AND created_at >= %s"
            count_params.append(start_date)
        
        if end_date:
            count_query += " AND created_at <= %s"
            count_params.append(end_date)
        
        cursor.execute(count_query, count_params)
        total_logs = cursor.fetchone()[0]
        
        return jsonify({
            'logs': result,
            'total': total_logs,
            'pages': (total_logs + limit - 1) // limit,
            'current_page': page
        })
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении логов: {str(e)}")
        return jsonify({"error": "Ошибка при получении логов"}), 500
    finally:
        cursor.close()
        conn.close()

# API для управления пользователями
@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def get_users():
    try:
        status = request.args.get('status')
        search = request.args.get('search')
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'asc')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Базовый запрос
        query = """
            SELECT u.id, u.username, u.email, u.status, u.created_at, up.last_visit
            FROM users u
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE 1=1
        """
        params = []
        
        # Применяем фильтры
        if status:
            query += " AND u.status = %s"
            params.append(status)
        
        if search:
            query += " AND (u.username ILIKE %s OR u.email ILIKE %s)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param])
        
        # Проверяем допустимость параметров сортировки
        valid_sort_columns = ['id', 'username', 'email', 'status', 'created_at', 'last_visit']
        valid_sort_orders = ['asc', 'desc']
        
        if sort_by not in valid_sort_columns:
            sort_by = 'id'
        
        if sort_order.lower() not in valid_sort_orders:
            sort_order = 'asc'
        
        # Добавляем сортировку и пагинацию
        query += f" ORDER BY u.{sort_by} {sort_order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        users = cursor.fetchall()
        
        # Форматируем результаты
        result = []
        for user in users:
            user_id, username, email, status, created_at, last_visit = user
            result.append({
                'id': user_id,
                'username': username,
                'email': email,
                'status': status,
                'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'last_visit': last_visit.strftime('%Y-%m-%d %H:%M:%S') if last_visit else None
            })
        
        # Получаем общее количество пользователей для пагинации
        count_query = """
            SELECT COUNT(*) FROM users u WHERE 1=1
        """
        count_params = []
        
        if status:
            count_query += " AND u.status = %s"
            count_params.append(status)
        
        if search:
            count_query += " AND (u.username ILIKE %s OR u.email ILIKE %s)"
            search_param = f"%{search}%"
            count_params.extend([search_param, search_param])
        
        cursor.execute(count_query, count_params)
        total_users = cursor.fetchone()[0]
        
        return jsonify({
            'users': result,
            'total': total_users,
            'pages': (total_users + limit - 1) // limit,
            'current_page': page
        })
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении пользователей: {str(e)}")
        return jsonify({"error": "Ошибка при получении пользователей"}), 500
    finally:
        cursor.close()
        conn.close()

# API для получения данных конкретного пользователя
@admin_bp.route("/api/admin/users/<int:user_id>", methods=["GET"])
@admin_required
def get_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные пользователя
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.status, u.created_at, up.last_visit
            FROM users u
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        user_id, username, email, status, created_at, last_visit = user_data
        
        # Форматируем данные
        result = {
            'id': user_id,
            'username': username,
            'email': email,
            'status': status,
            'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None,
            'last_visit': last_visit.strftime('%Y-%m-%d %H:%M:%S') if last_visit else None
        }
        
        # Логируем доступ к данным пользователя
        admin_id = request.cookies.get('user_id')
        AdminLogger.info('admin', f'Просмотр данных пользователя #{user_id}', 
                        {'admin_id': admin_id, 'user_id': user_id})
        
        return jsonify(result)
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении данных пользователя #{user_id}: {str(e)}")
        return jsonify({"error": "Ошибка при получении данных пользователя"}), 500
    finally:
        cursor.close()
        conn.close()

# API для удаления пользователя
@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    admin_id = request.cookies.get('user_id')
    
    # Проверяем, не пытается ли админ удалить сам себя
    if str(user_id) == admin_id:
        return jsonify({"error": "Вы не можете удалить свой собственный аккаунт"}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные пользователя перед удалением для логирования
        cursor.execute("SELECT username, email FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        # Удаляем пользователя
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        
        # Логируем удаление пользователя
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        AdminLogger.warning('admin', f'Удаление пользователя #{user_id}', 
                           {'admin_id': admin_id, 'user': {'id': user_id, 'username': user_data[0], 'email': user_data[1]}, 'ip': ip})
        
        # Записываем действие в лог администратора
        cursor.execute(
            """
            INSERT INTO admin_actions 
            (admin_id, action_type, entity_type, entity_id, old_data, ip_address) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (admin_id, "user_delete", "user", user_id, json.dumps({'username': user_data[0], 'email': user_data[1]}), ip)
        )
        conn.commit()
        
        return jsonify({"success": True, "message": "Пользователь успешно удален"})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при удалении пользователя #{user_id}: {str(e)}")
        return jsonify({"error": "Ошибка при удалении пользователя"}), 500
    finally:
        cursor.close()
        conn.close()

# Страница управления пользователями
@admin_bp.route("/admin/users", methods=["GET"])
@admin_required
def admin_users():
    user_id = request.cookies.get('user_id')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные о текущем пользователе (для navbar)
        cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")
        
        # Устанавливаем дефолтный аватар для текущего пользователя
        current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")
        
        return render_template(
            "admin/users.html",
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar,
            current_user_status=current_user_status
        )
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при загрузке страницы управления пользователями: {str(e)}")
        return jsonify({"error": "Ошибка при загрузке страницы управления пользователями"}), 500
    finally:
        cursor.close()
        release_db_connection(conn)

# API для обновления данных пользователя
@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@admin_required
def update_user(user_id):
    admin_id = request.cookies.get('user_id')
    
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем текущие данные пользователя для логирования изменений
        cursor.execute("SELECT username, email, status FROM users WHERE id = %s", (user_id,))
        current_user_data = cursor.fetchone()
        
        if not current_user_data:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        # Формируем старые данные для записи в лог
        old_data = {
            'username': current_user_data[0],
            'email': current_user_data[1],
            'status': current_user_data[2]
        }
        
        # Проверяем, не пытается ли администратор изменить свой собственный статус
        is_changing_own_status = int(admin_id) == user_id and 'status' in data and data['status'] != 'admin'
        if is_changing_own_status:
            return jsonify({"error": "Вы не можете понизить свой собственный уровень доступа"}), 403
        
        # Обновляем пользователя
        update_fields = []
        update_values = []
        
        if 'username' in data:
            update_fields.append("username = %s")
            update_values.append(data['username'])
            
        if 'email' in data:
            update_fields.append("email = %s")
            update_values.append(data['email'])
        
        if 'status' in data:
            valid_statuses = ['user', 'admin', 'coder']
            if data['status'] not in valid_statuses:
                return jsonify({"error": "Недопустимый статус пользователя"}), 400
            update_fields.append("status = %s")
            update_values.append(data['status'])
        
        if 'password' in data and data['password']:
            # Проверка сложности пароля
            if not is_strong_password(data['password']):
                return jsonify({"error": "Пароль должен содержать минимум 8 символов, включая заглавные и строчные буквы, цифры и специальные символы"}), 400
            
            hashed_pass = hash_password(data['password'])
            update_fields.append("hashed_password = %s")
            update_values.append(hashed_pass)
        
        if not update_fields:
            return jsonify({"error": "Не указаны поля для обновления"}), 400
        
        # Формируем и выполняем запрос на обновление
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
        update_values.append(user_id)
        
        cursor.execute(query, update_values)
        conn.commit()
        
        # Формируем новые данные для записи в лог
        new_data = {}
        if 'username' in data:
            new_data['username'] = data['username']
        if 'email' in data:
            new_data['email'] = data['email']
        if 'status' in data:
            new_data['status'] = data['status']
        if 'password' in data and data['password']:
            new_data['password'] = '******'  # Не сохраняем сам пароль
            
        # Записываем действие в лог администратора
        try:
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            cursor.execute(
                """
                INSERT INTO admin_actions 
                (admin_id, action_type, entity_type, entity_id, old_data, new_data, ip_address) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (admin_id, "user_update", "user", user_id, json.dumps(old_data), json.dumps(new_data), ip)
            )
            
            conn.commit()
            
            # Используем более безопасный способ логирования для предотвращения TypeError
            success_message = f"Администратор #{admin_id} обновил пользователя #{user_id}"
            AdminLogger.info('admin', success_message, details=new_data, user_id=admin_id)
        except Exception as log_error:
            # Отдельный блок для обработки ошибок логирования
            print(f"Ошибка при логировании: {str(log_error)}")
            # Не вызываем здесь AdminLogger, чтобы избежать рекурсивных ошибок
        
        return jsonify({"success": True, "message": "Данные пользователя обновлены"})
    except Exception as e:
        # Обрабатываем ошибку более детально
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        
        try:
            AdminLogger.error('admin', f"Ошибка при обновлении пользователя #{user_id}: {str(e)}", details=error_details, user_id=admin_id)
        except Exception as log_error:
            # Если логирование не удалось, выводим ошибку в консоль
            print(f"Ошибка при логировании исключения: {str(log_error)}")
            
        return jsonify({"error": "Ошибка при обновлении пользователя"}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

# API для отправки уведомлений пользователям
@admin_bp.route("/api/admin/notifications", methods=["POST"])
@admin_required
def send_notification():
    admin_id = request.cookies.get('user_id')
    
    try:
        data = request.json
        required_fields = ['user_id', 'title', 'message', 'severity']
        
        # Проверяем наличие всех необходимых полей
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Отсутствует обязательное поле {field}"}), 400
        
        # Проверяем уровень серьезности уведомления
        valid_severities = ['info', 'warning', 'error']
        if data['severity'] not in valid_severities:
            return jsonify({"error": "Недопустимый уровень уведомления"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Если user_id - это массив, создаем уведомления для каждого пользователя
        user_ids = data['user_id'] if isinstance(data['user_id'], list) else [data['user_id']]
        processed_users = []
        
        for user_id in user_ids:
            try:
                user_id = int(user_id)  # убедимся, что ID - это число
                cursor.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                
                if not user:
                    continue  # пропускаем несуществующих пользователей
                
                # Создаем уведомление для пользователя
                cursor.execute(
                    """
                    INSERT INTO user_notifications 
                    (user_id, title, message, severity) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, data['title'], data['message'], data['severity'])
                )
                processed_users.append(user_id)
            except (ValueError, TypeError) as e:
                # Логируем ошибку, но продолжаем с другими пользователями
                print(f"Ошибка при обработке ID пользователя {user_id}: {str(e)}")
                continue
        
        # Важно! Выполняем commit после всех вставок
        conn.commit()
        
        if not processed_users:
            return jsonify({"error": "Не удалось отправить уведомление ни одному из указанных пользователей"}), 400
        
        # Записываем действие в лог администратора
        try:
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            cursor.execute(
                """
                INSERT INTO admin_actions 
                (admin_id, action_type, entity_type, entity_id, old_data, new_data, ip_address) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    admin_id, 
                    "send_notification", 
                    "user", 
                    json.dumps(processed_users), 
                    None, 
                    json.dumps(data), 
                    ip
                )
            )
            
            conn.commit()
            
            # Логирование действия
            AdminLogger.info(
                'admin', 
                f"Администратор отправил уведомление пользователям (кол-во: {len(processed_users)})", 
                details={"notification": data, "user_ids": processed_users},
                user_id=admin_id
            )
            
            return jsonify({"success": True, "message": f"Уведомление отправлено {len(processed_users)} пользователям"})
        except Exception as log_error:
            conn.rollback()
            print(f"Ошибка при логировании отправки уведомления: {str(log_error)}")
            # Возвращаем успех, так как уведомления были отправлены даже если логирование не удалось
            return jsonify({"success": True, "message": f"Уведомление отправлено, но возникла ошибка при логировании"})
    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
            
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        
        try:
            AdminLogger.error('admin', f"Ошибка при отправке уведомления: {str(e)}", details=error_details, user_id=admin_id)
        except Exception as log_error:
            print(f"Ошибка при логировании исключения: {str(log_error)}")
            
        return jsonify({"error": "Ошибка при отправке уведомления"}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

# API для получения уведомлений пользователя (для админов)
@admin_bp.route("/api/admin/users/<int:user_id>/notifications", methods=["GET"])
@admin_required
def get_user_notifications(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверка существования пользователя
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"error": "Пользователь не найден"}), 404
        
        # Получаем все уведомления пользователя
        cursor.execute(
            """
            SELECT id, title, message, severity, is_read, created_at
            FROM user_notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        
        notifications = []
        for notification in cursor.fetchall():
            notifications.append({
                "id": notification[0],
                "title": notification[1],
                "message": notification[2],
                "severity": notification[3],
                "is_read": notification[4],
                "created_at": notification[5].strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({"notifications": notifications})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении уведомлений пользователя #{user_id}: {str(e)}")
        return jsonify({"error": "Ошибка при получении уведомлений"}), 500
    finally:
        cursor.close()
        conn.close()

# API для получения недавних уведомлений
@admin_bp.route("/admin/notifications/recent", methods=["GET"])
@admin_required
def get_recent_notifications():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем последние уведомления из таблицы user_notifications вместо admin_logs
        cursor.execute("""
            SELECT id, user_id, title, message, severity, created_at
            FROM user_notifications
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        logs = []
        for notification in cursor.fetchall():
            logs.append({
                "id": notification[0],
                "user_id": notification[1],
                "action": "send_notification",  # Константа для совместимости
                "details": json.dumps({
                    "notification": {
                        "title": notification[2],
                        "message": notification[3],
                        "severity": notification[4]
                    },
                    "user_ids": [notification[1]]
                }),
                "created_at": notification[5].strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({"success": True, "logs": logs})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении недавних уведомлений: {str(e)}")
        return jsonify({"error": "Ошибка при получении недавних уведомлений"}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

# Страница логов системы
@admin_bp.route("/admin/logs", methods=["GET"])
@admin_required
def admin_logs():
    user_id = request.cookies.get('user_id')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные о текущем пользователе (для navbar)
        cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")
        
        # Устанавливаем дефолтный аватар для текущего пользователя
        current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")
        
        # Получаем доступные источники логов
        cursor.execute("SELECT DISTINCT source FROM system_logs")
        sources = [source[0] for source in cursor.fetchall()]
        
        return render_template(
            "admin/logs.html",
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar,
            current_user_status=current_user_status,
            sources=sources
        )
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при загрузке страницы логов: {str(e)}")
        return jsonify({"error": "Ошибка при загрузке страницы логов"}), 500
    finally:
        cursor.close()
        release_db_connection(conn)

# Маршрут для страницы уведомлений
@admin_bp.route("/admin/notifications")
@admin_required
def admin_notifications():
    user_id = request.cookies.get('user_id')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные о текущем пользователе (для navbar)
        cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")
        
        # Устанавливаем дефолтный аватар для текущего пользователя
        current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")
        
        # Получаем список всех пользователей для селектора
        cursor.execute("SELECT id, username, avatar FROM users")
        users = cursor.fetchall()
        
        # Получаем количество непрочитанных уведомлений для админа
        cursor.execute("""
            SELECT COUNT(*) FROM admin_notifications
            WHERE admin_id = %s AND is_read = FALSE
        """, (user_id,))
        unread_notifications = cursor.fetchone()[0]
        
        # Получаем общее количество уведомлений
        cursor.execute("""
            SELECT COUNT(*) FROM admin_notifications
            WHERE admin_id = %s
        """, (user_id,))
        total_notifications = cursor.fetchone()[0]
        
        # Получаем недавние уведомления
        cursor.execute("""
            SELECT id, title, message, created_at 
            FROM admin_notifications 
            WHERE admin_id = %s
            ORDER BY created_at DESC 
            LIMIT 5
        """, (user_id,))
        recent_notifications = cursor.fetchall()
        
        # Форматируем текущую дату и время для шаблона
        current_datetime = datetime.now().strftime('%d %b. %Y г., %H:%M:%S')
        
        return render_template(
            'admin/notifications.html',
            users=users,
            recent_notifications=recent_notifications,
            total_notifications=total_notifications,
            unread_notifications=unread_notifications,
            current_datetime=current_datetime,
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar
        )
    except Exception as e:
        print(f"Ошибка при загрузке страницы уведомлений: {str(e)}")
        return render_template(
            'admin/notifications.html',
            users=[],
            recent_notifications=[],
            total_notifications=0,
            unread_notifications=0,
            error=str(e),
            current_user_username="Admin",
            current_user_avatar='default-avatar.png'
        )
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

# API для добавления лога через API (может использоваться другими частями приложения)
@admin_bp.route("/api/admin/log", methods=["POST"])
def add_log():
    try:
        data = request.json
        required_fields = ['level', 'source', 'message']
        
        # Проверяем наличие всех необходимых полей
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Отсутствует обязательное поле {field}"}), 400
        
        # Проверяем валидность уровня лога
        valid_levels = ['INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if data['level'] not in valid_levels:
            return jsonify({"error": "Недопустимый уровень лога"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем IP-адрес и user_id, если есть
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_id = request.cookies.get('user_id')
        
        # Добавляем запись в таблицу логов
        cursor.execute(
            """
            INSERT INTO system_logs 
            (level, source, message, details, ip_address, user_id) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                data['level'],
                data['source'],
                data['message'],
                json.dumps(data.get('details', {})),
                ip,
                user_id
            )
        )
        
        conn.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при добавлении лога: {str(e)}")
        return jsonify({"error": "Ошибка при добавлении лога"}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)

# Функция для проверки сложности пароля
def is_strong_password(password):
    """
    Проверяет, соответствует ли пароль требованиям сложности:
    - Длина не менее 8 символов
    - Содержит как минимум одну заглавную букву
    - Содержит как минимум одну строчную букву
    - Содержит как минимум одну цифру
    - Содержит как минимум один специальный символ
    """
    if len(password) < 8:
        return False
    
    if not re.search(r'[A-Z]', password):  # Заглавная буква
        return False
    
    if not re.search(r'[a-z]', password):  # Строчная буква
        return False
    
    if not re.search(r'[0-9]', password):  # Цифра
        return False
    
    if not re.search(r'[^A-Za-z0-9]', password):  # Спецсимвол
        return False
    
    return True
