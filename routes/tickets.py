from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask import session, current_app
from datetime import datetime, timezone
from database.connection import get_db_connection, release_db_connection
from security.access_control import require_role, UserRole
import logging

tickets_bp = Blueprint('tickets', __name__)

@tickets_bp.route("/tickets")
def tickets_list():
    """Отображение списка тикетов для пользователя или списка всех тикетов для сотрудника поддержки"""
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем информацию о пользователе
        cursor.execute("SELECT username, status, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return redirect(url_for('login.login'))
        
        username, status, avatar = user_data
        is_support = status in ['admin', 'support']
        
        if is_support:
            # Для сотрудников поддержки и администраторов: показать все тикеты
            cursor.execute("""
                SELECT t.id, t.subject, t.status, t.created_at, u.username, 
                       (SELECT COUNT(*) FROM support_messages WHERE ticket_id = t.id) as message_count,
                       (SELECT MAX(created_at) FROM support_messages WHERE ticket_id = t.id) as last_update
                FROM support_tickets t
                JOIN users u ON t.user_id = u.id
                ORDER BY 
                    CASE WHEN t.status = 'open' THEN 1
                         WHEN t.status = 'answered' THEN 2
                         ELSE 3 END,
                    last_update DESC NULLS LAST
            """)
        else:
            # Для обычных пользователей: показать только их тикеты
            cursor.execute("""
                SELECT t.id, t.subject, t.status, t.created_at, u.username, 
                       (SELECT COUNT(*) FROM support_messages WHERE ticket_id = t.id) as message_count,
                       (SELECT MAX(created_at) FROM support_messages WHERE ticket_id = t.id) as last_update
                FROM support_tickets t
                JOIN users u ON t.user_id = u.id
                WHERE t.user_id = %s
                ORDER BY 
                    CASE WHEN t.status = 'open' THEN 1
                         WHEN t.status = 'answered' THEN 2
                         ELSE 3 END,
                    last_update DESC NULLS LAST
            """, (user_id,))
        
        tickets = []
        for row in cursor.fetchall():
            created_at = row[3].strftime('%d.%m.%Y %H:%M')
            last_update = row[6].strftime('%d.%m.%Y %H:%M') if row[6] else created_at
            
            tickets.append({
                'id': row[0],
                'subject': row[1],
                'status': row[2],
                'created_at': created_at,
                'username': row[4],
                'message_count': row[5],
                'last_update': last_update
            })
        
        # Получаем общую статистику по тикетам для админов/поддержки
        ticket_stats = None
        if is_support:
            cursor.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'open') as open_count,
                    COUNT(*) FILTER (WHERE status = 'answered') as answered_count,
                    COUNT(*) FILTER (WHERE status = 'closed') as closed_count
                FROM support_tickets
            """)
            stats_row = cursor.fetchone()
            if stats_row:
                ticket_stats = {
                    'open': stats_row[0],
                    'answered': stats_row[1],
                    'closed': stats_row[2],
                    'total': stats_row[0] + stats_row[1] + stats_row[2]
                }
        
        return render_template(
            'tickets/list.html',
            username=username,
            status=status,
            avatar=avatar or 'user.png',
            tickets=tickets,
            is_support=is_support,
            ticket_stats=ticket_stats
        )
    
    except Exception as e:
        logging.error(f"Ошибка при загрузке списка тикетов: {e}")
        return redirect(url_for('home.home'))
    
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)


@tickets_bp.route("/tickets/new", methods=["GET", "POST"])
def new_ticket():
    """Создание нового тикета поддержки"""
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем информацию о пользователе
        cursor.execute("SELECT username, status, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return redirect(url_for('login.login'))
        
        username, status, avatar = user_data
        
        if request.method == "POST":
            subject = request.form.get('subject')
            category = request.form.get('category')
            message = request.form.get('message')
            order_id = request.form.get('order_id')
            
            # Проверка заполнения обязательных полей
            if not subject or not message or not category:
                flash("Пожалуйста, заполните все обязательные поля", "error")
                return redirect(url_for('tickets.new_ticket'))
                
            # Проверка длины полей (ограничение по длине полей в базе данных)
            if len(subject) > 70:
                flash("Тема тикета слишком длинная. Максимальная длина - 70 символов", "error")
                return redirect(url_for('tickets.new_ticket'))
                
            # Обрабатываем HTML и ограничиваем размер сообщения
            from bs4 import BeautifulSoup
            import re
            
            try:
                # Проверяем, если сообщение содержит HTML
                if re.search(r'<[^>]+>', message):
                    # Безопасно обрабатываем HTML
                    soup = BeautifulSoup(message, 'html.parser')
                    
                    # Разрешаем только безопасные теги
                    allowed_tags = ['b', 'i', 'u', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'h2', 'blockquote', 'pre', 'code', 'a']
                    allowed_attrs = {'a': ['href', 'target']}
                    
                    # Удаляем все небезопасные теги
                    for tag in soup.find_all(True):
                        if tag.name not in allowed_tags:
                            tag.unwrap()
                        else:
                            # Удаляем неразрешенные атрибуты
                            allowed = allowed_attrs.get(tag.name, [])
                            for attr in list(tag.attrs):
                                if attr not in allowed:
                                    del tag[attr]
                    
                    # Добавляем target="_blank" к ссылкам
                    for a_tag in soup.find_all('a'):
                        a_tag['target'] = '_blank'
                    
                    # Получаем чистый HTML
                    message = str(soup)
                    
                    # Проверяем длину текста без HTML-тегов
                    plain_text = soup.get_text()
                    if len(plain_text) > 1500:
                        flash("Ваше сообщение слишком длинное. Максимальная длина - 1500 символов", "warning")
                else:
                    # Обычный текст без HTML
                    if len(message) > 1500:
                        message = message[:1500] + "..."
                        flash("Ваше сообщение было усечено до 1500 символов", "warning")
            except Exception as e:
                logging.error(f"Ошибка при обработке HTML в сообщении: {e}")
                # В случае ошибки обрабатываем как обычный текст
                message = re.sub(r'<[^>]*>', '', message)  # Удаляем все HTML теги
                if len(message) > 1500:
                    message = message[:1500] + "..."
                    flash("Ваше сообщение было усечено до 1500 символов", "warning")
            
            # Формируем тему с категорией
            formatted_subject = f"[{category}] {subject}"
            
            # Проверяем длину форматированной темы (макс. 255 символов в базе данных)
            if len(formatted_subject) > 255:
                formatted_subject = formatted_subject[:255]
                flash("Тема тикета была усечена из-за превышения лимита длины", "warning")
            
            now = datetime.now(timezone.utc)
            
            # Создаем новый тикет
            cursor.execute("""
                INSERT INTO support_tickets (user_id, subject, status, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (user_id, formatted_subject, 'open', now))
            
            ticket_id = cursor.fetchone()[0]
            
            # Добавляем первое сообщение
            if order_id and order_id.isdigit():
                # Если указан ID заказа, добавляем информацию в сообщение
                message_with_order = f"ID заказа: {order_id}\n\n{message}"
                cursor.execute("""
                    INSERT INTO support_messages (ticket_id, user_id, message, created_at)
                    VALUES (%s, %s, %s, %s)
                """, (ticket_id, user_id, message_with_order, now))
            else:
                cursor.execute("""
                    INSERT INTO support_messages (ticket_id, user_id, message, created_at)
                    VALUES (%s, %s, %s, %s)
                """, (ticket_id, user_id, message, now))
            
            conn.commit()
            
            flash("Ваш запрос отправлен в поддержку", "success")
            return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
        
        # Проверяем существование таблицы orders
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'orders'
            );
        """)
        
        orders_table_exists = cursor.fetchone()[0]
        orders = []
        
        if orders_table_exists:
            # Запрос списка заказов пользователя для выбора, если таблица существует
            try:
                cursor.execute("""
                    SELECT o.id, o.title
                    FROM orders o
                    JOIN order_status os ON o.id = os.order_id
                    WHERE o.user_id = %s OR os.coder = %s
                    ORDER BY o.id DESC
                """, (user_id, user_id))
                
                orders = cursor.fetchall()
            except Exception as e:
                logging.error(f"Ошибка при получении заказов: {e}")
                orders = []
        
        return render_template(
            'tickets/new.html',
            username=username,
            status=status,
            avatar=avatar or 'user.png',
            orders=orders
        )
    
    except Exception as e:
        logging.error(f"Ошибка при создании тикета: {e}")
        return redirect(url_for('tickets.tickets_list'))
    
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)


@tickets_bp.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
def view_ticket(ticket_id):
    """Просмотр тикета и добавление сообщений"""
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('login.login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем информацию о пользователе
        cursor.execute("SELECT username, status, avatar FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return redirect(url_for('login.login'))
        
        username, status, avatar = user_data
        is_support = status in ['admin', 'support']
        
        # Проверяем, существует ли тикет и имеет ли пользователь доступ к нему
        cursor.execute("""
            SELECT t.id, t.subject, t.status, t.created_at, t.user_id, u.username
            FROM support_tickets t
            JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (ticket_id,))
        
        ticket_data = cursor.fetchone()
        
        if not ticket_data:
            flash("Тикет не найден", "error")
            return redirect(url_for('tickets.tickets_list'))
        
        # Проверяем права доступа: поддержка имеет доступ ко всем тикетам, обычные пользователи - только к своим
        if not is_support and str(ticket_data[4]) != user_id:
            flash("У вас нет доступа к этому тикету", "error")
            return redirect(url_for('tickets.tickets_list'))
        
        ticket = {
            'id': ticket_data[0],
            'subject': ticket_data[1],
            'status': ticket_data[2],
            'created_at': ticket_data[3].strftime('%d.%m.%Y %H:%M'),
            'user_id': ticket_data[4],
            'username': ticket_data[5]
        }
        
        # Получаем расширенную информацию о пользователе (только для персонала поддержки)
        user_details = None
        if is_support:
            try:
                # Получаем базовую информацию о пользователе
                cursor.execute("""
                    SELECT 
                        u.email, 
                        u.status, 
                        u.created_at,
                        up.ip_address,
                        up.last_visit,
                        COALESCE(up.balance, 0) as balance,
                        (SELECT EXISTS(SELECT 1 FROM telegram_profiles WHERE user_id = u.id)) as has_telegram
                    FROM users u
                    LEFT JOIN user_profiles up ON u.id = up.user_id
                    WHERE u.id = %s
                """, (ticket['user_id'],))
                
                user_info = cursor.fetchone()
                if user_info:
                    # Получаем часовой пояс пользователя для корректного отображения времени
                    timezone_offset = 5  # По умолчанию +5 (для Восточной временной зоны)
                    
                    # Форматирование даты с учетом часового пояса
                    def format_date_with_timezone(date):
                        if not date:
                            return 'Нет данных'
                        return date.strftime('%d.%m.%Y %H:%M')
                        
                    user_details = {
                        'email': user_info[0],
                        'status': user_info[1],
                        'registration_date': format_date_with_timezone(user_info[2]),
                        'ip': user_info[3] or 'Нет данных',
                        'last_login': format_date_with_timezone(user_info[4]),
                        'balance': user_info[5],
                        'has_telegram': user_info[6]
                    }
                    
                    # Если есть привязка к Telegram, получаем дополнительные данные
                    if user_details['has_telegram']:
                        cursor.execute("""
                            SELECT 
                                telegram_id, 
                                telegram_username, 
                                telegram_first_name, 
                                telegram_last_name,
                                notifications_enabled,
                                created_at,
                                updated_at
                            FROM telegram_profiles
                            WHERE user_id = %s
                        """, (ticket['user_id'],))
                        
                        telegram_data = cursor.fetchone()
                        if telegram_data:
                            user_details['telegram'] = {
                                'id': telegram_data[0],
                                'username': telegram_data[1],
                                'first_name': telegram_data[2],
                                'last_name': telegram_data[3],
                                'notifications_enabled': telegram_data[4],
                                'created_at': format_date_with_timezone(telegram_data[5]),
                                'updated_at': format_date_with_timezone(telegram_data[6])
                            }
            except Exception as e:
                logging.error(f"Ошибка при получении данных пользователя: {e}")
                user_details = None
        
        # Если пользователь подал POST-запрос (добавление сообщения или изменение статуса)
        if request.method == "POST":
            message = request.form.get('message')
            new_status = request.form.get('status')
            action = request.form.get('action')  # Новый параметр для действий без сообщения
            
            # Действие закрытия тикета (без сообщения)
            if action == 'close' and (is_support or str(ticket['user_id']) == user_id):
                try:
                    # Проверяем, что тикет еще не закрыт
                    if ticket['status'] == 'closed':
                        # Тикет уже закрыт, просто возвращаем успех
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({"success": True, "message": "Тикет уже закрыт", "status": "closed"})
                        else:
                            return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
                    
                    # Обновляем статус тикета на закрытый
                    cursor.execute("""
                        UPDATE support_tickets
                        SET status = 'closed'
                        WHERE id = %s
                    """, (ticket_id,))
                    
                    # Добавляем сообщение о закрытии тикета
                    now = datetime.now(timezone.utc)
                    system_message = "[SYSTEM] Тикет был закрыт"
                    cursor.execute("""
                        INSERT INTO support_messages (ticket_id, user_id, message, created_at)
                        VALUES (%s, %s, %s, %s)
                    """, (ticket_id, user_id, system_message, now))
                    
                    conn.commit()
                    
                    # Получаем информацию о только что добавленном сообщении
                    cursor.execute("""
                        SELECT id, created_at 
                        FROM support_messages 
                        WHERE ticket_id = %s AND user_id = %s AND message = %s 
                        ORDER BY id DESC LIMIT 1
                    """, (ticket_id, user_id, system_message))
                    
                    message_info = cursor.fetchone()
                    created_at = message_info[1].strftime('%d.%m.%Y %H:%M') if message_info else None
                    
                    # Если запрос от AJAX, возвращаем JSON ответ
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({
                            "success": True, 
                            "message": "Тикет успешно закрыт", 
                            "status": "closed",
                            "created_at": created_at
                        })
                    else:
                        # Закрываем соединения перед перенаправлением
                        cursor.close()
                        release_db_connection(conn)
                        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
                    
                except Exception as e:
                    conn.rollback()  # Откатываем изменения в случае ошибки
                    logging.error(f"Ошибка при закрытии тикета: {e}")
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({"success": False, "message": "Ошибка при закрытии тикета"}), 500
                    
                    return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
                
            # Если отправлено новое сообщение
            if message:
                now = datetime.now(timezone.utc)
                
                cursor.execute("""
                    INSERT INTO support_messages (ticket_id, user_id, message, created_at)
                    VALUES (%s, %s, %s, %s)
                """, (ticket_id, user_id, message, now))
                
                # Если сообщение от поддержки и тикет был открыт, меняем статус на 'answered'
                if is_support and ticket['status'] == 'open':
                    cursor.execute("""
                        UPDATE support_tickets
                        SET status = 'answered'
                        WHERE id = %s
                    """, (ticket_id,))
                
                # Если сообщение от пользователя и тикет был отвечен, меняем статус на 'open'
                if not is_support and ticket['status'] == 'answered':
                    cursor.execute("""
                        UPDATE support_tickets
                        SET status = 'open'
                        WHERE id = %s
                    """, (ticket_id,))
            
            # Если передан новый статус и пользователь является поддержкой
            elif new_status and is_support:
                cursor.execute("""
                    UPDATE support_tickets
                    SET status = %s
                    WHERE id = %s
                """, (new_status, ticket_id))
                # Если тикет закрывается, добавляем системное сообщение
                if new_status == 'closed':
                    system_message = "[SYSTEM] Тикет был закрыт сотрудником поддержки."
                    now = datetime.now(timezone.utc)
                    cursor.execute("""
                        INSERT INTO support_messages (ticket_id, user_id, message, created_at)
                        VALUES (%s, %s, %s, %s)
                    """, (ticket_id, user_id, system_message, now))
            
            conn.commit()
            return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
        
        # Получаем сообщения в тикете
        cursor.execute("""
            SELECT m.id, m.user_id, m.message, m.created_at, u.username, u.avatar, u.status
            FROM support_messages m
            JOIN users u ON m.user_id = u.id
            WHERE m.ticket_id = %s
            ORDER BY m.created_at ASC
        """, (ticket_id,))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row[0],
                'user_id': row[1],
                'message': row[2],
                'created_at': row[3].strftime('%d.%m.%Y %H:%M'),
                'username': row[4],
                'avatar': row[5] or 'user.png',
                'status': row[6],
                'is_support': row[6] in ['admin', 'support'],
                'is_mine': str(row[1]) == user_id
            })
        
        # Добавляем флаг для отображения форматированных сообщений
        return render_template(
            'tickets/view.html',
            ticket=ticket,
            messages=messages,
            user_id=user_id,
            username=username,
            status=status,
            is_support=is_support,
            is_owner=ticket['user_id'] == user_id,
            avatar=avatar or 'user.png',
            can_close=True,
            user_details=user_details,  # Исправлено: user_details вместо user_data
            allow_html=True  # Флаг для разрешения HTML в сообщениях
        )

    except Exception as e:
        logging.error(f"Ошибка при просмотре тикета: {e}")
        return redirect(url_for('tickets.tickets_list'))
    
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            release_db_connection(conn)
