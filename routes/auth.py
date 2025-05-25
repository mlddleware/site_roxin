from flask import Blueprint, render_template, request, make_response, redirect, url_for, jsonify, session
from database.connection import get_db_connection, release_db_connection
from utils.logging import logger
from utils.admin_logger import AdminLogger
from security.password_utils import hash_password, check_password
from security.brute_force import BruteForceProtection
import secrets
import re
import logging
import traceback
import uuid
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Настройка логгера
logger = logging.getLogger(__name__)

register_bp = Blueprint('register', __name__)
login_bp = Blueprint('login', __name__)
logout_bp = Blueprint('logout', __name__)
forgot_password_bp = Blueprint('auth', __name__)

# Функция для проверки сложности пароля
def is_password_strong(password):
    # Минимум 8 символов, содержит цифры и буквы
    if len(password) < 8:
        return False
    if not re.search(r'\d', password):
        return False
    if not re.search(r'[a-zA-Z]', password):
        return False
    return True

# Функция для проверки сложности пароля
def is_strong_password(password):
    """
    Проверяет, соответствует ли пароль требованиям сложности:
    - Длина не менее 8 символов
    - Содержит как минимум одну заглавную букву
    - Содержит как минимум одну строчную букву
    - Содержит как минимум одну цифру
    - Содержит как минимум один специальный символ
    """
    if len(password) < 8:
        return False
    
    if not re.search(r'[A-Z]', password):  # Заглавная буква
        return False
    
    if not re.search(r'[a-z]', password):  # Строчная буква
        return False
    
    if not re.search(r'[0-9]', password):  # Цифра
        return False
    
    if not re.search(r'[^A-Za-z0-9]', password):  # Спецсимвол
        return False
    
    return True

# Генерация CSRF-токена
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

# Функция для отправки электронной почты
def send_email(to_email, subject, html_content):
    try:
        # Настройки SMTP-сервера
        smtp_server = "smtp.gmail.com"  # Замените на ваш SMTP-сервер
        smtp_port = 587  # Порт (обычно 587 для TLS)
        smtp_username = "ryabikinkirya90@gmail.com"  # Замените на вашу почту
        smtp_password = "ctni nchj orcs ftjz"  # Замените на пароль приложения
        
        # Создание сообщения
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = smtp_username
        message["To"] = to_email
        
        # Добавление HTML-контента
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Отправка письма
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Включение TLS
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, to_email, message.as_string())
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке письма: {str(e)}")
        return False

