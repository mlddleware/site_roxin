import os
from flask import Flask
from socketio_config import socketio
from database.connection import get_db_connection
from routes.profile import profile_bp
from routes.home import home_bp
from routes.orders import my_orders_bp, coder_orders_bp, update_order_bp, accept_order_bp, orders_view_bp, order_bp
from routes.users import users_bp
from routes.auth import register_bp, login_bp, logout_bp, forgot_password_bp
from routes.timezone import timezone_bp
from routes.chat import chat_bp
from routes.settings import settings_bp
from routes.notifications import notifications_bp
from routes.finances import finances_bp
from utils import logging
from flask_cors import CORS
from security.headers import add_security_headers
from routes.admin import admin_bp

# Инициализация SocketIO
app = Flask(__name__)  # Создаём Flask-приложение
socketio.init_app(app)  # Теперь socketio подключается здесь

# Инициализация CORS с безопасными настройками
#cors = CORS(app, resources={r"/api/*": {"origins": "https://твой-домен.com"}})

# Настройка секретного ключа для сессий
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Регистрация функции добавления заголовков безопасности
app.after_request(add_security_headers)

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
app.register_blueprint(forgot_password_bp, url_prefix='/')
app.register_blueprint(admin_bp, url_prefix='/')
app.register_blueprint(notifications_bp, url_prefix='/')
app.register_blueprint(finances_bp, url_prefix='/')

@app.after_request
def add_security_headers(response):
    # Защита от XSS
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Запрет встраивания сайта в iframe
    response.headers['X-Frame-Options'] = 'DENY'
    # Запрет определения типа контента браузером
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Content Security Policy
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.socket.io; style-src 'self' https://cdnjs.cloudflare.com https://fonts.googleapis.com 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:;"
    
    return response

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)