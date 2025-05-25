from flask import Blueprint, make_response, render_template, request, redirect, url_for, jsonify
from utils.logging import logging
from database.connection import DatabaseConnection
from database.redis_cache import cache_set, cache_get, invalidate_cache
import pytz
from datetime import datetime, timezone, timedelta
import time

users_bp = Blueprint('users', __name__)

def format_last_visit(last_visit, user_tz):
    # Приводим last_visit к timezone-aware формату, если он timezone-naive
    if last_visit.tzinfo is None:
        last_visit = last_visit.replace(tzinfo=timezone.utc)
        
    now = datetime.now(timezone.utc)
    time_diff = now - last_visit

    # Конвертируем разницу во времени
    minutes = int(time_diff.total_seconds() / 60)
    hours = minutes // 60
    days = hours // 24

    def get_minutes_form(n):
        """Возвращает правильную форму слова 'минута'"""
        n = abs(n)
        if n % 10 == 1 and n % 100 != 11:
            return "минуту"
        elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
            return "минуты"
        return "минут"

    def get_hours_form(n):
        """Возвращает правильную форму слова 'час'"""
        n = abs(n)
        if n % 10 == 1 and n % 100 != 11:
            return "час"
        elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
            return "часа"
        return "часов"

    def get_days_form(n):
        """Возвращает правильную форму слова 'день'"""
        n = abs(n)
        if n % 10 == 1 and n % 100 != 11:
            return "день"
        elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
            return "дня"
        return "дней"

    if minutes < 1:
        return "Онлайн"
    elif minutes < 60:
        return f"Был {minutes} {get_minutes_form(minutes)} назад"
    elif hours < 24:
        return f"Был {hours} {get_hours_form(hours)} назад"
    elif days < 7:
        return f"Был {days} {get_days_form(days)} назад"
    else:
        return last_visit.astimezone(user_tz).strftime('%d.%m.%Y %H:%M')

def get_user_timezone():
    """Получает часовой пояс пользователя из cookies или устанавливает UTC по умолчанию."""
    user_timezone = request.cookies.get("user_timezone", "UTC")
    try:
        return pytz.timezone(user_timezone)
    except pytz.UnknownTimeZoneError:
        return pytz.utc

