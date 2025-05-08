from flask import Blueprint, render_template, request, redirect, url_for, jsonify
import logging
from datetime import datetime
import pytz
from pytz import timezone
from database.connection import get_db_connection
import traceback


my_orders_bp = Blueprint('my_orders', __name__)
coder_orders_bp = Blueprint('coder_orders', __name__)
update_order_bp = Blueprint('update_order', __name__)
accept_order_bp = Blueprint('accept_order', __name__)
orders_view_bp = Blueprint('orders_view', __name__)
order_bp = Blueprint('order', __name__)


@my_orders_bp.route("/my_orders")
def my_orders():
    user_id = request.cookies.get('user_id')
    user_timezone = request.cookies.get("user_timezone", "UTC")  # Часовой пояс пользователя, по умолчанию UTC

    if not user_id:
        return redirect(url_for('login.login'))  # Если пользователь не авторизован

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные пользователя для navbar
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            cursor.close()
            conn.close()
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
            SELECT co.id, co.service, co.tech_assignment, co.budget, os.status, os.created_at
            FROM customer_orders co
            LEFT JOIN order_status os ON co.id = os.order_id
            WHERE co.user_id = %s
        """, (user_id,))
        orders = cursor.fetchall()

        user_tz = pytz.timezone(user_timezone)

        formatted_orders = []
        for order in orders:
            created_at_utc = order[5]  # Дата и время создания заказа из order_status
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

            formatted_orders.append({
                "id": order[0],
                "service": order[1],
                "tech_assignment": order[2],
                "budget": order[3],
                "status": order[4] if order[4] else "Не указан",
                "created_at": created_at_str,
            })

        cursor.close()
        conn.close()

        return render_template("my_orders.html", orders=formatted_orders, user_status=user_status, username=username, avatar=avatar, orders_count=orders_count)

    except Exception as e:
        logging.error(f"Ошибка при получении заказов: {e}")
        return jsonify({"error": "Ошибка при получении заказов"}), 500


import traceback

@coder_orders_bp.route("/coder_orders")
def coder_orders():
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect(url_for("login.login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Получаем данные текущего пользователя
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()

        if not user_data or user_data[0] not in ['coder', 'admin']:
            return redirect(url_for("login.login"))
            
        user_status = user_data[0]
        username = user_data[1]
        avatar = user_data[2] if user_data[2] else "default_avatar.png"

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

        cursor.close()
        conn.close()

        return render_template(
            "coder_orders.html", 
            coder_orders=coder_orders,
            completed_orders_count=completed_orders_count,
            in_progress_count=in_progress_count,
            under_review_count=under_review_count,
            total_earnings=total_earnings,
            user_status=user_status,
            username=username,
            avatar=avatar
        )

    except Exception as e:
        error_message = f"Ошибка при получении заказов для программистов: {e}"
        traceback_info = traceback.format_exc()  
        logging.error(f"{error_message}\n{traceback_info}")  
        return jsonify({"error": "Произошла ошибка при получении данных"}), 500


@coder_orders_bp.route("/coder_decline_order/<int:order_id>", methods=["POST"])
def coder_decline_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверяем, является ли текущий пользователь исполнителем заказа
        cursor.execute("SELECT coder FROM order_status WHERE order_id = %s", (order_id,))
        assigned_coder = cursor.fetchone()

        if not assigned_coder or assigned_coder[0] != int(user_id):
            return jsonify({"error": "Вы не являетесь исполнителем этого заказа"}), 403

        # Обновляем статус заказа и убираем исполнителя
        cursor.execute("""
            UPDATE order_status
            SET status = 'created', coder = NULL
            WHERE order_id = %s
        """, (order_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("coder_orders.coder_orders"))

    except Exception as e:
        logging.error(f"Ошибка при отказе от заказа: {e}")
        return jsonify({"error": "Ошибка при отказе от заказа"}), 500


@update_order_bp.route("/update_order", methods=["POST"])
def update_order():
    order_id = request.form['order_id']
    coder_id = request.form['coder']
    payment = request.form['payment']
    required_skills = request.form['required_skills']
    assigned_time = request.form['assigned_time']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверяем, есть ли заказ в order_status
        cursor.execute("SELECT id FROM order_status WHERE id = %s", (order_id,))
        if not cursor.fetchone():
            logging.error(f"Заказ {order_id} не найден в order_status")
            return jsonify({"error": "Заказ не найден"}), 404

        # Обновляем статус заказа и назначенного кодера в order_status
        print(f"Обновляем order_status: {coder_id} -> {order_id}")
        cursor.execute("""
            UPDATE order_status
            SET status = 'under_review',
                coder = %s
            WHERE id = %s
        """, (coder_id, order_id))

        # Проверяем, есть ли запись в coder_assignments
        cursor.execute("SELECT order_id FROM coder_assignments WHERE order_id = %s", (order_id,))
        if not cursor.fetchone():
            logging.error(f"Запись для заказа {order_id} не найдена в coder_assignments")
            return jsonify({"error": "Запись в coder_assignments не найдена"}), 404

        # Обновляем данные в coder_assignments
        print(f"Обновляем coder_assignments: {payment}, {required_skills}, {assigned_time} -> {order_id}")
        cursor.execute("""
            UPDATE coder_assignments
            SET payment = %s, 
                required_skills = %s, 
                assigned_time = %s
            WHERE order_id = %s
        """, (payment, required_skills, assigned_time, order_id))

        conn.commit()  # Обязательно коммитим изменения
        print("Коммит выполнен")

        cursor.close()
        conn.close()

        return redirect(url_for("orders_view.orders_view"))

    except Exception as e:
        logging.error(f"Ошибка при обновлении заказа: {e}")
        return jsonify({"error": "Ошибка при обновлении заказа"}), 500


@coder_orders_bp.route("/coder_accept_order/<int:order_id>", methods=["POST"])
def coder_accept_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Фиксируем текущее время принятия заказа
        response_time = datetime.utcnow()

        # Обновляем coder_response и coder_response_time в coder_assignments
        cursor.execute("""
            UPDATE coder_assignments
            SET coder_response = 'accepted', coder_response_time = %s
            WHERE order_id = %s
        """, (response_time, order_id))

        # Обновляем статус в order_status
        cursor.execute("""
            UPDATE order_status
            SET status = 'payment_pending'
            WHERE order_id = %s
        """, (order_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("coder_orders.coder_orders"))  # Обновляем страницу заказов

    except Exception as e:
        logging.error(f"Ошибка при принятии заказа программистом: {e}")
        return jsonify({"error": "Ошибка при обновлении заказа"}), 500



@accept_order_bp.route("/accept_order/<int:order_id>", methods=["GET", "POST"])
def accept_order(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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

            conn.commit()

            cursor.close()
            conn.close()

            return redirect(url_for("orders_view.orders_view"))

        cursor.close()
        conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # получить данные пользователя для navbar
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            cursor.close()
            conn.close()
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

        # Получаем заказы
        query = """
            SELECT co.id, co.user_id, co.tech_assignment, co.budget, co.service, 
                   os.status, os.created_at, os.coder, os.last_from, ca.coder_response, ca.coder_response_time
            FROM customer_orders co
            LEFT JOIN order_status os ON co.id = os.order_id
            LEFT JOIN coder_assignments ca ON co.id = ca.order_id
        """

        params = []
        if filter_status:
            if filter_status == "my_orders":
                query += " WHERE os.last_from = %s"
                params.append(user_id)
            else:
                query += " WHERE os.status = %s"
                params.append(filter_status)

        cursor.execute(query, params)
        orders = cursor.fetchall()

        formatted_orders = []
        for order in orders:
            cursor.execute("SELECT username FROM users WHERE id = %s", (order[1],))
            user = cursor.fetchone()
            username = user[0] if user else "Неизвестный пользователь"

            cursor.execute("SELECT username FROM users WHERE id = %s", (order[7],))
            coder = cursor.fetchone()
            coder_name = coder[0] if coder else "Неизвестный кодер"

            # Получаем информацию о правке, если она есть
            cursor.execute("""
                SELECT old_price, new_price, old_deadline, new_deadline, reason, status 
                FROM revision_requests WHERE order_id = %s ORDER BY id DESC LIMIT 1
            """, (order[0],))
            revision = cursor.fetchone()

            revision_data = None
            if revision:
                revision_data = {
                    "old_price": revision[0],
                    "new_price": revision[1],
                    "old_deadline": revision[2],
                    "new_deadline": revision[3],
                    "reason": revision[4],
                    "status": revision[5]
                }

            created_at_utc = order[6]
            if isinstance(created_at_utc, datetime):
                if created_at_utc.tzinfo is None:
                    created_at_utc = pytz.utc.localize(created_at_utc)
            else:
                created_at_utc = datetime.strptime(created_at_utc, "%Y-%m-%d %H:%M:%S")
                created_at_utc = pytz.utc.localize(created_at_utc)

            user_tz = pytz.timezone(user_timezone)
            local_time = created_at_utc.astimezone(user_tz)

            formatted_orders.append({
                "id": order[0],
                "user_id": order[1],
                "username": username,
                "tech_assignment": order[2],
                "budget": order[3],
                "service": order[4],
                "status": order[5],
                "coder_name": coder_name,
                "created_at": local_time.strftime("%d.%m.%Y %H:%M:%S"),
                "coder_response": order[9],
                "coder_response_time": order[10],
                "revision": revision_data  # Добавляем данные о правке
            })

        cursor.close()
        conn.close()

        return render_template("orders_view.html", orders=formatted_orders, filter_status=filter_status, 
                            username=current_username, avatar=avatar, status=status)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Ошибка при загрузке заказов"}), 500

@orders_view_bp.route("/accept_revision/<int:order_id>", methods=["POST"])
def accept_revision(order_id):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect(url_for("login.login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("orders_view.orders_view"))

    except Exception as e:
        logging.error(f"Ошибка при принятии правки: {e}")
        return jsonify({"error": "Ошибка при принятии правки"}), 500




@coder_orders_bp.route("/request_revision/<int:order_id>", methods=["POST"])
def request_revision(order_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))

    new_price = request.form.get("new_price")
    new_deadline = request.form.get("new_deadline")
    reason = request.form.get("reason")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Получаем старые данные
        cursor.execute("SELECT payment, assigned_time FROM coder_assignments WHERE order_id = %s", (order_id,))
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

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("coder_orders.coder_orders"))

    except Exception as e:
        logging.error(f"Ошибка при запросе правки: {e}")
        return jsonify({"error": "Ошибка при запросе правки"}), 500
    

@order_bp.route("/order", methods=["GET", "POST"])
def order():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))  # если пользователь не авторизован, перенаправляем на страницу входа

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # получить данные пользователя для navbar
        cursor.execute("SELECT status, username, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            cursor.close()
            conn.close()
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
            conn.close()
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

            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for("profile.profile"))  # Перенаправляем на страницу заказов

        cursor.close()
        conn.close()
        return render_template("order.html", status=status, username=username, avatar=avatar, orders_count=orders_count)

    except Exception as e:
        logging.error(f"Ошибка при создании заказа: {str(e)}")
        return jsonify({"error": "ошибка при создании заказа"}), 500
