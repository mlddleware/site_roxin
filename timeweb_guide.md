# 🚀 Деплой ROXIN Studio на Timeweb Cloud

## 1. Создание VPS

### Заходим в панель Timeweb:
1. Регистрируемся на [timeweb.cloud](https://timeweb.cloud)
2. Переходим в раздел **"Облачные серверы"**
3. Нажимаем **"Создать сервер"**

### Конфигурация:
- **ОС**: Ubuntu 22.04 LTS
- **CPU**: 1 ядро
- **RAM**: 1 ГБ
- **Диск**: 10 ГБ SSD
- **Цена**: ~200₽/месяц

### Настройки:
- **Имя**: roxin-studio
- **SSH ключ**: добавь свой публичный ключ или используй пароль
- **Firewall**: пока оставляем по умолчанию

## 2. Подключение к серверу

После создания получишь IP адрес. Подключайся:

```bash
ssh root@YOUR_SERVER_IP
```

## 3. Автоматический деплой

### Скачиваем скрипт деплоя:
```bash
wget https://raw.githubusercontent.com/mlddleware/site_roxin/main/deploy.sh
chmod +x deploy.sh
```

### Запускаем деплой:
```bash
bash deploy.sh
```

Скрипт автоматически:
- ✅ Обновит систему
- ✅ Установит Python, PostgreSQL, Nginx
- ✅ Скачает код с GitHub
- ✅ Настроит базу данных
- ✅ Создаст systemd сервис
- ✅ Настроит Nginx
- ✅ Настроит firewall

## 4. Проверка работы

### Статус сервиса:
```bash
sudo systemctl status roxin-studio
```

### Логи приложения:
```bash
sudo journalctl -u roxin-studio -f
```

### Проверка Nginx:
```bash
sudo nginx -t
sudo systemctl status nginx
```

## 5. Открытие в браузере

Переходи по IP сервера:
```
http://YOUR_SERVER_IP
```

## 6. Настройка домена (опционально)

Если есть домен:

1. **В DNS настройках** домена добавь A-запись:
   ```
   A    @    YOUR_SERVER_IP
   A    www  YOUR_SERVER_IP
   ```

2. **Обновить Nginx конфиг**:
   ```bash
   sudo nano /etc/nginx/sites-available/roxin-studio
   # Замени server_name _ на server_name yourdomain.com www.yourdomain.com;
   sudo systemctl reload nginx
   ```

3. **Установить SSL (Let's Encrypt)**:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
   ```

## 7. Обновление кода

При изменениях в коде:

```bash
cd /var/www/roxin-studio
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart roxin-studio
```

## 8. Мониторинг и обслуживание

### Размер логов:
```bash
sudo journalctl --disk-usage
sudo journalctl --vacuum-time=7d  # Очистка логов старше 7 дней
```

### Обновление системы:
```bash
sudo apt update && sudo apt upgrade
sudo systemctl restart roxin-studio
```

### Бэкап базы данных:
```bash
pg_dump -U roxin_user -h localhost roxin_studio > backup.sql
```

## 🔧 Полезные команды

### Перезапуск сервисов:
```bash
sudo systemctl restart roxin-studio
sudo systemctl restart nginx
sudo systemctl restart postgresql
```

### Просмотр логов:
```bash
# Логи приложения
sudo journalctl -u roxin-studio -f

# Логи Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Логи PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### Управление базой данных:
```bash
# Подключение к БД
sudo -u postgres psql roxin_studio

# Список таблиц
\dt

# Выход
\q
```

## 💰 Стоимость

**Базовая конфигурация**: ~200₽/месяц
- 1 CPU, 1GB RAM, 10GB SSD
- Трафик: безлимитный
- Подходит для 100+ пользователей

**При росте нагрузки**:
- 2 CPU, 2GB RAM: ~400₽/месяц
- 4 CPU, 4GB RAM: ~800₽/месяц

## 🆘 Решение проблем

### Приложение не запускается:
```bash
# Проверяем логи
sudo journalctl -u roxin-studio -n 50

# Проверяем сокет файл
ls -la /var/www/roxin-studio/roxin-studio.sock

# Перезапускаем
sudo systemctl restart roxin-studio
```

### Nginx показывает 502:
```bash
# Проверяем статус приложения
sudo systemctl status roxin-studio

# Проверяем права на сокет
sudo chmod 664 /var/www/roxin-studio/roxin-studio.sock
```

### База данных недоступна:
```bash
# Проверяем PostgreSQL
sudo systemctl status postgresql

# Проверяем подключение
sudo -u postgres psql -l
``` 