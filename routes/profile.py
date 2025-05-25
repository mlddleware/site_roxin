from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from database.connection import get_db_connection, release_db_connection, DatabaseConnection, cleanup_connections
from database.redis_cache import cached, cache_delete, cache_set, cache_get, invalidate_cache
import pytz
import time
import json
from security.access_control import require_role, UserRole

profile_bp = Blueprint('profile', __name__)

# Функция форматирования даты регистрации
def format_registration_date(created_at, user_tz):
    """Форматирует дату регистрации в удобочитаемый вид без относительного времени."""
    start_time = time.time()

    months_ru = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
        7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    created_at_local = created_at.astimezone(user_tz)
    formatted_date = created_at_local.strftime(f"%d {months_ru[created_at_local.month]} %Y, %H:%M")

    print(f"Время выполнения format_registration_date: {time.time() - start_time:.6f} сек")
    # Возвращаем только отформатированную дату без относительного времени
    return formatted_date

@profile_bp.route('/update_last_visit', methods=['POST'])
def update_last_visit():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    # Инвалидируем кэш профиля при обновлении времени последнего посещения
    invalidate_cache(f"profile:{user_id}")
    
    try:
        with DatabaseConnection() as db:
            current_time = datetime.now(timezone.utc)
            cursor = db.cursor()
            cursor.execute("""
                UPDATE user_profiles 
                SET last_visit = %s 
                WHERE user_id = %s
            """, (current_time, user_id))
            db.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Ошибка при обновлении last_visit: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@profile_bp.route('/profile/info', methods=['GET'])
@require_role(UserRole.USER)
def profile_info():
    """API для получения базовой информации о профиле"""
    user_id = request.cookies.get('user_id')
    
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
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

