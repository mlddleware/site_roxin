from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from database.connection import get_db_connection, release_db_connection
from socketio_config import socketio
from flask_socketio import emit
from datetime import datetime, timedelta, timezone
import pytz
import json
from security.access_control import require_role, UserRole

chat_bp = Blueprint('chat', __name__)

# Глобальный словарь аватаров по статусу
avatar_map = {
    "user": "user.png",
    "admin": "admin.png", 
    "coder": "coder.png",
    "designer": "designer.png",
    "intern": "user.png"
}

@socketio.on("send_message")
def handle_send_message(data):
    sender_id = request.cookies.get("user_id")
    if not sender_id:
        return

    sender_id = int(sender_id)
    recipient_id = data.get("user_id")
    message = data.get("message")
    reply_to = data.get("reply_to")
    message_id = data.get("message_id")

    if not recipient_id or not message:
        return

    # Получаем имя отправителя
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT username FROM users WHERE id = %s", (sender_id,))
        result = cursor.fetchone()
        sender_username = result[0] if result else "Неизвестный"

        # Преобразуем данные ответа в JSON, если они есть
        if reply_to:
            # Проверяем, что reply_to уже не строка
            if not isinstance(reply_to, str):
                try:
                    reply_to_json = json.dumps(reply_to)
                except Exception:
                    reply_to_json = None
            else:
                # Если reply_to уже строка, проверяем, что это валидный JSON
                try:
                    # Проверка валидности JSON
                    json.loads(reply_to)
                    reply_to_json = reply_to
                except Exception:
                    reply_to_json = None
        else:
            reply_to_json = None

        # Вставляем сообщение с информацией об ответе и ID
        cursor.execute("""
            INSERT INTO messages (sender_id, message, created_at, user_id1, user_id2, reply_to, message_id)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s)
        """, (sender_id, message, sender_id, recipient_id, reply_to_json, message_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        cursor.close()
        release_db_connection(conn)

    # Добавляем вызов функции уведомлений
    from notifications.message_notifier import notify_new_message
    notify_new_message(sender_id, recipient_id, message)

    emit("new_message", {
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "sender": sender_username,
        "message": message,
        "reply_to": reply_to,
        "message_id": message_id
    }, broadcast=True)

@chat_bp.route("/chat/get_user_by_chat_id/<int:chat_id>", methods=["GET"])
@require_role(UserRole.USER)
def get_user_by_chat_id(chat_id):
    current_user_id = request.cookies.get("user_id")
    if not current_user_id:
        return jsonify({"error": "Необходима авторизация"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT CASE 
                WHEN user_id1 = %s THEN user_id2
                ELSE user_id1
            END AS other_user_id
            FROM chats WHERE id = %s
        """, (current_user_id, chat_id))

        chat = cursor.fetchone()

        if chat:
            other_user_id = chat[0]
            cursor.execute("SELECT username, avatar, status FROM users WHERE id = %s", (other_user_id,))
            user = cursor.fetchone()
            
            avatar = user[1] if user[1] else avatar_map.get(user[2], "user.png")
            return jsonify({
                "user_id": other_user_id, 
                "username": user[0], 
                "avatar": f"/static/images/{avatar}"
            })
    finally:
        cursor.close()
        release_db_connection(conn)
    
    return jsonify({"error": "Чат не найден"}), 404

@chat_bp.route("/chat/info/<int:chat_id>", methods=["GET"])
@require_role(UserRole.USER)
def get_chat_info(chat_id):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return jsonify({"error": "Необходима авторизация"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем, есть ли чат и кто собеседник
        cursor.execute("""
            SELECT user_id1, user_id2 FROM chats WHERE id = %s
        """, (chat_id,))
        chat = cursor.fetchone()

        if not chat:
            return jsonify({"error": "Чат не найден"}), 404

        user1, user2 = chat
        if str(user1) == user_id:
            other_user_id = user2
        elif str(user2) == user_id:
            other_user_id = user1
        else:
            return jsonify({"error": "Нет доступа"}), 403

        # Получаем данные собеседника, включая last_visit
        cursor.execute("""
            SELECT u.username, u.created_at, u.avatar, up.last_visit
            FROM users u
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE u.id = %s
        """, (other_user_id,))
        
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404

        username, created_at, avatar, last_visit = user
        
        # Форматируем last_visit
        current_time = datetime.now(timezone.utc)
        user_timezone = request.cookies.get("user_timezone", "UTC")
        user_tz = pytz.timezone(user_timezone)
        
        if last_visit:
            last_visit = last_visit.replace(tzinfo=timezone.utc) if last_visit.tzinfo is None else last_visit
            last_visit_str = last_visit.astimezone(user_tz).strftime('%d.%m.%Y %H:%M')
            online_status = "Онлайн" if (current_time - last_visit) <= timedelta(minutes=1) else f"Был {last_visit_str}"
        else:
            online_status = "Последнее посещение неизвестно"

        return jsonify({
            "user_id": other_user_id,
            "username": username,
            "created_at": created_at,
            "avatar": avatar if avatar and avatar.startswith("/static/images/") else f"/static/images/{avatar or 'user.png'}",
            "online_status": online_status
        })
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route('/chat/<int:chat_id>')
@require_role(UserRole.USER)
def chat_with_user(chat_id):
    user_id = request.cookies.get('user_id')

    if not user_id:
        return redirect(url_for('login.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем, существует ли чат с таким chat_id и текущим пользователем
        cursor.execute("""
            SELECT user_id1, user_id2 FROM chats WHERE id = %s
        """, (chat_id,))
        
        chat = cursor.fetchone()
        
        if not chat:
            return redirect(url_for('chat.chat'))  # Если чата нет, редирект на общий чат

        user1, user2 = chat

        if str(user1) != user_id and str(user2) != user_id:
            return redirect(url_for('chat.chat'))  # Если пользователь не в чате, редирект
    finally:
        cursor.close()
        release_db_connection(conn)
    
    return render_template('chat.html', chat_id=chat_id)

@chat_bp.route("/chat/get_chat_id/<int:user_id>", methods=["GET"])
def get_chat_id(user_id):
    current_user_id = request.cookies.get("user_id")
    if not current_user_id:
        return jsonify({"error": "Необходима авторизация"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id FROM chats 
            WHERE (user_id1 = %s AND user_id2 = %s) 
               OR (user_id1 = %s AND user_id2 = %s)
        """, (current_user_id, user_id, user_id, current_user_id))

        chat = cursor.fetchone()
        
        return jsonify({"chat_id": chat[0] if chat else None})
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route('/chat')
def chat():
    user_id = request.cookies.get('user_id')
    user_timezone = request.cookies.get("user_timezone", "UTC")

    if not user_id:
        return redirect(url_for('login.login'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Получаем список чатов
        cursor.execute("""
            SELECT c.id, 
                   CASE WHEN c.user_id1 = %s THEN u2.username ELSE u1.username END AS username,
                   (SELECT message 
                    FROM messages m 
                    WHERE (m.user_id1 = c.user_id1 AND m.user_id2 = c.user_id2)
                       OR (m.user_id1 = c.user_id2 AND m.user_id2 = c.user_id1)
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message,
                   (SELECT created_at 
                    FROM messages m 
                    WHERE (m.user_id1 = c.user_id1 AND m.user_id2 = c.user_id2)
                       OR (m.user_id1 = c.user_id2 AND m.user_id2 = c.user_id1)
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message_time
            FROM chats c
            JOIN users u1 ON c.user_id1 = u1.id
            JOIN users u2 ON c.user_id2 = u2.id
            WHERE c.user_id1 = %s OR c.user_id2 = %s
            ORDER BY last_message_time DESC
        """, (user_id, user_id, user_id))
        
        chats = cursor.fetchall()

        # Получаем информацию о пользователе (аватар)
        cursor.execute("SELECT avatar FROM users WHERE id = %s", (user_id,))
        user_avatar = cursor.fetchone()
        avatar = user_avatar[0] if user_avatar and user_avatar[0] else "user.png"

        # Устанавливаем часовой пояс
        user_tz = pytz.timezone(user_timezone)

        formatted_chats = []
        for chat in chats:
            chat_id, username, last_message, last_message_time = chat
            if last_message_time:
                last_message_time_utc = pytz.utc.localize(last_message_time) if last_message_time.tzinfo is None else last_message_time
                local_time = last_message_time_utc.astimezone(user_tz)
                formatted_time = local_time.strftime("%d.%m.%Y %H:%M:%S")
            else:
                formatted_time = "N/A"

            formatted_chats.append({
                'chat_id': chat_id,
                'username': username,
                'last_message': last_message,
                'last_message_time': formatted_time
            })

        return render_template('chat.html', chats=formatted_chats, avatar=avatar)

    except Exception:
        return jsonify({"error": "Ошибка при загрузке чатов"}), 500
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route("/chat/list", methods=["GET"])
def chat_list():
    user_id = request.cookies.get("user_id")
    user_timezone = request.cookies.get("user_timezone", "UTC")

    if not user_id:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT CASE WHEN c.user_id1 = %s THEN u2.id ELSE u1.id END AS other_user_id,
                   CASE WHEN c.user_id1 = %s THEN u2.username ELSE u1.username END AS username,
                   CASE WHEN c.user_id1 = %s THEN u2.avatar ELSE u1.avatar END AS avatar,
                   CASE WHEN c.user_id1 = %s THEN u2.status ELSE u1.status END AS user_status,
                   (SELECT message FROM messages m 
                    WHERE (m.user_id1 = c.user_id1 AND m.user_id2 = c.user_id2)
                       OR (m.user_id1 = c.user_id2 AND m.user_id2 = c.user_id1)
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message,
                   (SELECT created_at FROM messages m 
                    WHERE (m.user_id1 = c.user_id1 AND m.user_id2 = c.user_id2)
                       OR (m.user_id1 = c.user_id2 AND m.user_id2 = c.user_id1)
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message_date
            FROM chats c
            JOIN users u1 ON c.user_id1 = u1.id
            JOIN users u2 ON c.user_id2 = u2.id
            WHERE c.user_id1 = %s OR c.user_id2 = %s
            ORDER BY last_message_date DESC
        """, (user_id, user_id, user_id, user_id, user_id, user_id))

        chats = cursor.fetchall()

        user_tz = pytz.timezone(user_timezone)

        chat_list = []
        for row in chats:
            other_user_id, username, avatar, user_status, last_message, last_message_date = row
            
            # Логика выбора аватара
            if not avatar or avatar == 'None':
                avatar = avatar_map.get(user_status, "user.png")

            truncated_message = (last_message[:30] + '...') if last_message and len(last_message) > 30 else last_message
            if last_message_date:
                last_message_date_utc = pytz.utc.localize(last_message_date) if last_message_date.tzinfo is None else last_message_date
                local_time = last_message_date_utc.astimezone(user_tz)
                formatted_time = local_time.strftime('%H:%M:%S')
            else:
                formatted_time = 'N/A'

            chat_list.append({
                "user_id": other_user_id,
                "username": username,
                "avatar": f"/static/images/{avatar}",
                "last_message": truncated_message,
                "last_message_date": formatted_time
            })  

        return jsonify(chat_list)
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route("/chat/messages/<int:user_id>", methods=["GET"])
def chat_messages(user_id):
    current_user_id = int(request.cookies.get("user_id"))
    user_timezone = request.cookies.get("user_timezone", "UTC")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Получаем имена пользователей
        cursor.execute("SELECT username FROM users WHERE id = %s", (current_user_id,))
        current_user_name = cursor.fetchone()[0]

        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        other_user_name = cursor.fetchone()[0]

        # Загружаем сообщения с информацией об ответах и ID сообщений
        cursor.execute("""
            SELECT sender_id, message, created_at, reply_to, message_id
            FROM messages
            WHERE (user_id1 = %s AND user_id2 = %s) OR (user_id1 = %s AND user_id2 = %s)
            ORDER BY created_at ASC
        """, (current_user_id, user_id, user_id, current_user_id))
        
        messages = cursor.fetchall()

        user_tz = pytz.timezone(user_timezone)

        # Формируем список сообщений с правильными именами и временем
        messages_list = []
        for row in messages:
            sender_id, message, created_at, reply_to, message_id = row
            created_at_utc = pytz.utc.localize(created_at) if created_at.tzinfo is None else created_at
            local_time = created_at_utc.astimezone(user_tz)
            formatted_time = local_time.strftime('%Y-%m-%d %H:%M:%S')

            # Преобразуем JSON данные ответа если они есть
            reply_to_data = None
            if reply_to:
                try:
                    reply_to_data = json.loads(reply_to)
                except Exception:
                    # Если не удалось разобрать JSON, оставляем как есть
                    reply_to_data = reply_to

            messages_list.append({
                "sender": current_user_name if sender_id == current_user_id else other_user_name, 
                "message": message, 
                "timestamp": formatted_time,
                "reply_to": reply_to_data,
                "message_id": message_id,
                "created_at_raw": created_at.timestamp()  # Временная метка для сортировки
            })

        # Дополнительно сортируем сообщения по времени создания
        messages_list.sort(key=lambda x: x["created_at_raw"])
        
        # Удаляем временное поле перед отправкой
        for msg in messages_list:
            if "created_at_raw" in msg:
                del msg["created_at_raw"]

        return jsonify(messages_list)
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route("/chat/user/<int:user_id>", methods=["GET"])
def chat_user_info(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT u.username, u.created_at, u.avatar, u.status, up.last_visit
            FROM users u
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404

        username, created_at, avatar, status, last_visit = user
        
        # Выбор аватара по статусу, если нет своего
        if not avatar or avatar == 'None':
            avatar = avatar_map.get(status, "user.png")
        
        current_time = datetime.now(timezone.utc)
        user_timezone = request.cookies.get("user_timezone", "UTC")
        user_tz = pytz.timezone(user_timezone)
        
        if last_visit:
            last_visit = last_visit.replace(tzinfo=timezone.utc) if last_visit.tzinfo is None else last_visit
            last_visit_str = last_visit.astimezone(user_tz).strftime('%d.%m.%Y %H:%M')
            online_status = "Онлайн" if (current_time - last_visit) <= timedelta(minutes=1) else f"Был {last_visit_str}"
        else:
            online_status = "Последнее посещение неизвестно"

        return jsonify({
            "username": username,
            "created_at": created_at,
            "avatar": f"/static/images/{avatar}",
            "online_status": online_status
        })
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route("/chat/send", methods=["POST"])
def send_message():
    data = request.json
    message = data["message"]
    recipient_id = data["user_id"]
    sender_id = int(request.cookies.get("user_id"))
    reply_to = data.get("reply_to")
    message_id = data.get("message_id")

    # Валидация
    if not message:
        return jsonify({"error": "Пустое сообщение"}), 400
    
    if len(message) > 2000:  # Ограничение длины сообщения
        return jsonify({"error": "Сообщение слишком длинное"}), 400
        
    if not recipient_id or not isinstance(recipient_id, int):
        return jsonify({"error": "Некорректный получатель"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Преобразуем данные ответа в JSON, если они есть
        reply_to_json = json.dumps(reply_to) if reply_to else None

        # Вставляем сообщение с информацией об ответе и ID
        cursor.execute("""
            INSERT INTO messages (sender_id, message, created_at, user_id1, user_id2, reply_to, message_id)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s)
        """, (sender_id, message, sender_id, recipient_id, reply_to_json, message_id))

        conn.commit()
        return jsonify({"status": "Message sent"})
    except Exception:
        conn.rollback()
        return jsonify({"error": "Ошибка отправки сообщения"}), 500
    finally:
        cursor.close()
        release_db_connection(conn)

@chat_bp.route('/chat/start/<int:user_id>', methods=['POST'])
def start_chat(user_id):
    current_user_id = request.cookies.get("user_id")
    if not current_user_id:
        return jsonify({"error": "Необходима авторизация"}), 403

    try:
        current_user_id = int(current_user_id)
    except ValueError:
        return jsonify({"error": "Некорректный user_id"}), 400

    if current_user_id == user_id:
        return jsonify({"error": "Нельзя создать чат с самим собой"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id FROM chats 
            WHERE (user_id1 = %s AND user_id2 = %s) 
               OR (user_id1 = %s AND user_id2 = %s)
        """, (current_user_id, user_id, user_id, current_user_id))

        chat = cursor.fetchone()

        if not chat:
            cursor.execute("""
                INSERT INTO chats (user_id1, user_id2, created_at) 
                VALUES (%s, %s, NOW()) RETURNING id
            """, (current_user_id, user_id))
            chat_id = cursor.fetchone()[0]
            conn.commit()
        else:
            chat_id = chat[0]

        return jsonify({"chat_url": f"/chat/{chat_id}"})
    except Exception:
        conn.rollback()
        return jsonify({"error": "Ошибка создания чата"}), 500
    finally:
        cursor.close()
        release_db_connection(conn)