# ROXIN Studio

Инновационная студия цифровой разработки. Создаем современные веб-приложения, мобильные приложения и цифровые решения.

## 🚀 Быстрый старт

### Локальная разработка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/ваш-юзернейм/roxin-studio.git
cd roxin-studio
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env`:
```env
FLASK_ENV=development
DATABASE_URL=postgresql://username:password@localhost:5432/roxin_studio
FLASK_SECRET_KEY=your-secret-key
```

4. Запустите приложение:
```bash
python app.py
```

### Деплой на Render

Проект настроен для автоматического деплоя на Render.com:

1. Форкните этот репозиторий
2. Подключите к Render через Blueprint
3. Render автоматически прочитает `render.yaml`

## 📋 Структура проекта

```
roxin-studio/
├── app.py                 # Главное приложение
├── requirements.txt       # Зависимости Python
├── render.yaml           # Конфигурация Render
├── database/             # Модули базы данных
├── routes/               # Маршруты Flask
├── templates/            # HTML шаблоны
├── static/              # Статические файлы
├── utils/               # Утилиты
└── security/            # Модули безопасности
```

## 🛠️ Технологии

- **Backend**: Flask, Python 3.11
- **Database**: PostgreSQL
- **Frontend**: HTML5, CSS3, JavaScript
- **Deployment**: Render.com
- **Real-time**: Socket.IO

## 📝 Лицензия

Этот проект создан для демонстрационных целей.

## 👨‍💻 Разработчик

ROXIN Studio - Инновационная студия разработки 