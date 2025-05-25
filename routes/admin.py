from flask import Blueprint, render_template, request, jsonify, session, abort, redirect, url_for
from flask import Blueprint, render_template, redirect, url_for, request, abort, jsonify
from database.connection import get_db_connection, release_db_connection, DatabaseConnection
from utils.logging import logger
from utils.admin_logger import AdminLogger
from security.password_utils import hash_password, check_password
from datetime import datetime, timedelta, timezone
import secrets
import re
import json
import logging
import traceback
from functools import wraps
import uuid
import string
import random

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
            with DatabaseConnection() as db:
                cursor = db.cursor()
                cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                
                if not user or user[0] != 'admin':
                    abort(403)  # Доступ запрещен
                    
            return f(*args, **kwargs)
        except Exception as e:
            AdminLogger.error('admin', f"Ошибка при проверке прав администратора: {str(e)}")
            abort(500)
    
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

# API для получения списка пользователей
@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def get_users_list():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'asc')
        
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование таблицы user_bans
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'user_bans'
            )
        """)
        user_bans_table_exists = cursor.fetchone()[0]
        
        # Базовый запрос для получения пользователей
        if user_bans_table_exists:
            query = """
                SELECT u.id, u.username, u.email, u.status, u.created_at, p.last_visit,
                       EXISTS(
                           SELECT 1 FROM user_bans b
                           WHERE b.user_id = u.id
                           AND b.active = TRUE
                           AND (b.expires_at IS NULL OR b.expires_at > NOW())
                       ) as is_banned
                FROM users u
                LEFT JOIN user_profiles p ON u.id = p.user_id
                WHERE 1=1
            """
        else:
            # Если таблицы user_bans нет, используем запрос без нее
            query = """
                SELECT u.id, u.username, u.email, u.status, u.created_at, p.last_visit, FALSE as is_banned
                FROM users u
                LEFT JOIN user_profiles p ON u.id = p.user_id
                WHERE 1=1
            """
        
        # Параметры для запроса
        params = []
        
        # Добавляем фильтр по статусу, если указан
        if status:
            query += " AND u.status = %s"
            params.append(status)
        
        # Добавляем поиск, если указан
        if search:
            query += " AND (u.username ILIKE %s OR u.email ILIKE %s)"
            search_param = f'%{search}%'
            params.extend([search_param, search_param])
        
        # Добавляем сортировку
        if sort_by in ['id', 'username', 'email', 'status', 'created_at', 'last_visit']:
            sort_direction = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
            if sort_by == 'last_visit':
                query += f" ORDER BY p.{sort_by} {sort_direction}, u.id ASC"
            else:
                query += f" ORDER BY u.{sort_by} {sort_direction}, u.id ASC"
        else:
            query += " ORDER BY u.id ASC"
        
        # Добавляем пагинацию
        query_count = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cursor.execute(query_count, params)
        total_count = cursor.fetchone()[0]
        
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        users = cursor.fetchall()
        
        result = []
        for user in users:
            result.append({
                'id': user[0],
                'username': user[1],
                'email': user[2],
                'status': user[3],
                'created_at': user[4].isoformat() if user[4] else None,
                'last_visit': user[5].isoformat() if user[5] else None,
                'is_banned': user[6] if user[6] is not None else False
            })
        
        total_pages = (total_count + limit - 1) // limit
        
        response = {
            'success': True,
            'users': result,
            'total': total_count,
            'pages': total_pages,
            'current_page': page
        }
        
        return jsonify(response)
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении списка пользователей: {str(e)}")
        print(f"Ошибка при получении списка пользователей: {str(e)}")
        return jsonify({"success": False, "error": "Ошибка при загрузке данных. Пожалуйста, попробуйте позже."}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

# API для работы с отдельным пользователем
@admin_bp.route("/api/admin/users/<int:user_id>", methods=["GET", "PUT", "DELETE"])
@admin_required
def manage_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли пользователь
        cursor.execute("SELECT id, username, email, status FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"success": False, "error": "Пользователь не найден"}), 404
        
        # GET - получение информации о пользователе
        if request.method == "GET":
            return jsonify({
                "success": True,
                "user": {
                    "id": user[0],
                    "username": user[1],
                    "email": user[2],
                    "status": user[3]
                }
            })
        
        # PUT - обновление пользователя
        elif request.method == "PUT":
            data = request.json
            
            # Получаем данные для обновления
            username = data.get("username")
            email = data.get("email")
            status = data.get("status")
            password = data.get("password")
            
            # Проверяем наличие обязательных полей
            if not username or not email or not status:
                return jsonify({"success": False, "error": "Необходимо указать имя пользователя, email и статус"}), 400
            
            # Проверяем, не занято ли имя пользователя или email другим пользователем
            cursor.execute("SELECT id FROM users WHERE (username = %s OR email = %s) AND id != %s", (username, email, user_id))
            if cursor.fetchone():
                return jsonify({"success": False, "error": "Имя пользователя или email уже заняты"}), 400
            
            # Формируем запрос на обновление
            update_query = "UPDATE users SET username = %s, email = %s, status = %s"
            params = [username, email, status]
            
            # Если указан новый пароль, обновляем его
            if password:
                from security.password_utils import hash_password
                hashed_password = hash_password(password)
                update_query += ", hashed_password = %s"
                params.append(hashed_password)
            
            update_query += " WHERE id = %s"
            params.append(user_id)
            
            cursor.execute(update_query, params)
            conn.commit()
            
            return jsonify({"success": True, "message": "Пользователь успешно обновлен"})
        
        # DELETE - удаление пользователя
        elif request.method == "DELETE":
            # Проверяем, не удаляем ли сами себя
            admin_id = request.cookies.get('user_id')
            if int(admin_id) == user_id:
                return jsonify({"success": False, "error": "Нельзя удалить свой собственный аккаунт"}), 400
            
            # Удаляем пользователя
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            
            return jsonify({"success": True, "message": "Пользователь успешно удален"})
    
    except Exception as e:
        conn.rollback()
        AdminLogger.error('admin', f"Ошибка при работе с пользователем: {str(e)}")
        return jsonify({"success": False, "error": "Ошибка при работе с пользователем"}), 500
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

# Страница транзакций
@admin_bp.route("/admin/transactions", methods=["GET"])
@admin_required
def admin_transactions():
    user_id = request.cookies.get('user_id')
    page = request.args.get('page', 1, type=int)
    filter_type = request.args.get('type', '')
    filter_status = request.args.get('status', '')
    filter_period = request.args.get('period', 'all')
    per_page = 20
    
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Получаем данные о текущем пользователе (для navbar)
            cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (user_id,))
            current_user = cursor.fetchone()
            current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")
            current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")
            
            # Получаем кол-во ожидающих запросов на вывод
            cursor.execute("""
                SELECT COUNT(*) FROM financial_transactions 
                WHERE type = 'withdraw' AND status = 'pending'
            """)
            pending_withdrawals_count = cursor.fetchone()[0]
            
            # Получаем кол-во непрочитанных уведомлений
            cursor.execute("""
                SELECT COUNT(*) FROM admin_notifications WHERE is_read = FALSE
            """)
            notifications_count = cursor.fetchone()[0]
    
            # Формируем базовый запрос
            query = """
                SELECT ft.id, ft.user_id, u.username, ft.type, ft.amount, ft.fee_amount, ft.payment_method, 
                       ft.status, ft.created_at, ft.updated_at, ft.description, ft.details
                FROM financial_transactions ft
                LEFT JOIN users u ON CAST(ft.user_id AS INTEGER) = u.id
                WHERE 1=1
            """
            params = []
            
            # Добавляем фильтры
            if filter_type:
                query += " AND ft.type = %s"
                params.append(filter_type)
                
            if filter_status:
                query += " AND ft.status = %s"
                params.append(filter_status)
                
            if filter_period != 'all':
                if filter_period == 'today':
                    query += " AND DATE(ft.created_at) = CURRENT_DATE"
                elif filter_period == 'week':
                    query += " AND ft.created_at >= DATE_TRUNC('week', CURRENT_DATE)"
                elif filter_period == 'month':
                    query += " AND ft.created_at >= DATE_TRUNC('month', CURRENT_DATE)"
                elif filter_period == '3months':
                    query += " AND ft.created_at >= CURRENT_DATE - INTERVAL '3 months'"
            
            # Получаем общее количество транзакций
            count_query = f"SELECT COUNT(*) FROM ({query}) AS filtered_transactions"
            cursor.execute(count_query, params)
            total_transactions = cursor.fetchone()[0]
            
            # Добавляем пагинацию
            query += " ORDER BY ft.created_at DESC LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])
            
            # Выполняем запрос
            cursor.execute(query, params)
            transactions = []
            for row in cursor.fetchall():
                created_at = row[8].replace(tzinfo=timezone.utc) if row[8] else None
                updated_at = row[9].replace(tzinfo=timezone.utc) if row[9] else None
                
                transactions.append({
                    "id": row[0],
                    "user_id": row[1],
                    "username": row[2],
                    "type": row[3],
                    "amount": row[4],
                    "fee_amount": row[5],
                    "payment_method": row[6],
                    "status": row[7],
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "description": row[10],
                    "details": row[11]
                })
            
            # Расчет пагинации
            pages = (total_transactions + per_page - 1) // per_page
            pagination = {
                "page": page,
                "pages": pages,
                "total": total_transactions,
                "per_page": per_page
            }
            
        return render_template(
            "admin/transactions.html",
            active_page="transactions",
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar,
            current_user_status=current_user_status,
            transactions=transactions,
            total_transactions=total_transactions,
            filter_type=filter_type,
            filter_status=filter_status,
            filter_period=filter_period,
            pagination=pagination,
            notifications_count=notifications_count,
            pending_withdrawals_count=pending_withdrawals_count,
            transactions_count=pending_withdrawals_count  # Счетчик для левого меню
        )
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при загрузке страницы транзакций: {str(e)}")
        traceback.print_exc()
        abort(500)

# Страница запросов на вывод средств
@admin_bp.route("/admin/withdrawals", methods=["GET"])
@admin_required
def admin_withdrawals():
    user_id = request.cookies.get('user_id')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Получаем данные о текущем пользователе
            cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (user_id,))
            current_user = cursor.fetchone()
            current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")
            current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")
            
            # Получаем ожидающие запросы на вывод
            cursor.execute("""
                SELECT ft.id, ft.user_id, u.username, ft.amount, ft.fee_amount, ft.payment_method, 
                       ft.status, ft.created_at, ft.updated_at, ft.details
                FROM financial_transactions ft
                LEFT JOIN users u ON CAST(ft.user_id AS INTEGER) = u.id
                WHERE ft.type = 'withdraw' AND ft.status = 'pending'
                ORDER BY ft.created_at DESC
            """)
            pending_withdrawals = []
            for row in cursor.fetchall():
                created_at = row[7].replace(tzinfo=timezone.utc) if row[7] else None
                updated_at = row[8].replace(tzinfo=timezone.utc) if row[8] else None
                
                pending_withdrawals.append({
                    "id": row[0],
                    "user_id": row[1],
                    "username": row[2],
                    "amount": row[3],
                    "fee_amount": row[4],
                    "payment_method": row[5],
                    "status": row[6],
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "details": row[9]
                })
            
            # Получаем историю выводов с пагинацией
            cursor.execute("""
                SELECT COUNT(*) FROM financial_transactions 
                WHERE type = 'withdraw' AND status IN ('completed', 'cancelled')
            """)
            total_withdrawal_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT ft.id, ft.user_id, u.username, ft.amount, ft.fee_amount, ft.payment_method, 
                       ft.status, ft.created_at, ft.updated_at, ft.details
                FROM financial_transactions ft
                LEFT JOIN users u ON CAST(ft.user_id AS INTEGER) = u.id
                WHERE ft.type = 'withdraw' AND ft.status IN ('completed', 'cancelled')
                ORDER BY ft.updated_at DESC
                LIMIT %s OFFSET %s
            """, (per_page, (page - 1) * per_page))
            
            completed_withdrawals = []
            for row in cursor.fetchall():
                created_at = row[7].replace(tzinfo=timezone.utc) if row[7] else None
                updated_at = row[8].replace(tzinfo=timezone.utc) if row[8] else None
                
                completed_withdrawals.append({
                    "id": row[0],
                    "user_id": row[1],
                    "username": row[2],
                    "amount": row[3],
                    "fee_amount": row[4],
                    "payment_method": row[5],
                    "status": row[6],
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "details": row[9]
                })
            
            # Получаем статистику выводов
            cursor.execute("""
                SELECT SUM(amount) FROM financial_transactions 
                WHERE type = 'withdraw' AND status = 'completed'
            """)
            total_withdrawn = cursor.fetchone()[0] or 0
            
            cursor.execute("""
                SELECT SUM(amount) FROM financial_transactions 
                WHERE type = 'withdraw' AND status = 'completed' 
                AND EXTRACT(MONTH FROM created_at) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
            """)
            monthly_withdrawn = cursor.fetchone()[0] or 0
            
            # Статистика по методам вывода
            cursor.execute("""
                SELECT payment_method, SUM(amount) FROM financial_transactions 
                WHERE type = 'withdraw' AND status = 'completed'
                GROUP BY payment_method
            """)
            withdrawal_methods = []
            for row in cursor.fetchall():
                withdrawal_methods.append({
                    "name": row[0],
                    "amount": row[1]
                })
            
            # Получаем кол-во непрочитанных уведомлений
            cursor.execute("""
                SELECT COUNT(*) FROM admin_notifications WHERE is_read = FALSE
            """)
            notifications_count = cursor.fetchone()[0]
            
            # Расчет пагинации
            pages = (total_withdrawal_count + per_page - 1) // per_page
            pagination = {
                "page": page,
                "pages": pages,
                "total": total_withdrawal_count,
                "per_page": per_page
            }
            
        return render_template(
            "admin/withdrawals.html",
            active_page="withdrawals",
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar,
            current_user_status=current_user_status,
            pending_withdrawals=pending_withdrawals,
            completed_withdrawals=completed_withdrawals,
            total_withdrawal_count=total_withdrawal_count,
            pagination=pagination,
            total_withdrawn=total_withdrawn,
            monthly_withdrawn=monthly_withdrawn,
            withdrawal_methods=withdrawal_methods,
            notifications_count=notifications_count,
            pending_withdrawals_count=len(pending_withdrawals),
            transactions_count=len(pending_withdrawals)  # Счетчик для левого меню
        )
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при загрузке страницы запросов на вывод: {str(e)}")
        traceback.print_exc()
        abort(500)

