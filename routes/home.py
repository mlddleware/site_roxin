from datetime import datetime, timezone
from flask import Blueprint, render_template, request
from database.connection import get_db_connection

home_bp = Blueprint('/', __name__)

@home_bp.route("/")
def home():
    user_id = request.cookies.get("user_id")
    user_status = None
    orders_count = 0

    if user_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Обновляем last_visit
            cursor.execute("UPDATE user_profiles SET last_visit = %s WHERE user_id = %s", (datetime.now(timezone.utc), user_id))
            conn.commit()

            # Получаем статус пользователя
            cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            if result:
                user_status = result[0]

            # Получаем количество заказов
            if user_status == "admin":
                cursor.execute("SELECT COUNT(*) FROM order_status")
                orders_count = cursor.fetchone()[0]

            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Ошибка при обновлении времени последнего визита: {e}")

    return render_template("index.html", user_id=user_id, user_status=user_status, orders_count=orders_count)

@home_bp.route("/help")
def help_page():
    user_id = request.cookies.get("user_id")
    user_status = None
    username = None
    avatar = "user.png"  # Аватар по умолчанию
    
    if user_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Получаем статус пользователя и имя
            cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            if result:
                user_status = result[0]
                username = result[1]
                if result[2]:  # Если у пользователя есть аватар
                    avatar = result[2]
                    
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Ошибка при получении данных пользователя: {e}")
    
    return render_template("help.html", user_status=user_status, username=username, avatar=avatar)

@home_bp.route("/empty-page")
def empty_page():
    user_id = request.cookies.get("user_id")
    user_status = None
    username = None
    avatar = "user.png"  # Аватар по умолчанию
    
    if user_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Получаем статус пользователя и имя
            cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            if result:
                user_status = result[0]
                username = result[1]
                if result[2]:  # Если у пользователя есть аватар
                    avatar = result[2]
                    
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Ошибка при получении данных пользователя: {e}")
    
    return render_template("empty_page.html", user_status=user_status, username=username, avatar=avatar)