@register_bp.route("/register", methods=["GET", "POST"])
def register():
    user_id = request.cookies.get('user_id')
    if user_id:
        return redirect(url_for('profile.profile'))

    if request.method == "GET":
        return render_template("register.html", csrf_token=generate_csrf_token())

    if request.method == "POST":
        # Проверка CSRF-токена
        csrf_token = session.pop('_csrf_token', None)
        if not csrf_token or csrf_token != request.form.get('_csrf_token'):
            logger.warning("CSRF-проверка не пройдена при регистрации")
            AdminLogger.warning('auth', 'CSRF-проверка не пройдена при регистрации', 
                               {'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
            return jsonify({"error": "Ошибка безопасности. Попробуйте еще раз."}), 403

        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # Проверка валидности email
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            AdminLogger.warning('auth', 'Попытка регистрации с некорректным email', 
                              {'email': email, 'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
            return jsonify({"error": "Некорректный email адрес"}), 400

        # Проверка длины имени пользователя
        if len(username) < 3 or len(username) > 30:
            AdminLogger.warning('auth', 'Попытка регистрации с некорректным именем пользователя', 
                              {'username': username, 'length': len(username)})
            return jsonify({"error": "Имя пользователя должно содержать от 3 до 30 символов"}), 400

        # Проверка совпадения паролей
        if password != confirm_password:
            logger.warning(f"Пароли не совпадают: {email}")
            AdminLogger.warning('auth', 'Пароли не совпадают при регистрации', {'email': email})
            return jsonify({"error": "Пароли не совпадают"}), 400

        # Проверка сложности пароля
        if not is_password_strong(password):
            AdminLogger.warning('auth', 'Попытка регистрации со слабым паролем', {'email': email})
            return jsonify({"error": "Пароль должен содержать минимум 8 символов, включая буквы и цифры"}), 400

        hashed_pass = hash_password(password)
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Проверка существующего email с параметризованным запросом
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            existing_user = cursor.fetchone()
            if existing_user:
                logger.warning(f"Попытка регистрации с уже занятым email: {email}")
                AdminLogger.warning('auth', 'Попытка регистрации с уже занятым email', 
                                  {'email': email, 'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
                return jsonify({"error": "Этот email уже зарегистрирован"}), 400

            # Добавление пользователя
            cursor.execute(
                "INSERT INTO users (email, username, hashed_password) VALUES (%s, %s, %s) RETURNING id",
                (email, username, hashed_pass)
            )
            user_id = cursor.fetchone()[0]
            conn.commit()

            logger.info(f"Пользователь зарегистрирован: {email}")
            AdminLogger.info('auth', 'Пользователь успешно зарегистрирован', 
                           {'email': email, 'username': username, 'user_id': user_id})
            return redirect(url_for("login.login"))
        except Exception as e:
            logger.error(f"Ошибка при регистрации пользователя {email}: {str(e)}")
            AdminLogger.error('auth', f"Ошибка при регистрации пользователя: {str(e)}", 
                            {'email': email, 'error': str(e)})
            return jsonify({"error": f"Ошибка регистрации: {str(e)}"}), 500
        finally:
            if cursor:
                cursor.close()
            if conn:
                release_db_connection(conn)

@login_bp.route("/login", methods=["GET", "POST"])
def login():
    user_id = request.cookies.get('user_id')
    if user_id:
        return redirect(url_for('profile.profile'))

    if request.method == "GET":
        return render_template("login.html", csrf_token=generate_csrf_token())

    if request.method == "POST":
        # Проверка CSRF-токена
        csrf_token = session.pop('_csrf_token', None)
        if not csrf_token or csrf_token != request.form.get('_csrf_token'):
            logger.warning("CSRF-проверка не пройдена при входе")
            AdminLogger.warning('auth', 'CSRF-проверка не пройдена при входе', 
                              {'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
            return jsonify({"error": "Ошибка безопасности. Попробуйте еще раз."}), 403

        email = request.form.get("email")
        password = request.form.get("password")

        # Проверка на брутфорс
        if not BruteForceProtection.check(email):
            logger.warning(f"Блокировка попыток входа для {email} из-за превышения лимита")
            AdminLogger.warning('auth', 'Блокировка попыток входа из-за превышения лимита', 
                              {'email': email, 'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
            return jsonify({"error": "Слишком много попыток входа. Попробуйте позже."}), 429

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Проверка учетных данных
            cursor.execute("SELECT id, hashed_password FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user and check_password(user[1], password):
                # Успешный вход - создаем безопасные cookies
                resp = make_response(redirect(url_for('profile.profile')))
                resp.set_cookie(
                    'user_id', 
                    str(user[0]), 
                    httponly=True,              # Недоступен из JavaScript
                    secure=True,                # Только через HTTPS
                    samesite='Lax',             # Защита от CSRF
                    max_age=3600 * 24 * 7,      # 7 дней
                    path='/'
                )
                
                # Запись IP-адреса для аудита безопасности
                ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                cursor.execute(
                    "INSERT INTO login_audit (user_id, login_time, ip_address) VALUES (%s, NOW(), %s)",
                    (user[0], ip)
                )
                conn.commit()
                
                # Логирование успешного входа
                AdminLogger.info('auth', 'Успешный вход пользователя', 
                               {'user_id': user[0], 'ip': ip})
                
                return resp
            else:
                # Неудачная попытка входа
                logger.warning(f"Неудачная попытка входа для email: {email}")
                AdminLogger.warning('auth', 'Неудачная попытка входа', 
                                  {'email': email, 'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
                return jsonify({"error": "Неверный email или пароль"}), 401
                
        except Exception as e:
            logger.error(f"Ошибка при входе: {str(e)}")
            AdminLogger.error('auth', f"Ошибка при входе: {str(e)}", 
                            {'email': email, 'error': str(e)})
            return jsonify({"error": "Внутренняя ошибка сервера"}), 500
        finally:
            if cursor:
                cursor.close()
            if conn:
                release_db_connection(conn)

@logout_bp.route("/logout")
def logout():
    # Получаем ID пользователя перед выходом для логирования
    user_id = request.cookies.get('user_id')
    
    # Безопасный выход с инвалидацией cookies
    resp = make_response(redirect(url_for('/.home')))
    resp.delete_cookie('user_id')
    
    # Очистка сессии
    session.clear()
    
    # Логирование выхода пользователя
    if user_id:
        AdminLogger.info('auth', 'Пользователь вышел из системы', {'user_id': user_id})
    
    return resp

# Маршрут для запроса восстановления пароля
@forgot_password_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    # Генерируем CSRF-токен для GET-запроса
    if request.method == "GET":
        csrf_token = generate_csrf_token()
        return render_template("forgot_password.html", csrf_token=csrf_token)
        
    # Обработка POST-запроса
    if request.method == "POST":
        # Проверка CSRF-токена
        csrf_token = request.form.get('_csrf_token')
        if not csrf_token or csrf_token != session.get('_csrf_token'):
            logger.warning("CSRF-проверка не пройдена при восстановлении пароля")
            AdminLogger.warning('auth', 'CSRF-проверка не пройдена при восстановлении пароля', 
                              {'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
                              
            # Определяем, является ли запрос AJAX или обычным
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            if is_ajax:
                return jsonify({
                    'success': False, 
                    'error': 'Истек токен безопасности. Пожалуйста, перезагрузите страницу и попробуйте снова.'
                }), 400
            else:
                return render_template("forgot_password.html", message="Ошибка безопасности. Пожалуйста, попробуйте еще раз.", 
                                    message_type="error", csrf_token=generate_csrf_token())
        
        email = request.form.get("email", "").lower().strip()
        
        # Проверка наличия email
        if not email:
            # Определяем, является ли запрос AJAX или обычным
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            if is_ajax:
                return jsonify({'success': False, 'error': 'Пожалуйста, введите ваш email'}), 400
            else:
                return render_template("forgot_password.html", message="Пожалуйста, введите ваш email", 
                                    message_type="error", csrf_token=generate_csrf_token())
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Проверяем, существует ли пользователь с таким email
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if not user:
                # Не раскрываем информацию о существовании аккаунта
                is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                success_message = "Если указанный email зарегистрирован, на него будет отправлена инструкция по восстановлению пароля."
                
                if is_ajax:
                    return jsonify({'success': True, 'message': success_message})
                else:
                    return render_template("forgot_password.html", message=success_message, 
                                        message_type="success", csrf_token=generate_csrf_token())
            
            # Генерируем токен для сброса пароля
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)  # Токен действителен 24 часа
            
            # Сохраняем токен в базе данных
            cursor.execute(
                "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (user[0], token, expires_at)
            )
            conn.commit()
            
            # Формируем ссылку для восстановления пароля
            reset_link = url_for('auth.reset_password', token=token, _external=True)
            
            # Формируем HTML-контент письма
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #8B5CF6, #6366F1);
                        padding: 20px;
                        text-align: center;
                        color: white;
                        border-radius: 5px 5px 0 0;
                    }}
                    .content {{
                        padding: 20px;
                    }}
                    .button {{
                        display: inline-block;
                        background: #8B5CF6;
                        color: white;
                        text-decoration: none;
                        padding: 10px 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 20px;
                        font-size: 12px;
                        color: #888;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Восстановление пароля</h2>
                    </div>
                    <div class="content">
                        <p>Здравствуйте!</p>
                        <p>Вы запросили восстановление пароля на сайте ROXIN Studio.</p>
                        <p>Для установки нового пароля, пожалуйста, перейдите по ссылке ниже:</p>
                        <p><a href="{reset_link}" class="button">Сбросить пароль</a></p>
                        <p>Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.</p>
                        <p>Ссылка действительна в течение 24 часов.</p>
                    </div>
                    <div class="footer">
                        <p>&copy; 2025 ROXIN Studio. Все права защищены.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Отправляем письмо
            email_sent = send_email(email, "Восстановление пароля в ROXIN Studio", html_content)
            
            # Определяем, является ли запрос AJAX или обычным
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            
            if email_sent:
                success_message = "Инструкции по восстановлению пароля отправлены на ваш email."
                if is_ajax:
                    return jsonify({'success': True, 'message': success_message})
                else:
                    return render_template("forgot_password.html", message=success_message, 
                                        message_type="success", csrf_token=generate_csrf_token())
            else:
                error_message = "Произошла ошибка при отправке инструкций. Пожалуйста, попробуйте позже."
                if is_ajax:
                    return jsonify({'success': False, 'error': error_message}), 500
                else:
                    return render_template("forgot_password.html", message=error_message, 
                                        message_type="error", csrf_token=generate_csrf_token())
        except Exception as e:
            # Логирование ошибки
            logger.error(f"Ошибка при запросе восстановления пароля: {str(e)}")
            AdminLogger.error('auth', f"Ошибка при запросе восстановления пароля", 
                           {'error': str(e)})
            
            # Определяем, является ли запрос AJAX или обычным
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            error_message = "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            
            if is_ajax:
                return jsonify({'success': False, 'error': error_message}), 500
            else:
                return render_template("forgot_password.html", message=error_message, 
                                    message_type="error", csrf_token=generate_csrf_token())
        finally:
            if 'conn' in locals() and conn:
                release_db_connection(conn)

# Маршрут для сброса пароля с использованием токена
@forgot_password_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем действительность токена
        cursor.execute(
            "SELECT user_id, expires_at FROM password_reset_tokens WHERE token = %s AND used = FALSE",
            (token,)
        )
        token_data = cursor.fetchone()
        
        # Если токен не найден или уже использован
        if not token_data:
            return render_template("login.html", message="Недействительная или устаревшая ссылка для сброса пароля", message_type="error")
        
        user_id, expires_at = token_data
        
        # Проверяем, не истек ли срок действия токена
        if expires_at < datetime.now():
            return render_template("login.html", message="Срок действия ссылки для сброса пароля истек", message_type="error")
        
        if request.method == "POST":
            # Проверка CSRF-токена
            csrf_token = request.form.get('_csrf_token')
            if not csrf_token or csrf_token != session.get('_csrf_token'):
                logger.warning("CSRF-проверка не пройдена при сбросе пароля")
                AdminLogger.warning('auth', 'CSRF-проверка не пройдена при сбросе пароля', 
                                  {'ip': request.headers.get('X-Forwarded-For', request.remote_addr)})
                return render_template("reset_password.html", token=token, message="Ошибка безопасности. Пожалуйста, попробуйте еще раз.", message_type="error")
                
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")
            
            # Проверка на совпадение паролей
            if password != confirm_password:
                return render_template("reset_password.html", token=token, message="Пароли не совпадают", message_type="error")
            
            # Проверка сложности пароля
            if not is_strong_password(password):
                return render_template("reset_password.html", token=token, message="Пароль не соответствует требованиям безопасности", message_type="error")
            
            # Хешируем новый пароль
            hashed_password = hash_password(password)
            
            # Обновляем пароль пользователя
            cursor.execute(
                "UPDATE users SET hashed_password = %s WHERE id = %s",
                (hashed_password, user_id)
            )
            
            # Помечаем токен как использованный
            cursor.execute(
                "UPDATE password_reset_tokens SET used = TRUE, used_at = NOW() WHERE token = %s",
                (token,)
            )
            
            conn.commit()
            
            return render_template("login.html", message="Ваш пароль успешно изменен. Теперь вы можете войти с новым паролем.", message_type="success")
        
        # GET-запрос - показываем форму для сброса пароля
        return render_template("reset_password.html", token=token, csrf_token=generate_csrf_token())
        
    except Exception as e:
        logger.error(f"Ошибка при сбросе пароля: {str(e)}")
        AdminLogger.error('auth', f"Ошибка при сбросе пароля: {str(e)}", 
                        {'error': str(e)})
        return render_template("login.html", message="Произошла ошибка при сбросе пароля. Пожалуйста, попробуйте позже.", message_type="error")
    finally:
        cursor.close()
        conn.close()