# Детали транзакции
@admin_bp.route("/admin/transaction/<transaction_id>", methods=["GET"])
@admin_required
def admin_transaction_details(transaction_id):
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            cursor.execute("""
                SELECT ft.*, u.username FROM financial_transactions ft
                LEFT JOIN users u ON CAST(ft.user_id AS INTEGER) = u.id
                WHERE ft.id = %s
            """, (transaction_id,))
            transaction_data = cursor.fetchone()
            
            if not transaction_data:
                return jsonify({"error": "Транзакция не найдена"}), 404
                
            # Формируем ответ
            transaction = {
                "id": transaction_data[0],
                "user_id": transaction_data[1],
                "username": transaction_data[-1],  # Последнее поле - username
                "type": transaction_data[2],
                "amount": float(transaction_data[3]),
                "fee_amount": float(transaction_data[4]) if transaction_data[4] else 0,
                "payment_method": transaction_data[5],
                "status": transaction_data[6],
                "created_at": transaction_data[7].isoformat() if transaction_data[7] else None,
                "updated_at": transaction_data[8].isoformat() if transaction_data[8] else None,
                "description": transaction_data[9],
                "details": transaction_data[10]
            }
            
            return jsonify({"transaction": transaction})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении деталей транзакции: {str(e)}")
        return jsonify({"error": "Произошла ошибка при получении данных"}), 500

