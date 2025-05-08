from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from database.connection import get_db_connection, release_db_connection
import pytz
import time
from security.access_control import require_role, UserRole

profile_bp = Blueprint('profile', __name__)

# Функция форматирования даты регистрации
def format_registration_date(created_at, user_tz):
    """Форматирует дату регистрации в удобочитаемый вид."""
    start_time = time.time()

    months_ru = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
        7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    created_at_local = created_at.astimezone(user_tz)
    formatted_date = created_at_local.strftime(f"%d {months_ru[created_at_local.month]} %Y, %H:%M")

    delta = datetime.now(timezone.utc).astimezone(user_tz) - created_at_local
    years, months = divmod(delta.days, 365)[0], (delta.days % 365) // 30

    if years > 0:
        time_ago = f"{years} {'год' if years == 1 else 'года' if 2 <= years <= 4 else 'лет'} назад"
    elif months > 0:
        time_ago = f"{months} {'месяц' if months == 1 else 'месяца' if 2 <= months <= 4 else 'месяцев'} назад"
    else:
        time_ago = "Меньше месяца назад"

    print(f"Время выполнения format_registration_date: {time.time() - start_time:.6f} сек")
    return f"{formatted_date}\n{time_ago}"

@profile_bp.route('/update_last_visit', methods=['POST'])
def update_last_visit():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            current_time = datetime.now(timezone.utc)
            cursor.execute("""
                UPDATE user_profiles 
                SET last_visit = %s 
                WHERE user_id = %s
            """, (current_time, user_id))
        conn.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Ошибка при обновлении last_visit: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)

@profile_bp.route('/profile/info', methods=['GET'])
@require_role(UserRole.USER)
def profile_info():
    """API для получения базовой информации о профиле"""
    user_id = request.cookies.get('user_id')
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({"error": "Пользователь не найден"}), 404
            
        return jsonify({
            "username": user_data[0]
        })
    except Exception as e:
        print(f"Ошибка при получении информации о профиле: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

@profile_bp.route("/profile")
def profile():
    start_time = time.time()
    
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('register.register'))

    print(f"Получение user_id из куков заняло: {time.time() - start_time:.6f} сек")

    conn = None
    try:
        conn = get_db_connection()
        print(f"Создание подключения к БД заняло: {time.time() - start_time:.6f} сек")

        current_time = datetime.now(timezone.utc)

        with conn.cursor() as cursor:
            # Объединяем UPDATE last_visit и SELECT user data
            cursor.execute("""
                WITH updated AS (
                    UPDATE user_profiles
                    SET last_visit = %s
                    WHERE user_id = %s
                    RETURNING user_id, last_visit  -- Добавляем user_id
                )
                SELECT u.username, u.status, u.avatar, u.balance, u.created_at, up.last_visit,
                    e.direction, e.coin, e.completed_orders, e.reviews_count, e.rating, e.avg_completion_time, e.warn
                FROM users u
                LEFT JOIN updated up ON u.id = up.user_id  -- Теперь user_id есть
                LEFT JOIN employees e ON u.id = e.user_id
                WHERE u.id = %s

            """, (current_time, user_id, user_id))

            user_data = cursor.fetchone()

        print(f"Основной SQL-запрос занял: {time.time() - start_time:.6f} сек")

        if not user_data:
            return redirect(url_for('logout.logout'))

        # Распаковываем данные
        (username, status, avatar, balance, created_at, last_visit, 
         direction, coin, completed_orders, reviews_count, rating, avg_completion_time, warn) = user_data

        print(f"Данные пользователя: {username}, статус: {status}")

        avatar = avatar or {
            "user": "user.png",
            "admin": "admin.png",
            "coder": "coder.png",
            "designer": "designer.png"
        }.get(status, "user.png")

        user_tz = pytz.timezone(request.cookies.get("user_timezone", "UTC"))

        # Форматируем дату регистрации
        registration_start = time.time()
        registration_date_info = format_registration_date(created_at, user_tz) if created_at else "Нет данных"
        print(f"Обработка даты регистрации заняла: {time.time() - registration_start:.6f} сек")

        # Форматируем last_visit
        last_visit_start = time.time()
        if last_visit:
            last_visit = last_visit.replace(tzinfo=timezone.utc)
            last_visit_str = last_visit.astimezone(user_tz).strftime('%d.%m.%Y %H:%M')
            online_status = "Онлайн" if (current_time - last_visit) <= timedelta(minutes=1) else f"Был в сети {last_visit_str}"
        else:
            last_visit_str = "Нет данных"
            online_status = "Нет данных"
        print(f"Обработка last_visit заняла: {time.time() - last_visit_start:.6f} сек")

        orders_count = 0
        user_orders_count = 0
        employees_data = None

        if status == "admin":
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM order_status")
                orders_count = cursor.fetchone()[0]

        if status == "user":
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE user_id = %s", (user_id,))
                user_orders_count = cursor.fetchone()[0]

        if status in {"coder", "designer", "intern"}:
            employees_data = {
                "direction": direction,
                "coin": coin,
                "completed_orders": completed_orders,
                "reviews_count": reviews_count,
                "rating": rating,
                "avg_completion_time": avg_completion_time,
                "warn": warn,
                "balance": balance
            }

        render_start = time.time()
        response = render_template(
            "profile.html",
            username=username,
            status=status,
            avatar=avatar,
            employees_data=employees_data,
            orders_count=orders_count,
            user_orders_count=user_orders_count,
            balance=balance,
            online_status=online_status,
            registration_date_info=registration_date_info
        )
        print(f"Рендеринг HTML занял: {time.time() - render_start:.6f} сек")

        print(f"Общее время загрузки профиля: {time.time() - start_time:.6f} сек")
        return response

    except Exception as e:
        print(f"Ошибка при загрузке профиля: {e}")
        return jsonify({"error": "Ошибка при загрузке профиля"}), 500

    finally:
        if conn:
            release_db_connection(conn)
        print("Соединение с БД закрыто")
