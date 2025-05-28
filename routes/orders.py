from flask import Blueprint, render_template, request, redirect, url_for, jsonify
import logging
from datetime import datetime
import pytz
from pytz import timezone
from database.connection import DatabaseConnection
from database.redis_cache import cache_set, cache_get, invalidate_cache
from middleware.cache_control import invalidate_cache_on_action
import traceback
import time


my_orders_bp = Blueprint('my_orders', __name__)
coder_orders_bp = Blueprint('coder_orders', __name__)
update_order_bp = Blueprint('update_order', __name__)
accept_order_bp = Blueprint('accept_order', __name__)
orders_view_bp = Blueprint('orders_view', __name__)
order_bp = Blueprint('order', __name__)


@my_orders_bp.route("/my_orders")
def my_orders():
    start_time = time.time()
    user_id = request.cookies.get('user_id')
    user_timezone = request.cookies.get("user_timezone", "UTC")  # Часовой пояс пользователя, по умолчанию UTC

    if not user_id:
        return redirect(url_for('login.login'))  # Если пользователь не авторизован
        
    # Генерируем ключ кэша для заказов пользователя
    cache_key = f"my_orders:{user_id}:{user_timezone}"
    
    # Проверяем наличие данных в кэше
    cached_data = cache_get(cache_key)
    if cached_data:
        print(f"Данные о заказах пользователя {user_id} получены из кэша ({time.time() - start_time:.6f} сек)")
        return render_template("my_orders.html", **cached_data)

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
        
        # Получаем данные пользователя для navbar
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            cursor.close()
            return redirect(url_for('login.login'))
            
        user_status, username, avatar = user_data
        # Используем правильную систему аватаров в зависимости от статуса
        avatar_map = {"user": "user.png", "admin": "admin.png", "coder": "coder.png"}
        if not avatar or avatar == 'None':
            avatar = avatar_map.get(user_status, "user.png")
        
        # Получаем количество заказов для админов/разработчиков
        orders_count = 0
        if user_status in ['admin', 'coder']:
            cursor.execute("""
                SELECT COUNT(*) FROM customer_orders co
                JOIN order_status os ON co.id = os.order_id
                WHERE os.status != 'completed' AND os.status != 'cancelled'
            """)
            orders_count = cursor.fetchone()[0]

        # Получаем все заказы для текущего пользователя с их статусами из order_status
        cursor.execute("""
            SELECT co.id, co.service, co.tech_assignment, co.budget, os.status, os.created_at, os.opened_at,
                   ca.review, ca.rating, ca.review_time
            FROM customer_orders co
            LEFT JOIN order_status os ON co.id = os.order_id
            LEFT JOIN coder_assignments ca ON co.id = ca.order_id
            WHERE co.user_id = %s
        """, (user_id,))
        orders = cursor.fetchall()

        user_tz = pytz.timezone(user_timezone)

        formatted_orders = []
        for order in orders:
            created_at_utc = order[5]  # Дата и время создания заказа из order_status
            opened_at_utc = order[6]   # Дата и время начала работы
            review_time_utc = order[9]  # Дата и время отзыва
            
            if created_at_utc:
                if isinstance(created_at_utc, datetime):
                    if created_at_utc.tzinfo is None:
                        created_at_utc = pytz.utc.localize(created_at_utc)  # Приводим к UTC
                else:
                    created_at_utc = datetime.strptime(created_at_utc, "%Y-%m-%d %H:%M:%S")
                    created_at_utc = pytz.utc.localize(created_at_utc)

                # Преобразуем в локальное время пользователя
                local_time = created_at_utc.astimezone(user_tz)
                created_at_str = local_time.strftime("%d.%m.%Y %H:%M:%S")
            else:
                created_at_str = "Не указано"

            # Форматируем opened_at
            opened_at_str = None
            if opened_at_utc:
                if isinstance(opened_at_utc, datetime):
                    if opened_at_utc.tzinfo is None:
                        opened_at_utc = pytz.utc.localize(opened_at_utc)
                else:
                    opened_at_utc = datetime.strptime(opened_at_utc, "%Y-%m-%d %H:%M:%S")
                    opened_at_utc = pytz.utc.localize(opened_at_utc)
                local_opened_time = opened_at_utc.astimezone(user_tz)
                opened_at_str = local_opened_time.strftime("%d.%m.%Y %H:%M:%S")

            # Форматируем review_time
            review_time_str = None
            if review_time_utc:
                if isinstance(review_time_utc, datetime):
                    if review_time_utc.tzinfo is None:
                        review_time_utc = pytz.utc.localize(review_time_utc)
                else:
                    review_time_utc = datetime.strptime(review_time_utc, "%Y-%m-%d %H:%M:%S")
                    review_time_utc = pytz.utc.localize(review_time_utc)
                local_review_time = review_time_utc.astimezone(user_tz)
                review_time_str = local_review_time.strftime("%d.%m.%Y %H:%M:%S")

            formatted_orders.append({
                "id": order[0],
                "service": order[1],
                "tech_assignment": order[2],
                "budget": order[3],
                "status": order[4] if order[4] else "Не указан",
                "created_at": created_at_str,
                "opened_at": opened_at_str,
                "review": order[7],
                "rating": order[8],
                "review_time": review_time_str
            })

        # Подготавливаем данные для шаблона и кэширования
        template_data = {
            "orders": formatted_orders, 
            "user_status": user_status, 
            "username": username, 
            "avatar": avatar, 
            "orders_count": orders_count
        }
        
        # Сохраняем в кэш на 2 минуты
        cache_set(cache_key, template_data, 120)
        print(f"Данные о заказах пользователя {user_id} сохранены в кэш ({time.time() - start_time:.6f} сек)")
        
        return render_template("my_orders.html", **template_data)

    except Exception as e:
        logging.error(f"Ошибка при получении заказов: {e}")
        return jsonify({"error": "Ошибка при получении заказов"}), 500


