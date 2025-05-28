import os
from flask import Flask

# Создаём Flask-приложение
app = Flask(__name__)

# Конфигурация для продакшена
if os.environ.get('FLASK_ENV') == 'production':
    app.config['DEBUG'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
else:
    app.config['DEBUG'] = True
    app.config['SECRET_KEY'] = 'dev-secret-key'

@app.route('/')
def home():
    return '<h1>ROXIN Studio</h1><p>Сайт успешно развернут на Render!</p><p>База данных: ' + str(os.environ.get('DATABASE_URL', 'Не настроена')) + '</p>'

@app.route('/health')
def health():
    return {'status': 'healthy'}, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 