# Подтверждение транзакции вывода
@admin_bp.route("/admin/transaction/<transaction_id>/approve", methods=["POST"])
@admin_required
def admin_approve_transaction(transaction_id):
    try:
        comment = request.json.get('comment', '')
        user_id = request.cookies.get('user_id')
        
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, является ли транзакция запросом на вывод в статусе pending
            cursor.execute("""
                SELECT type, status, user_id, amount FROM financial_transactions 
                WHERE id = %s
            """, (transaction_id,))
            transaction = cursor.fetchone()
            
            if not transaction:
                return jsonify({"error": "Транзакция не найдена"}), 404
                
            if transaction[0] != 'withdraw' or transaction[1] != 'pending':
                return jsonify({"error": "Эта транзакция не может быть подтверждена"}), 400
                
            # Обновляем статус транзакции
            cursor.execute("""
                UPDATE financial_transactions 
                SET status = 'completed', updated_at = %s 
                WHERE id = %s
            """, (datetime.now(timezone.utc), transaction_id))
            
            # Создаем уведомление для пользователя
            cursor.execute("""
                INSERT INTO user_notifications 
                (user_id, title, message, type, read, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                transaction[2],
                "Запрос на вывод подтвержден",
                f"Ваш запрос на вывод {transaction[3]} ₽ был подтвержден администратором." + 
                (f" Комментарий: {comment}" if comment else ""),
                "finance",
                False,
                datetime.now(timezone.utc)
            ))
            
            db.commit()
            
            AdminLogger.info('admin', f"Транзакция {transaction_id} подтверждена администратором", 
                          {"user_id": user_id, "transaction_id": transaction_id, "amount": transaction[3]})
            
            return jsonify({"success": True})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при подтверждении транзакции: {str(e)}")
        return jsonify({"error": "Произошла ошибка при обработке запроса"}), 500

# Отклонение транзакции вывода
@admin_bp.route("/admin/transaction/<transaction_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel_transaction(transaction_id):
    try:
        reason = request.json.get('reason', '')
        user_id = request.cookies.get('user_id')
        
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, является ли транзакция запросом на вывод в статусе pending
            cursor.execute("""
                SELECT type, status, user_id, amount FROM financial_transactions 
                WHERE id = %s
            """, (transaction_id,))
            transaction = cursor.fetchone()
            
            if not transaction:
                return jsonify({"error": "Транзакция не найдена"}), 404
                
            if transaction[0] != 'withdraw' or transaction[1] != 'pending':
                return jsonify({"error": "Эта транзакция не может быть отклонена"}), 400
                
            # Обновляем статус транзакции
            cursor.execute("""
                UPDATE financial_transactions 
                SET status = 'cancelled', updated_at = %s 
                WHERE id = %s
            """, (datetime.now(timezone.utc), transaction_id))
            
            # Возвращаем средства на баланс пользователя
            cursor.execute("""
                UPDATE user_profiles 
                SET balance = balance + %s 
                WHERE user_id = %s
            """, (transaction[3], transaction[2]))
            
            # Создаем уведомление для пользователя
            cursor.execute("""
                INSERT INTO user_notifications 
                (user_id, title, message, type, read, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                transaction[2],
                "Запрос на вывод отклонен",
                f"Ваш запрос на вывод {transaction[3]} ₽ был отклонен. Причина: {reason}",
                "finance",
                False,
                datetime.now(timezone.utc)
            ))
            
            db.commit()
            
            AdminLogger.info('admin', f"Транзакция {transaction_id} отклонена администратором", 
                          {"user_id": user_id, "transaction_id": transaction_id, "amount": transaction[3], "reason": reason})
            
            return jsonify({"success": True})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при отклонении транзакции: {str(e)}")
        return jsonify({"error": "Произошла ошибка при обработке запроса"}), 500

