import os
from flask import Flask, render_template, request, redirect, url_for
from flask_cors import CORS
import datetime

# Создаём Flask-приложение
app = Flask(__name__)

# Конфигурация для продакшена
if os.environ.get('FLASK_ENV') == 'production':
    app.config['DEBUG'] = False
    app.config['TESTING'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
    
    # Настройка базы данных для Render
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['DATABASE_URL'] = database_url
    
    # Инициализация CORS для продакшена
    CORS(app, resources={
        r"/api/*": {"origins": ["https://*.onrender.com"]},
    })
else:
    app.config['DEBUG'] = True
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    CORS(app)

# Добавление фильтра strftime для Jinja2
@app.template_filter('strftime')
def strftime_filter(date, format='%d.%m.%Y %H:%M:%S'):
    if date is None:
        return ""
    return date.strftime(format)

@app.route('/')
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ROXIN Studio</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #0a0a0f; color: white; }
            .container { max-width: 800px; margin: 0 auto; text-align: center; }
            h1 { color: #6366f1; font-size: 3rem; margin-bottom: 1rem; }
            .status { background: #1f2937; padding: 20px; border-radius: 10px; margin: 20px 0; }
            .success { color: #10b981; }
            .info { color: #3b82f6; }
            a { color: #8b5cf6; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 ROXIN Studio</h1>
            <div class="status">
                <h2 class="success">✅ Сайт успешно развернут!</h2>
                <p class="info">Домен: <a href="https://roxin-site.onrender.com">roxin-site.onrender.com</a></p>
                <p class="info">База данных: Подключена ✅</p>
                <p class="info">Статус: Продакшен 🔥</p>
            </div>
            <p>Цифровая студия разработки готова к работе!</p>
        </div>
    </body>
    </html>
    '''

@app.route('/status')
def status():
    return {
        'status': 'healthy',
        'database': 'connected' if os.environ.get('DATABASE_URL') else 'not configured',
        'environment': os.environ.get('FLASK_ENV', 'development'),
        'domain': 'https://roxin-site.onrender.com'
    }

# Обработчик ошибки 404
@app.errorhandler(404)
def page_not_found(error):
    return '<h1>404 - Страница не найдена</h1><a href="/">Вернуться на главную</a>', 404

# Обработчик ошибки 500
@app.errorhandler(500)
def internal_server_error(error):
    return '<h1>500 - Внутренняя ошибка сервера</h1><a href="/">Вернуться на главную</a>', 500

if __name__ == '__main__':
    if os.environ.get('FLASK_ENV') == 'production':
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)
    else:
        app.run(debug=True, host="0.0.0.0", port=5000) 