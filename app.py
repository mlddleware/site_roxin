import os
from flask import Flask, render_template, request, redirect, url_for, g
from socketio_config import socketio
from database.connection import get_db_connection, release_db_connection, DatabaseConnection
import datetime
from routes.profile import profile_bp
from routes.home import home_bp
from routes.orders import my_orders_bp, coder_orders_bp, update_order_bp, accept_order_bp, orders_view_bp, order_bp
from routes.users import users_bp
from routes.auth import register_bp, login_bp, logout_bp, forgot_password_bp
from routes.timezone import timezone_bp
from routes.legal import legal_bp
from routes.chat import chat_bp
from routes.settings import settings_bp
from routes.notifications import notifications_bp
from routes.finances import finances_bp
from routes.ban import ban_bp
from routes.admin_bans import admin_bans_bp
from routes.tickets import tickets_bp
from utils import logging
from flask_cors import CORS
from security.headers import add_security_headers
from routes.admin import admin_bp
from jinja2.exceptions import TemplateSyntaxError

# Создаём Flask-приложение
app = Flask(__name__)

# Инициализация SocketIO
socketio.init_app(app)

# Конфигурация для продакшена
if os.environ.get('FLASK_ENV') == 'production':
    app.config['DEBUG'] = False
    app.config['TESTING'] = False
    # Настройка секретного ключа из переменной окружения
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
    
    # Настройка базы данных для Render
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Render предоставляет DATABASE_URL в формате postgres://
        # но psycopg2 требует postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['DATABASE_URL'] = database_url
    
    # Инициализация CORS для продакшена
    CORS(app, resources={
        r"/api/*": {"origins": ["https://*.onrender.com"]},
        r"/socket.io/*": {"origins": ["https://*.onrender.com"]}
    })
else:
    # Настройки для разработки
    app.config['DEBUG'] = True
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    # CORS для разработки
    CORS(app)

# Добавление фильтра strftime для Jinja2
@app.template_filter('strftime')
def strftime_filter(date, format='%d.%m.%Y %H:%M:%S'):
    if date is None:
        return ""
    return date.strftime(format)

# Регистрация функции добавления заголовков безопасности
app.after_request(add_security_headers)

# Проверка бана пользователя перед каждым запросом
@app.before_request
def check_user_ban():
    # Исключаем страницы, которые не требуют проверки бана
    excluded_endpoints = ['ban.banned', 'logout.logout', 'static', 'settings.settings', 'login.login', 'register.register']
    if request.endpoint in excluded_endpoints:
        return
    
    user_id = request.cookies.get('user_id')
    
    # Если пользователь не авторизован, продолжаем запрос
    if not user_id:
        return
    
    # Проверяем, забанен ли пользователь
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM user_bans 
                        WHERE user_id = %s 
                        AND active = TRUE 
                        AND (expires_at IS NULL OR expires_at > NOW())
                    )
                    """,
                    (user_id,)
                )
                
                is_banned = cursor.fetchone()[0]
                if is_banned:
                    return redirect(url_for('ban.banned'))
    except Exception as e:
        print(f"Ошибка при проверке бана пользователя: {str(e)}")
        # В случае ошибки продолжаем выполнение запроса
        pass

# Регистрация Blueprints
app.register_blueprint(profile_bp, url_prefix='/')
app.register_blueprint(home_bp, url_prefix='/')
app.register_blueprint(users_bp, url_prefix='/')
app.register_blueprint(my_orders_bp, url_prefix='/')
app.register_blueprint(coder_orders_bp, url_prefix='/')
app.register_blueprint(update_order_bp, url_prefix='/')
app.register_blueprint(accept_order_bp, url_prefix='/')
app.register_blueprint(orders_view_bp, url_prefix='/')
app.register_blueprint(order_bp, url_prefix='/')
app.register_blueprint(register_bp, url_prefix='/')
app.register_blueprint(login_bp, url_prefix='/')
app.register_blueprint(logout_bp, url_prefix='/')
app.register_blueprint(timezone_bp, url_prefix='/')
app.register_blueprint(chat_bp, url_prefix='/')
app.register_blueprint(settings_bp, url_prefix='/')
app.register_blueprint(notifications_bp, url_prefix='/')
app.register_blueprint(finances_bp, url_prefix='/')
app.register_blueprint(ban_bp, url_prefix='/')
app.register_blueprint(admin_bans_bp, url_prefix='/')
app.register_blueprint(admin_bp, url_prefix='/')
app.register_blueprint(legal_bp, url_prefix='/')
app.register_blueprint(forgot_password_bp, url_prefix='/')
app.register_blueprint(tickets_bp, url_prefix='/')

@app.after_request
def add_security_headers(response):
    # Защита от XSS
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Запрет встраивания сайта в iframe
    response.headers['X-Frame-Options'] = 'DENY'
    # Запрет определения типа контента браузером
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Content Security Policy для продакшена
    if os.environ.get('FLASK_ENV') == 'production':
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.socket.io; style-src 'self' https://cdnjs.cloudflare.com https://fonts.googleapis.com 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' wss:;"
    else:
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.socket.io; style-src 'self' https://cdnjs.cloudflare.com https://fonts.googleapis.com 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:;"
    
    return response

# Обработчик ошибки 404
@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

# Обработчик ошибки 500 (внутренняя ошибка сервера)
@app.errorhandler(500)
def internal_server_error(error):
    return render_template('404.html'), 500

# Обработчик ошибки 403 (доступ запрещен)
@app.errorhandler(403)
def forbidden(error):
    return render_template('404.html'), 403

# Обработчик ошибки 400 (неверный запрос)
@app.errorhandler(400)
def bad_request(error):
    return render_template('404.html'), 400

# Обработчик ошибки TemplateSyntaxError
@app.errorhandler(TemplateSyntaxError)
def template_syntax_error(error):
    error_details = str(error)
    timestamp = datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    return render_template('template_error.html', 
                         error_details=error_details,
                         timestamp=timestamp), 500

if __name__ == '__main__':
    if os.environ.get('FLASK_ENV') == 'production':
        # В продакшене используем gunicorn
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)
    else:
        # В разработке используем встроенный сервер
        socketio.run(app, debug=True, host="0.0.0.0", port=5000) 