# Детали запроса на вывод
@admin_bp.route("/admin/withdrawal/<withdrawal_id>", methods=["GET"])
@admin_required
def admin_withdrawal_details(withdrawal_id):
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            cursor.execute("""
                SELECT ft.*, u.username FROM financial_transactions ft
                LEFT JOIN users u ON CAST(ft.user_id AS INTEGER) = u.id
                WHERE ft.id = %s AND ft.type = 'withdraw'
            """, (withdrawal_id,))
            withdrawal_data = cursor.fetchone()
            
            if not withdrawal_data:
                return jsonify({"error": "Запрос на вывод не найден"}), 404
                
            # Формируем ответ
            withdrawal = {
                "id": withdrawal_data[0],
                "user_id": withdrawal_data[1],
                "username": withdrawal_data[-1],  # Последнее поле - username
                "type": withdrawal_data[2],
                "amount": float(withdrawal_data[3]),
                "fee_amount": float(withdrawal_data[4]) if withdrawal_data[4] else 0,
                "payment_method": withdrawal_data[5],
                "status": withdrawal_data[6],
                "created_at": withdrawal_data[7].isoformat() if withdrawal_data[7] else None,
                "updated_at": withdrawal_data[8].isoformat() if withdrawal_data[8] else None,
                "description": withdrawal_data[9],
                "details": withdrawal_data[10]
            }
            
            return jsonify({"withdrawal": withdrawal})
    except Exception as e:
        AdminLogger.error('admin', f"Ошибка при получении деталей запроса на вывод: {str(e)}")
        return jsonify({"error": "Произошла ошибка при получении данных"}), 500