import traceback

@coder_orders_bp.route("/coder_orders")
def coder_orders():
    start_time = time.time()
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
    
    # Проверяем параметр refresh для принудительного обновления данных
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    # Генерируем ключ кэша для заказов разработчика
    cache_key = f"coder_orders:{user_id}"
    
    # Проверяем наличие данных в кэше только если не запрошено обновление
    if not refresh:
        cached_data = cache_get(cache_key)
        if cached_data:
            print(f"Данные о заказах разработчика {user_id} получены из кэша ({time.time() - start_time:.6f} сек)")
            return render_template("coder_orders.html", **cached_data)

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()

            # Получаем данные текущего пользователя
            cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()

            if not user_data or user_data[0] not in ['coder', 'admin']:
                return redirect(url_for("login.login"))
                
            user_status = user_data[0]
            username = user_data[1]
            avatar = user_data[2] if user_data[2] else "default_avatar.png"

            print(f"ID пользователя: {user_id}, статус: {user_status}")
            
            # Сначала проверим, есть ли заказы с этим coder в таблице order_status
            check_query = "SELECT COUNT(*) FROM order_status WHERE coder = %s"
            cursor.execute(check_query, (user_id,))
            orders_count = cursor.fetchone()[0]
            print(f"Количество заказов с coder={user_id}: {orders_count}")
            
            # Если нет заказов, проверим все заказы в системе
            if orders_count == 0:
                cursor.execute("SELECT order_id, coder FROM order_status LIMIT 5")
                sample_orders = cursor.fetchall()
                print(f"Примеры заказов в базе: {sample_orders}")
                
                # Проверим тип данных в поле coder
                cursor.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'order_status' AND column_name = 'coder'")
                coder_type = cursor.fetchone()
                print(f"Тип данных поля coder: {coder_type}")
                
                # Проверим тип user_id
                print(f"Тип user_id: {type(user_id)}, значение: {user_id}")
                
                # Попробуем преобразовать тип user_id в int
                try:
                    int_user_id = int(user_id)
                    cursor.execute(check_query, (int_user_id,))
                    int_orders_count = cursor.fetchone()[0]
                    print(f"Количество заказов с coder={int_user_id} (int): {int_orders_count}")
                    
                    # Если нашли заказы после преобразования в int, используем этот тип
                    if int_orders_count > 0:
                        user_id = int_user_id
                except ValueError:
                    print("Не удалось преобразовать user_id в int")
            
            # Получаем заказы, где текущий пользователь назначен как coder
            query = """
                SELECT co.id, co.user_id, co.tech_assignment, ca.payment, co.service, 
                       ca.coder_response, ca.required_skills, ca.assigned_time, os.created_at, u.username, os.status
                FROM customer_orders co
                LEFT JOIN order_status os ON co.id = os.order_id
                LEFT JOIN coder_assignments ca ON co.id = ca.order_id
                LEFT JOIN users u ON co.user_id = u.id
                WHERE os.coder = %s
            """
            cursor.execute(query, (user_id,))
            orders = cursor.fetchall()
            print(f"Найдено заказов: {len(orders)}")

            # Подсчет количества выполненных, активных и проверяемых заказов
            completed_orders_count = 0
            in_progress_count = 0
            under_review_count = 0
            total_earnings = 0

            coder_orders = []
            for order in orders:
                order_dict = {
                    "id": order[0],
                    "user_id": order[1],
                    "tech_assignment": order[2],
                    "payment": order[3],
                    "service": order[4],
                    "coder_response": order[5],
                    "required_skills": order[6],
                    "assigned_time": order[7].strftime("%d.%m.%Y") if order[7] else None,
                    "created_at": order[8].strftime("%d.%m.%Y %H:%M:%S") if order[8] else None,
                    "username": order[9] if order[9] else "Неизвестный пользователь",
                    "status": order[10] if order[10] else "Не указан",
                }
                coder_orders.append(order_dict)

                # Подсчитываем выполненные и активные заказы
                if order_dict["status"] == "completed":
                    completed_orders_count += 1
                    if order_dict["payment"]:
                        total_earnings += order_dict["payment"]
                elif order_dict["status"] == "in_progress":
                    in_progress_count += 1

            # Подсчёт заказов "На проверке" по таблице revision_requests
            cursor.execute("""
                SELECT COUNT(*) FROM revision_requests 
                WHERE coder_id = %s AND status = 'pending'
            """, (user_id,))
            under_review_count = cursor.fetchone()[0]

        # Сортируем заказы по категориям
        in_progress_orders = []
        review_orders = []
        completed_orders = []
        
        for order in coder_orders:
            if order['status'] == 'in_progress':
                in_progress_orders.append(order)
            elif order['status'] == 'under_review' or order['coder_response'] == 'revision_requested':
                review_orders.append(order)
            elif order['status'] == 'completed':
                completed_orders.append(order)
        
        # Подготавливаем данные для шаблона и кэширования
        template_data = {
            "coder_orders": coder_orders,
            "in_progress_orders": in_progress_orders,
            "review_orders": review_orders,
            "completed_orders": completed_orders,
            "active_count": in_progress_count,
            "review_count": under_review_count,
            "completed_count": completed_orders_count,
            "total_earnings": total_earnings,
            "user_status": user_status,
            "username": username,
            "avatar": avatar,
            "orders_count": len(coder_orders)
        }
        
        # Сохраняем в кэш на 2 минуты
        cache_set(cache_key, template_data, 120)
        print(f"Данные о заказах разработчика {user_id} сохранены в кэш ({time.time() - start_time:.6f} сек)")
        
        return render_template("coder_orders.html", **template_data)

    except Exception as e:
        error_message = f"Ошибка при получении заказов для программистов: {e}"
        traceback_info = traceback.format_exc()  
        logging.error(f"{error_message}\n{traceback_info}")  
        return jsonify({"error": "Произошла ошибка при получении данных"}), 500


