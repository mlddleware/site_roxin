#!/usr/bin/env bash
# exit on error
set -o errexit

# Установка зависимостей Python
pip install -r requirements.txt

# Создание таблиц базы данных (если нужно)
python -c "
import os
import sys
sys.path.append('.')

try:
    from database.connection import test_database_connection
    from utils.init_db import init_database
    
    print('Testing database connection...')
    if test_database_connection():
        print('Database connection successful')
        print('Initializing database...')
        init_database()
        print('Database initialization complete')
    else:
        print('Database connection failed - continuing anyway')
except Exception as e:
    print(f'Database setup failed: {e}')
    print('Continuing without database initialization...')
"

echo "Build completed successfully!" 