@users_bp.route("/users/<int:user_id>/", methods=["GET"])
def user_profile(user_id):
    start_time = time.time()
    current_user_id = request.cookies.get('user_id')
    if not current_user_id:
        return redirect(url_for('login.login'))
    
    # Создаем ключ кэша, который учитывает ID просматриваемого профиля и текущего пользователя
    cache_key = f"user_profile:{user_id}:{current_user_id}"
    
    # Проверяем наличие данных в кэше
    cached_data = cache_get(cache_key)
    if cached_data:
        print(f"Данные профиля пользователя {user_id} получены из кэша ({time.time() - start_time:.6f} сек)")
        return render_template("user_profile.html", **cached_data)

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()

        # Получаем данные о пользователе и его профиле одним запросом
        cursor.execute("""
            SELECT u.username, u.avatar, u.status, u.created_at, up.last_visit, 
                   e.direction, e.completed_orders, e.reviews_count, e.rating, e.avg_completion_time, e.warn
            FROM users u
            LEFT JOIN user_profiles up ON u.id = up.user_id
            LEFT JOIN employees e ON u.id = e.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            return make_response("Пользователь не найден", 404)

        (username, avatar, status, created_at, last_visit, 
         direction, completed_orders, reviews_count, rating, avg_completion_time, warn) = user_data

        # Устанавливаем дефолтный аватар
        avatar = avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(status, "user.png")

        # Получаем данные о текущем пользователе (для navbar)
        cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (current_user_id,))
        current_user = cursor.fetchone()
        current_user_username, current_user_avatar, current_user_status = current_user or ("Гость", "default.png", "guest")

        # Устанавливаем дефолтный аватар для текущего пользователя
        current_user_avatar = current_user_avatar or {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}.get(current_user_status, "user.png")

        # Приводим `created_at` и `last_visit` к timezone-aware формату
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if last_visit and last_visit.tzinfo is None:
            last_visit = last_visit.replace(tzinfo=timezone.utc)

        # Конвертируем `last_visit` в локальный часовой пояс пользователя
        user_tz = get_user_timezone()
        last_visit_str = last_visit.astimezone(user_tz).strftime('%d.%m.%Y %H:%M') if last_visit else "Нет данных"

        # Определяем, онлайн ли пользователь
        now = datetime.now(timezone.utc)
        # Определяем онлайн-статус с помощью новой функции
        online_status_text = format_last_visit(last_visit, user_tz) if last_visit else "Последнее посещение неизвестно"
        is_offline = online_status_text != "Онлайн"

        # Форматируем дату регистрации``
        registration_date_info = format_last_visit(created_at, user_tz) if created_at else "Нет данных"

        # Подсчет количества заказов для админа
        orders_count = 0
        if status == "admin":
            cursor.execute("SELECT COUNT(*) FROM order_status")
            orders_count = cursor.fetchone()[0]

        # Получаем отзывы для разработчиков
        reviews = []
        if status == "coder":
            cursor.execute("""
                SELECT 
                    ca.review, 
                    ca.review_time, 
                    ca.rating,
                    co.user_id,
                    u.username,
                    u.avatar
                FROM 
                    order_status os
                JOIN 
                    customer_orders co ON os.order_id = co.id
                JOIN 
                    users u ON co.user_id = u.id
                JOIN 
                    coder_assignments ca ON os.order_id = ca.order_id
                WHERE 
                    os.coder = %s 
                    AND ca.review IS NOT NULL 
                    AND ca.review != ''
                    AND ca.rating IS NOT NULL
                ORDER BY 
                    ca.review_time DESC
                LIMIT 10
            """, (user_id,))
            
            reviews_data = cursor.fetchall()
            for review_text, review_date, review_rating, reviewer_id, reviewer_name, reviewer_avatar in reviews_data:
                # Проверяем, есть ли у пользователя аватар
                if not reviewer_avatar:
                    reviewer_avatar = "user.png"
                
                # Форматируем дату отзыва в нормальном формате
                if review_date:
                    if review_date.tzinfo is None:
                        review_date = review_date.replace(tzinfo=timezone.utc)
                    review_date_local = review_date.astimezone(user_tz)
                    months_ru = {
                        1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
                        7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
                    }
                    review_date_formatted = review_date_local.strftime(f"%d {months_ru[review_date_local.month]} %Y")
                else:
                    review_date_formatted = "Не указано"
                    
                reviews.append({
                    'rating': review_rating or 0,
                    'text': review_text,
                    'date': review_date_formatted,
                    'reviewer_name': reviewer_name,
                    'reviewer_avatar': reviewer_avatar
                })

        # Готовим данные для шаблона и кэширования
        template_data = {
            # Данные просматриваемого пользователя
            "target_username": username,
            "target_avatar": avatar,
            "target_status": status,
            "target_user_id": user_id,
            "target_direction": direction,
            "target_completed_orders": completed_orders,
            "target_reviews_count": reviews_count,
            "target_rating": rating,
            "target_avg_completion_time": avg_completion_time,
            "target_warn": warn,
            "target_online_status": online_status_text,
            "target_registration_date_info": registration_date_info,
            "target_orders_count": orders_count,
            "target_reviews": reviews,
            "target_is_offline": is_offline,
            
            # Данные текущего пользователя для navbar
            "username": current_user_username,
            "avatar": current_user_avatar,
            "status": current_user_status,
            "current_user_username": current_user_username,
            "current_user_avatar": current_user_avatar,
            "current_user_status": current_user_status
        }
        
        # Сохраняем в кэш на 3 минуты
        cache_set(cache_key, template_data, 180)
        print(f"Данные профиля пользователя {user_id} сохранены в кэш ({time.time() - start_time:.6f} сек)")

        return render_template("user_profile.html", **template_data)
    except Exception as e:
        logging.error(f"Ошибка при загрузке профиля пользователя {user_id}: {str(e)}")
        return jsonify({"error": "Ошибка при загрузке профиля"}), 500