@coder_orders_bp.route("/coder_accept_order/<int:order_id>", methods=["GET", "POST"])
def coder_accept_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
        
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, что пользователь имеет роль coder или admin
            cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            user_status = cursor.fetchone()
            if not user_status or user_status[0] not in ['coder', 'admin']:
                return redirect(url_for('login.login'))

            # Проверяем, что заказ существует и находится в статусе pending
            cursor.execute("""
                SELECT os.status, ca.coder_response
                FROM order_status os
                LEFT JOIN coder_assignments ca ON os.order_id = ca.order_id
                WHERE os.order_id = %s AND os.coder = %s
            """, (order_id, user_id))
            order_data = cursor.fetchone()
            
            if not order_data:
                return jsonify({"error": "Заказ не найден или вы не являетесь его исполнителем"}), 404

            # Фиксируем текущее время принятия заказа
            response_time = datetime.now()

            # Обновляем статус заказа в зависимости от текущего контекста
            cursor.execute("""
                UPDATE order_status
                SET status = 'payment_pending'
                WHERE order_id = %s
            """, (order_id,))
            
            # Обновляем статус ответа разработчика
            cursor.execute("""
                UPDATE coder_assignments
                SET coder_response = 'accepted', coder_response_time = %s
                WHERE order_id = %s
            """, (response_time, order_id))
            
            db.commit()
            
            # Инвалидируем кэш для всех страниц, связанных с заказами
            invalidate_cache(f"coder_orders:{user_id}*")
            invalidate_cache(f"my_orders:*")
            invalidate_cache(f"order:{order_id}*")
            
            # Перенаправляем на страницу с принудительным обновлением
            return redirect(url_for('coder_orders.coder_orders', refresh='true'))
            
    except Exception as e:
        logging.error(f"Ошибка при принятии заказа: {e}")
        traceback_info = traceback.format_exc()
        logging.error(f"Трейсбек: {traceback_info}")
        return jsonify({"error": "Произошла ошибка при обработке заказа"}), 500