# Подтверждение запроса на вывод
@admin_bp.route("/admin/withdrawal/<withdrawal_id>/approve", methods=["POST"])
@admin_required
def admin_approve_withdrawal(withdrawal_id):
    return admin_approve_transaction(withdrawal_id)

# Отклонение запроса на вывод
@admin_bp.route("/admin/withdrawal/<withdrawal_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel_withdrawal(withdrawal_id):
    return admin_cancel_transaction(withdrawal_id)

def generate_strong_password(length=12, include_uppercase=True, include_lowercase=True, include_numbers=True, include_special=True):
    """Генерирует сложный пароль с заданными параметрами"""
    # Определяем наборы символов
    uppercase_chars = string.ascii_uppercase if include_uppercase else ''
    lowercase_chars = string.ascii_lowercase if include_lowercase else ''
    number_chars = string.digits if include_numbers else ''
    special_chars = '!@#$%^&*' if include_special else ''

    # Объединяем все наборы символов
    all_chars = uppercase_chars + lowercase_chars + number_chars + special_chars

    # Проверяем, что хотя бы один набор символов выбран
    if not all_chars:
        raise ValueError("Должен быть выбран хотя бы один набор символов")

    # Генерируем пароль
    password = []
    
    # Добавляем минимум по одному символу из каждого выбранного набора
    if include_uppercase:
        password.append(random.choice(uppercase_chars))
    if include_lowercase:
        password.append(random.choice(lowercase_chars))
    if include_numbers:
        password.append(random.choice(number_chars))
    if include_special:
        password.append(random.choice(special_chars))

    # Добавляем оставшиеся символы
    remaining_length = length - len(password)
    password.extend(random.choice(all_chars) for _ in range(remaining_length))

    # Перемешиваем пароль
    random.shuffle(password)

    return ''.join(password)