@profile_bp.route("/profile")
def profile():
    start_time = time.time()
    
    user_id = request.cookies.get('user_id')
    user_tz_name = request.cookies.get("user_timezone", "UTC")
    
    # Проверяем, запрошено ли обновление
    refresh_requested = request.args.get('refresh')
    
    # Генерируем ключ кэша для профиля этого пользователя
    cache_key = f"profile:{user_id}:{user_tz_name}"
    
    # Если запрошено обновление, инвалидируем кеш
    if refresh_requested:
        print(f"Запрошено обновление профиля, сбрасываем кеш: {cache_key}")
        invalidate_cache(cache_key)
    else:
        # Проверяем наличие данных в кэше
        cached_profile = cache_get(cache_key)
        if cached_profile:
            print("Данные профиля получены из кэша, но статус запрашивается из БД")
            # Получаем актуальный статус из БД
            try:
                with DatabaseConnection() as db:
                    cursor = db.cursor()
                    cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
                    current_status = cursor.fetchone()
                    if current_status:
                        new_status = current_status[0]
                        old_status = cached_profile.get('status')
                        
                        # Обновляем статус в кэшированном профиле
                        cached_profile['status'] = new_status
                        
                        # Обновляем аватар в соответствии с актуальным статусом
                        default_avatars = {
                            "user": "user.png",
                            "admin": "admin.png",
                            "coder": "coder.png",
                            "designer": "designer.png"
                        }
                        if not cached_profile['avatar'] or cached_profile['avatar'] in default_avatars.values():
                            cached_profile['avatar'] = default_avatars.get(new_status, "user.png")
                        
                        # Если статус изменился на coder, designer или support, нужно добавить employees_data
                        if new_status in ["coder", "designer", "support"] and (old_status != new_status or 'employees_data' not in cached_profile):
                            # Получаем данные сотрудника из БД
                            cursor.execute("""
                                SELECT direction, coin, completed_orders, reviews_count, rating, avg_completion_time, warn
                                FROM employees WHERE user_id = %s
                            """, (user_id,))
                            emp_data = cursor.fetchone()
                            
                            # Если данные не найдены, создаем пустую структуру
                            if emp_data:
                                direction, coin, completed_orders, reviews_count, rating, avg_completion_time, warn = emp_data
                            else:
                                direction, coin, completed_orders, reviews_count, rating, avg_completion_time, warn = "Не указано", 0, 0, 0, 0, 0, 0
                                
                            # Сохраняем данные в кэш
                            cached_profile['employees_data'] = {
                                "direction": direction,
                                "coin": coin,
                                "completed_orders": completed_orders,
                                "reviews_count": reviews_count,
                                "rating": rating,
                                "avg_completion_time": avg_completion_time,
                                "warn": warn
                            }
                            
                            # Также надо убедиться, что в кэше есть reviews для разработчика
                            if 'reviews' not in cached_profile:
                                cached_profile['reviews'] = []
            except Exception as e:
                print(f"Ошибка при получении актуального статуса: {e}")
            return render_template("profile.html", **cached_profile)

    print(f"Получение user_id из куков заняло: {time.time() - start_time:.6f} сек")

    try:
        with DatabaseConnection() as db:
            print(f"Создание подключения к БД заняло: {time.time() - start_time:.6f} сек")

            current_time = datetime.now(timezone.utc)

            # Сначала обновляем last_visit в отдельном запросе для гарантии обновления
            cursor1 = db.cursor()
            cursor1.execute("""
                UPDATE user_profiles
                SET last_visit = %s
                WHERE user_id = %s
                RETURNING last_visit
            """, (current_time, user_id))
            db.commit()  # Сразу сохраняем изменения
            
            # Затем выполняем основной запрос для получения данных пользователя
            cursor = db.cursor()
            cursor.execute("""
                SELECT 
                    u.username, 
                    u.status, 
                    u.avatar, 
                    COALESCE(up.balance, 0) as balance,
                    u.created_at,
                    up.last_visit,
                    e.direction,
                    e.coin,
                    e.completed_orders,
                    e.reviews_count,
                    e.rating,
                    e.avg_completion_time,
                    e.warn
                FROM 
                    users u
                LEFT JOIN user_profiles up ON u.id = up.user_id
                LEFT JOIN employees e ON u.id = e.user_id
                WHERE u.id = %s
            """, (user_id,))

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
                # Поскольку мы только что обновили last_visit, пользователь гарантированно онлайн
                online_status = "Онлайн" # Всегда показываем "Онлайн" при посещении своей страницы
                is_offline = False  # Пользователь всегда онлайн на своей странице
            else:
                last_visit_str = "Нет данных"
                online_status = "Нет данных"
                is_offline = True
            print(f"Обработка last_visit заняла: {time.time() - last_visit_start:.6f} сек")

            orders_count = 0
            user_orders_count = 0
            employees_data = None

            if status == "admin":
                admin_cursor = db.cursor()
                admin_cursor.execute("SELECT COUNT(*) FROM order_status")
                orders_count = admin_cursor.fetchone()[0]

            if status == "user":
                user_cursor = db.cursor()
                user_cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE user_id = %s", (user_id,))
                user_orders_count = user_cursor.fetchone()[0]

            reviews = []
            if status in ["coder", "designer", "support"]:
                employees_data = {
                    "direction": direction or "Не указано",
                    "coin": coin or 0,
                    "completed_orders": completed_orders or 0,
                    "reviews_count": reviews_count or 0,
                    "rating": rating or 0,
                    "avg_completion_time": avg_completion_time or "Не указано",
                    "warn": warn or 0
                }
                
                # Получаем отзывы для кодера
                reviews_cursor = db.cursor()
                reviews_cursor.execute("""
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
                
                reviews_data = reviews_cursor.fetchall()
                for review_row in reviews_data:
                    review_text, review_date, review_rating, reviewer_id, reviewer_name, reviewer_avatar = review_row
                    
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
                        "text": review_text,
                        "date": review_date_formatted,
                        "rating": review_rating or 0,
                        "reviewer_id": reviewer_id,
                        "reviewer_name": reviewer_name,
                        "reviewer_avatar": reviewer_avatar
                    })
            
            # Форматируем вывод
            profile_data = {
                "username": username,
                "status": status,
                "avatar": avatar,
                "balance": balance,
                "registration_date_info": registration_date_info,
                "last_visit": last_visit_str,
                "online_status": online_status,
                "is_offline": is_offline,
                "orders_count": orders_count,
                "user_orders_count": user_orders_count,
                "employees_data": employees_data,
                "reviews": reviews,
            }
            
            # Очищаем соединения периодически
            if int(time.time()) % 10 == 0:
                cleanup_connections()
                
            total_time = time.time() - start_time
            print(f"Общее время выполнения: {total_time:.6f} сек")
            
            # Сохраняем данные в кэш на 5 минут (300 секунд)
            cache_set(cache_key, profile_data, 300)
            print(f"Данные профиля сохранены в кэш с ключом {cache_key}")

            return render_template("profile.html", **profile_data)

    except Exception as e:
        print(f"Ошибка при загрузке профиля: {e}")
        return jsonify({"error": "Ошибка при загрузке профиля"}), 500

    finally:
        print("Соединение с БД закрыто")