@coder_orders_bp.route("/coder_decline_order/<int:order_id>")
def coder_decline_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
        
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, что пользователь имеет роль coder или admin
            cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            user_status = cursor.fetchone()
            if not user_status or user_status[0] not in ['coder', 'admin']:
                return redirect(url_for('login.login'))
                
            # Проверяем, что заказ существует и находится в статусе pending
            cursor.execute("""
                SELECT os.status, ca.coder_response 
                FROM order_status os
                LEFT JOIN coder_assignments ca ON os.order_id = ca.order_id
                WHERE os.order_id = %s AND os.coder = %s
            """, (order_id, user_id))
            order_data = cursor.fetchone()
            
            if not order_data:
                return jsonify({"error": "Заказ не найден или вы не являетесь его исполнителем"}), 404
                
            # Обновляем статус заказа и удаляем связь с разработчиком
            cursor.execute("""
                UPDATE order_status
                SET status = 'created', coder = NULL
                WHERE order_id = %s
            """, (order_id,))
            
            # Обновляем статус ответа разработчика
            cursor.execute("""
                UPDATE coder_assignments
                SET coder_response = 'declined'
                WHERE order_id = %s
            """, (order_id,))
            
            db.commit()
            
            # Инвалидируем кэш для всех страниц, связанных с заказами
            invalidate_cache(f"my_orders:{user_id}*")
            invalidate_cache(f"coder_orders:{user_id}*")
            invalidate_cache(f"order:{order_id}*")
            
            # Перенаправляем на страницу с принудительным обновлением
            return redirect(url_for("coder_orders.coder_orders", refresh='true'))
            
    except Exception as e:
        logging.error(f"Ошибка при отклонении заказа: {e}")
        traceback_info = traceback.format_exc()
        logging.error(f"Трейсбек: {traceback_info}")
        return jsonify({"error": "Произошла ошибка при обработке заказа"}), 500


