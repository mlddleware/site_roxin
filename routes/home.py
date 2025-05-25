from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify
from database.connection import DatabaseConnection, get_db_connection
from database.redis_cache import cached, cache_set, cache_get, invalidate_cache
from database.redis_config import CACHE_SETTINGS
import time

home_bp = Blueprint('/', __name__)

@home_bp.route("/")
def home():
    start_time = time.time()
    user_id = request.cookies.get("user_id")
    user_status = None
    orders_count = 0
    username = None
    avatar = "user.png"  # Аватар по умолчанию
    
    # Генерируем ключ кэша для главной страницы
    cache_key = "home:general"
    if user_id:
        cache_key = f"home:{user_id}"
    
    # Проверяем наличие данных в кэше
    cached_data = cache_get(cache_key)
    if cached_data:
        print(f"Данные главной страницы получены из кэша ({time.time() - start_time:.6f} сек)")
        return render_template("index.html", **cached_data)

    if user_id:
        try:
            with DatabaseConnection() as db:
                cursor1 = db.cursor()

                # Обновляем last_visit
                cursor1.execute("UPDATE user_profiles SET last_visit = %s WHERE user_id = %s", (datetime.now(timezone.utc), user_id))
                db.commit()

                # Получаем данные пользователя для navbar
                cursor = db.cursor()
                cursor.execute("SELECT username, status, avatar FROM users WHERE id = %s", (user_id,))
                user_data = cursor.fetchone()
            
            if user_data:
                username, user_status, user_avatar = user_data
                # Используем аватар пользователя или дефолтный в зависимости от статуса
                avatar = user_avatar if user_avatar else f"status_{user_status}.png"

                # Получаем количество заказов для админа или пользователя
                cursor_orders = db.cursor()
                if user_status == 'admin':
                    cursor_orders.execute("SELECT COUNT(*) FROM order_status")
                    orders_count = cursor_orders.fetchone()[0]
                elif user_status == 'user':
                    cursor_orders.execute("SELECT COUNT(*) FROM customer_orders WHERE user_id = %s", (user_id,))
                    orders_count = cursor_orders.fetchone()[0]

                # контекст для шаблона home.html
                home_data = {
                    "user_id": user_id,
                    "username": username,
                    "user_status": user_status,
                    "avatar": avatar,
                    "orders_count": orders_count,
                }
                
                # Сохраняем данные в кэш на 2 минуты (120 секунд)
                cache_ttl = 120  # Кэшируем на короткое время, т.к. это главная страница
                cache_set(cache_key, home_data, cache_ttl)
                print(f"Данные главной страницы сохранены в кэш с ключом {cache_key} ({time.time() - start_time:.6f} сек)")
                
                return render_template("index.html", **home_data)
        except Exception as e:
            print(f"Ошибка при обновлении времени последнего визита: {e}")

    return render_template("index.html", user_id=user_id, user_status=user_status, 
                           orders_count=orders_count, username=username, avatar=avatar)

@home_bp.route("/help")
def help_page():
    user_id = request.cookies.get("user_id")
    user_status = None
    username = None
    avatar = "user.png"  # Аватар по умолчанию
    
    if user_id:
        try:
            with DatabaseConnection() as db:
                cursor = db.cursor()
                
                # Получаем статус пользователя и имя
                cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
                result = cursor.fetchone()
                if result:
                    user_status = result[0]
                    username = result[1]
                    if result[2]:  # Если у пользователя есть аватар
                        avatar = result[2]
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
            with DatabaseConnection() as db:
                cursor = db.cursor()
                
                # Получаем статус пользователя и имя
                cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
                result = cursor.fetchone()
                if result:
                    user_status = result[0]
                    username = result[1]
                    if result[2]:  # Если у пользователя есть аватар
                        avatar = result[2]
        except Exception as e:
            print(f"Ошибка при получении данных пользователя: {e}")
    
    return render_template("empty_page.html", user_status=user_status, username=username, avatar=avatar)