#!/bin/bash

# Скрипт деплоя ROXIN Studio на Timeweb Cloud
# Запуск: bash deploy.sh

echo "🚀 Начинаем деплой ROXIN Studio..."

# Обновление системы
echo "📦 Обновляем систему..."
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
echo "🔧 Устанавливаем зависимости..."
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx git

# Создание пользователя для PostgreSQL
echo "🗄️ Настраиваем PostgreSQL..."
sudo -u postgres createuser --createdb --no-superuser --no-createrole roxin_user
sudo -u postgres createdb roxin_studio --owner=roxin_user

# Установка пароля для пользователя PostgreSQL
sudo -u postgres psql -c "ALTER USER roxin_user WITH PASSWORD 'roxin_secure_2024';"

# Создание директории для проекта
echo "📁 Создаем директории..."
sudo mkdir -p /var/www/roxin-studio
sudo chown $USER:$USER /var/www/roxin-studio
cd /var/www/roxin-studio

# Клонирование репозитория (замени на свой URL)
echo "📥 Клонируем код..."
git clone https://github.com/mlddleware/site_roxin.git .

# Создание виртуального окружения
echo "🐍 Создаем виртуальное окружение..."
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей Python
echo "📚 Устанавливаем Python зависимости..."
pip install --upgrade pip
pip install -r requirements.txt

# Создание .env файла
echo "⚙️ Создаем конфигурацию..."
cat > .env << EOF
FLASK_ENV=production
DATABASE_URL=postgresql://roxin_user:roxin_secure_2024@localhost:5432/roxin_studio
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
REDIS_URL=redis://localhost:6379/0
CRYPTOBOT_API_KEY=demo_mode
CRYPTOBOT_APP_NAME=ROXIN Studio
EOF

# Инициализация базы данных
echo "🗄️ Инициализируем базу данных..."
python3 -c "
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

with open('database/init_schema.sql', 'r') as f:
    cursor.execute(f.read())

conn.commit()
print('✅ База данных инициализирована!')
"

# Создание systemd сервиса
echo "🔧 Создаем systemd сервис..."
sudo tee /etc/systemd/system/roxin-studio.service > /dev/null << EOF
[Unit]
Description=ROXIN Studio Flask App
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=/var/www/roxin-studio
Environment="PATH=/var/www/roxin-studio/venv/bin"
ExecStart=/var/www/roxin-studio/venv/bin/gunicorn --workers 3 --bind unix:roxin-studio.sock -m 007 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Запуск и включение сервиса
sudo systemctl daemon-reload
sudo systemctl start roxin-studio
sudo systemctl enable roxin-studio

# Настройка Nginx
echo "🌐 Настраиваем Nginx..."
sudo tee /etc/nginx/sites-available/roxin-studio > /dev/null << EOF
server {
    listen 80;
    server_name _; # Замени на свой домен

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/roxin-studio/roxin-studio.sock;
    }

    location /static {
        alias /var/www/roxin-studio/static;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Ограничение размера загружаемых файлов
    client_max_body_size 10M;
}
EOF

# Включение сайта
sudo ln -sf /etc/nginx/sites-available/roxin-studio /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# Настройка firewall
echo "🔒 Настраиваем firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "✅ Деплой завершен!"
echo "🌐 Сайт доступен по IP сервера"
echo "📊 Проверить статус: sudo systemctl status roxin-studio"
echo "📝 Логи: sudo journalctl -u roxin-studio -f" 