@coder_orders_bp.route("/request_revision/<int:order_id>", methods=["POST"])
def request_revision(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
        
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, что пользователь имеет роль coder или admin
            cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            user_status = cursor.fetchone()
            if not user_status or user_status[0] not in ['coder', 'admin']:
                return redirect(url_for('login.login'))
                
            # Получаем данные из формы
            new_price = request.form.get('new_price')
            new_deadline = request.form.get('new_deadline')
            reason = request.form.get('reason')
            
            # Валидация данных
            if not new_price or not new_deadline or not reason:
                return jsonify({"error": "Все поля обязательны"}), 400
                
            # Проверяем, что заказ существует и пользователь является его исполнителем
            cursor.execute("""
                SELECT ca.payment, ca.deadline 
                FROM order_status os
                LEFT JOIN coder_assignments ca ON os.order_id = ca.order_id
                WHERE os.order_id = %s AND os.coder = %s
            """, (order_id, user_id))
            old_data = cursor.fetchone()
            
            if not old_data:
                return jsonify({"error": "Заказ не найден"}), 404

            old_price, old_deadline = old_data

            # Обновляем coder_response в coder_assignments
            cursor.execute("""
                UPDATE coder_assignments
                SET coder_response = 'revision_requested'
                WHERE order_id = %s
            """, (order_id,))

            # Записываем запрос на правку в таблицу revision_requests
            cursor.execute("""
                INSERT INTO revision_requests (order_id, coder_id, old_price, new_price, old_deadline, new_deadline, reason, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            """, (order_id, user_id, old_price, new_price, old_deadline, new_deadline, reason))

            db.commit()
            
            # Инвалидируем кэш для всех страниц, связанных с заказами
            invalidate_cache(f"my_orders:{user_id}*")
            invalidate_cache(f"coder_orders:{user_id}*")
            invalidate_cache(f"order:{order_id}*")

            # Перенаправляем на страницу с принудительным обновлением
            return redirect(url_for("coder_orders.coder_orders", refresh='true'))

    except Exception as e:
        logging.error(f"Ошибка при запросе правки: {e}")
        traceback_info = traceback.format_exc()
        logging.error(f"Трейсбек: {traceback_info}")
        return jsonify({"error": "Произошла ошибка при обработке заказа"}), 500




# Эта функция была объединена с другой реализацией функции coder_accept_order выше



@accept_order_bp.route("/accept_order/<int:order_id>", methods=["GET", "POST"])
def accept_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()

        # Получаем список пользователей с ролью admin и coder
        cursor.execute("SELECT id, username, status FROM users WHERE status IN ('coder', 'admin') ORDER BY CASE WHEN status = 'admin' THEN 1 ELSE 2 END")
        users = cursor.fetchall()

        if request.method == "POST":
            coder_id = request.form.get("coder_id")
            payment = request.form.get("payment")
            required_skills = request.form.get("required_skills")
            assigned_time = request.form.get("assigned_time")

            # Обновляем статус заказа на 'accepted' и устанавливаем last_from на текущий user_id
            cursor.execute("""
                UPDATE order_status
                SET status = 'accepted', last_from = %s, coder = %s
                WHERE order_id = %s
            """, (user_id, coder_id, order_id))

            cursor.execute("""
                UPDATE coder_assignments
                SET payment = %s, required_skills = %s, assigned_time = %s
                WHERE order_id = %s
            """, (payment, required_skills, assigned_time, order_id))

            # Устанавливаем статус coder_response как 'pending'
            cursor.execute("""
                UPDATE coder_assignments
                SET coder_response = 'pending'
                WHERE order_id = %s
            """, (order_id,))

            db.commit()

            cursor.close()

            return redirect(url_for("orders_view.orders_view"))

        cursor.close()

        return render_template("accept_order.html", users=users, order_id=order_id)

    except Exception as e:
        logging.error(f"Ошибка при принятии заказа: {e}")
        return jsonify({"error": "Ошибка при принятии заказа"}), 500


    
@orders_view_bp.route("/orders_view", methods=["GET"])
def orders_view():
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect(url_for("login.login"))

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
        
        # получить данные пользователя для navbar
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            cursor.close()
            return redirect(url_for('login.login'))
        
        status, current_username, avatar = user_data
        
        # Подготовка аватара для отображения
        avatar_path = None
        if avatar:
            if avatar.startswith(('http://', 'https://')):
                # Если аватар - внешняя ссылка, используем как есть
                avatar_path = avatar
            else:
                # Если аватар - локальный файл
                if avatar.startswith('images/'):
                    avatar_path = avatar
                elif avatar.startswith('static/'):
                    avatar_path = avatar[7:]  # Удаляем 'static/'
                else:
                    avatar_path = f"images/{avatar}"
        
        # Проверяем статус пользователя
        cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user or user[0] != 'admin':
            return redirect(url_for("login.login"))

        user_timezone = request.cookies.get("user_timezone", "UTC")
        filter_status = request.args.get("status", "")

        # ДЕБАГ: Сначала проверим, есть ли заказы вообще
        cursor.execute("SELECT COUNT(*) FROM customer_orders")
        total_orders = cursor.fetchone()[0]
        print(f"ДЕБАГ: Всего заказов в customer_orders: {total_orders}")

        # УПРОЩЕННЫЙ запрос - сначала получаем только заказы
        query = """
            SELECT co.id, co.user_id, co.tech_assignment, co.budget, co.service, co.created_at
            FROM customer_orders co
        """

        params = []
        
        cursor.execute(query, params)
        orders = cursor.fetchall()
        print(f"ДЕБАГ: Найдено заказов: {len(orders)}")

        if not orders:
            print("ДЕБАГ: Заказы не найдены, возвращаем пустой список")
            return render_template("orders_view.html", orders=[], filter_status=filter_status, 
                                username=current_username, avatar=avatar, status=status)

        formatted_orders = []
        for order in orders:
            cursor.execute("SELECT username FROM users WHERE id = %s", (order[1],))
            user_result = cursor.fetchone()
            username = user_result[0] if user_result else "Неизвестный пользователь"

            # Получаем статус заказа отдельно
            cursor.execute("SELECT status, created_at FROM order_status WHERE order_id = %s", (order[0],))
            status_result = cursor.fetchone()
            order_status = status_result[0] if status_result else "created"
            order_created_at = status_result[1] if status_result else order[5]

            # Применяем фильтр если нужно
            if filter_status and filter_status != order_status:
                continue

            if isinstance(order_created_at, datetime):
                if order_created_at.tzinfo is None:
                    order_created_at = pytz.utc.localize(order_created_at)
            else:
                order_created_at = datetime.strptime(str(order_created_at), "%Y-%m-%d %H:%M:%S")
                order_created_at = pytz.utc.localize(order_created_at)

            user_tz = pytz.timezone(user_timezone)
            local_time = order_created_at.astimezone(user_tz)

            formatted_orders.append({
                "id": order[0],
                "user_id": order[1],
                "username": username,
                "tech_assignment": order[2],
                "budget": order[3],
                "service": order[4],
                "status": order_status,
                "created_at": local_time.strftime("%d.%m.%Y %H:%M:%S"),
            })

        print(f"ДЕБАГ: Отформатировано заказов: {len(formatted_orders)}")
        cursor.close()

        return render_template("orders_view.html", orders=formatted_orders, filter_status=filter_status, 
                            username=current_username, avatar=avatar, status=status)

    except Exception as e:
        print(f"ДЕБАГ: Ошибка в orders_view: {e}")
        traceback.print_exc()
        return jsonify({"error": "Ошибка при загрузке заказов"}), 500

@orders_view_bp.route("/accept_revision/<int:order_id>", methods=["POST"])
def accept_revision(order_id):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect(url_for("login.login"))

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()

        # Получаем последнюю правку для данного заказа
        cursor.execute("""
            SELECT new_price, new_deadline FROM revision_requests 
            WHERE order_id = %s AND status = 'pending' ORDER BY id DESC LIMIT 1
        """, (order_id,))
        revision = cursor.fetchone()

        if not revision:
            return jsonify({"error": "Правка не найдена или уже принята"}), 404

        new_price, new_deadline = revision

        # Обновляем статус правки на "approved"
        cursor.execute("""
            UPDATE revision_requests 
            SET status = 'approved' 
            WHERE order_id = %s AND status = 'pending'
        """, (order_id,))

        # Обновляем данные заказа в coder_assignments
        cursor.execute("""
            UPDATE coder_assignments 
            SET payment = %s, assigned_time = %s, coder_response = 'accepted' 
            WHERE order_id = %s
        """, (new_price, new_deadline, order_id))

        # Устанавливаем статус заказа в order_status как "payment_pending"
        cursor.execute("""
            UPDATE order_status 
            SET status = 'payment_pending' 
            WHERE order_id = %s
        """, (order_id,))

        db.commit()
        cursor.close()

        return redirect(url_for("orders_view.orders_view"))

    except Exception as e:
        logging.error(f"Ошибка при принятии правки: {e}")
        return jsonify({"error": "Ошибка при принятии правки"}), 500




# Эта функция была объединена с другой реализацией request_revision выше
    

@order_bp.route("/order", methods=["GET", "POST"])
def order():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))  # если пользователь не авторизован, перенаправляем на страницу входа

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()

        # получить данные пользователя для navbar
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            cursor.close()
            return redirect(url_for('login.login'))
            
        status, username, avatar = user_data

        # Получаем количество заказов для отображения в меню
        orders_count = 0
        if status in ['admin', 'coder']:
            cursor.execute("""
                SELECT COUNT(*) FROM customer_orders co
                JOIN order_status os ON co.id = os.order_id
                WHERE os.status != 'completed' AND os.status != 'cancelled'
            """)
            orders_count = cursor.fetchone()[0]

        if status != "user":
            cursor.close()
            return redirect('/')  # исправлено на прямой редирект

        if request.method == "POST":
            tech_assignment = request.form.get("tech_assignment")
            budget = request.form.get("budget")
            service = request.form.get("service")  # получаем выбранную услугу
            deadline = request.form.get("deadline")  # Получаем дату выполнения заказа
            user_timezone = request.form.get("timezone")  # Получаем часовой пояс из формы

            # Логируем данные
            logging.info(f"Получен часовой пояс пользователя: {user_timezone}")
            logging.info(f"Запланированный дедлайн заказа: {deadline}")

            # Конвертируем текущее время в нужный часовой пояс
            user_tz = pytz.timezone(user_timezone)
            user_time = datetime.now(user_tz)

            # Вставляем заказ в customer_orders
            cursor.execute(
                """
                INSERT INTO customer_orders (user_id, tech_assignment, budget, service) 
                VALUES (%s, %s, %s, %s) 
                RETURNING id
                """,
                (user_id, tech_assignment, budget, service)
            )
            order_id = cursor.fetchone()[0]  # Получаем ID созданного заказа

            # Записываем дедлайн в coder_assignments
            cursor.execute(
                """
                INSERT INTO coder_assignments (order_id, deadline) 
                VALUES (%s, %s)
                """,
                (order_id, deadline)
            )

            # Вставляем заказ в order_status со статусом "created"
            cursor.execute(
                """
                INSERT INTO order_status (order_id, status) 
                VALUES (%s, %s)
                """,
                (order_id, "created")
            )

            db.commit()
            cursor.close()
            return redirect(url_for("profile.profile"))  # Перенаправляем на страницу заказов

        cursor.close()
        return render_template("order.html", status=status, username=username, avatar=avatar, orders_count=orders_count)

    except Exception as e:
        logging.error(f"Ошибка при создании заказа: {str(e)}")
        return jsonify({"error": "ошибка при создании заказа"}), 500


