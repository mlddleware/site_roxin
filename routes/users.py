from flask import Blueprint, make_response, render_template, request, redirect, url_for, jsonify
from utils.logging import logging
from database.connection import get_db_connection
import pytz
from datetime import datetime, timezone, timedelta

users_bp = Blueprint('users', __name__)

def format_last_visit(last_visit, user_tz):
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
    current_user_id = request.cookies.get('user_id')
    if not current_user_id:
        return redirect(url_for('login.login'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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
        online_status = format_last_visit(last_visit, user_tz) if last_visit else "Последнее посещение неизвестно"

        # Форматируем дату регистрации``
        registration_date_info = format_last_visit(created_at, user_tz) if created_at else "Нет данных"

        # Подсчет количества заказов для админа
        orders_count = 0
        if status == "admin":
            cursor.execute("SELECT COUNT(*) FROM order_status")
            orders_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return render_template(
            "user_profile.html",
            username=username,
            avatar=avatar,
            status=status,
            user_id=user_id,
            current_user_username=current_user_username,
            current_user_avatar=current_user_avatar,
            current_user_status=current_user_status,
            direction=direction,
            completed_orders=completed_orders,
            reviews_count=reviews_count,
            rating=rating,
            avg_completion_time=avg_completion_time,
            warn=warn,
            online_status=online_status,
            registration_date_info=registration_date_info,
            orders_count=orders_count
        )
    except Exception as e:
        logging.error(f"Ошибка при загрузке профиля пользователя {user_id}: {str(e)}")
        return jsonify({"error": "Ошибка при загрузке профиля"}), 500