@my_orders_bp.route("/pay_order/<int:order_id>", methods=["POST"])
def pay_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Get order details and user balance
            cursor.execute("""
                SELECT co.budget, os.status 
                FROM customer_orders co
                JOIN order_status os ON co.id = os.order_id
                WHERE co.id = %s AND co.user_id = %s
            """, (order_id, user_id))
            order_data = cursor.fetchone()
            
            if not order_data:
                return jsonify({"error": "Order not found"}), 404
                
            budget, status = order_data
            
            if status != 'payment_pending':
                return jsonify({"error": "Order is not pending payment"}), 400
            
            # Get user balance
            cursor.execute("""
                SELECT balance 
                FROM user_profiles 
                WHERE user_id = %s
            """, (user_id,))
            balance_data = cursor.fetchone()
            
            if not balance_data:
                return jsonify({"error": "User profile not found"}), 404
                
            balance = balance_data[0]
            
            if balance < budget:
                return jsonify({
                    "error": "Insufficient balance",
                    "required": budget,
                    "available": balance,
                    "redirect": url_for('finances.finances')
                }), 402
            
            # Start transaction
            cursor.execute("BEGIN")
            
            try:
                # Deduct balance
                cursor.execute("""
                    UPDATE user_profiles 
                    SET balance = balance - %s 
                    WHERE user_id = %s
                """, (budget, user_id))
                
                # Update order status
                cursor.execute("""
                    UPDATE order_status 
                    SET status = 'in_progress', 
                        opened_at = CURRENT_TIMESTAMP 
                    WHERE order_id = %s
                """, (order_id,))
                
                # Create transaction record
                description = f"Payment for order #{order_id}"
                cursor.execute("""
                    INSERT INTO financial_transactions 
                    (id, user_id, type, amount, status, description, related_entity_id)
                    VALUES 
                    (gen_random_uuid(), %s, 'order_payment', %s, 'completed', %s, %s)
                """, (user_id, budget, description, order_id))
                
                # Create notification
                cursor.execute("""
                    INSERT INTO user_notifications 
                    (user_id, title, message, severity)
                    VALUES 
                    (%s, 'Payment Successful', %s, 'info')
                """, (user_id, f'Your payment for order #{order_id} has been processed successfully.'))
                
                cursor.execute("COMMIT")
                
                # Invalidate Redis cache for this user's orders
                invalidate_cache(f"my_orders:{user_id}*")
                invalidate_cache(f"order:{order_id}*")
                
                return jsonify({
                    "success": True,
                    "message": "Payment processed successfully",
                    "new_balance": balance - budget
                })
                
            except Exception as e:
                cursor.execute("ROLLBACK")
                raise e
                
    except Exception as e:
        logging.error(f"Error processing payment: {str(e)}")
        return jsonify({"error": "Error processing payment"}), 500


@my_orders_bp.route("/complete_order/<int:order_id>", methods=["POST"])
@invalidate_cache_on_action(cache_patterns=["order:{order_id}*"])
def complete_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Get order details and check ownership
            cursor.execute("""
                SELECT co.budget, os.status, os.coder, ca.payment
                FROM customer_orders co
                JOIN order_status os ON co.id = os.order_id
                LEFT JOIN coder_assignments ca ON co.id = ca.order_id
                WHERE co.id = %s AND co.user_id = %s
            """, (order_id, user_id))
            order_data = cursor.fetchone()
            
            if not order_data:
                return jsonify({"error": "Order not found"}), 404
                
            budget, status, coder_id, payment = order_data
            
            if status != 'in_progress':
                return jsonify({"error": "Order is not in progress"}), 400
                
            if not coder_id:
                return jsonify({"error": "No coder assigned to this order"}), 400
            
            # Start transaction
            cursor.execute("BEGIN")
            
            try:
                # Update order status to completed
                cursor.execute("""
                    UPDATE order_status 
                    SET status = 'completed',
                        closed_at = CURRENT_TIMESTAMP
                    WHERE order_id = %s
                """, (order_id,))
                
                # Transfer payment to coder
                cursor.execute("""
                    UPDATE user_profiles 
                    SET balance = balance + %s 
                    WHERE user_id = %s
                """, (payment, coder_id))
                
                # Create transaction record for coder
                cursor.execute("""
                    INSERT INTO financial_transactions 
                    (id, user_id, type, amount, status, description, related_entity_id)
                    VALUES 
                    (gen_random_uuid(), %s, 'order_completion', %s, 'completed', 'Payment received for order #%s', %s)
                """, (coder_id, payment, order_id, order_id))
                
                # Create notification for coder
                cursor.execute("""
                    INSERT INTO user_notifications 
                    (user_id, title, message, severity)
                    VALUES 
                    (%s, 'Order Completed', 'Your work on order #%s has been completed and payment has been received.', 'success')
                """, (coder_id, order_id))
                
                cursor.execute("COMMIT")
                
                return redirect(url_for('my_orders.my_orders'))
                
            except Exception as e:
                cursor.execute("ROLLBACK")
                raise e
                
    except Exception as e:
        logging.error(f"Error completing order: {str(e)}")
        return jsonify({"error": "Error completing order"}), 500

@my_orders_bp.route("/submit_review/<int:order_id>", methods=["POST"])
@invalidate_cache_on_action(cache_patterns=["order:{order_id}*"])
def submit_review(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))

    try:
        data = request.get_json()
        rating = data.get('rating')
        review_text = data.get('review')

        if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({"error": "Неверная оценка"}), 400

        if not review_text or not isinstance(review_text, str) or len(review_text) > 100:
            return jsonify({"error": "Неверный текст отзыва"}), 400

        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, существует ли заказ и принадлежит ли он пользователю
            cursor.execute("""
                SELECT co.id, os.status, os.coder
                FROM customer_orders co
                JOIN order_status os ON co.id = os.order_id
                WHERE co.id = %s AND co.user_id = %s
            """, (order_id, user_id))
            
            order = cursor.fetchone()
            if not order:
                return jsonify({"error": "Заказ не найден"}), 404
                
            if order[1] != 'completed':
                return jsonify({"error": "Можно оставить отзыв только на завершенный заказ"}), 400

            coder_id = order[2]  # Получаем ID кодировщика из order_status
            if not coder_id:
                return jsonify({"error": "Кодировщик не назначен на этот заказ"}), 400

            # Проверяем, существует ли уже отзыв для этого заказа
            cursor.execute("""
                SELECT 1 FROM coder_assignments WHERE order_id = %s
            """, (order_id,))
            review_exists = cursor.fetchone() is not None

            if review_exists:
                # Обновляем существующий отзыв
                cursor.execute("""
                    UPDATE coder_assignments 
                    SET review = %s, rating = %s, review_time = NOW()
                    WHERE order_id = %s
                """, (review_text, rating, order_id))
            else:
                # Создаем новый отзыв
                cursor.execute("""
                    INSERT INTO coder_assignments (order_id, coder_id, review, rating, review_time)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (order_id, coder_id, review_text, rating))

            # Создаем уведомление для кодировщика
            cursor.execute("""
                INSERT INTO user_notifications (user_id, title, message, severity)
                VALUES (%s, 'Новый отзыв', 'Получен новый отзыв на заказ #%s', 'info')
            """, (coder_id, order_id))

            db.commit()

        return redirect(url_for('my_orders.my_orders'))

    except Exception as e:
        logging.error(f"Ошибка при сохранении отзыва: {e}")
        return jsonify({"error": "Ошибка при сохранении отзыва"}), 500
