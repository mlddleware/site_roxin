import os
import psycopg2
import urllib.parse as up
from psycopg2 import pool
import logging
import time
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('database_connection')

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL не найден в переменных окружения!")
    raise EnvironmentError("DATABASE_URL не найден. Проверьте файл .env")

url = up.urlparse(DATABASE_URL)

# Используем ThreadedConnectionPool для многопоточной среды
# Оптимизация для 500+ пользователей
db_pool = pool.ThreadedConnectionPool(
    30, 300,  # min=30, max=300 соединений
    host=url.hostname,
    database=url.path[1:],
    user=url.username,
    password=url.password,
    port=url.port,
    # Дополнительные настройки для стабильности
    connect_timeout=3,      # 3 секунды на подключение
    keepalives=1,           # Включаем keepalive
    keepalives_idle=30,     # Проверка keepalive каждые 30 секунд
    keepalives_interval=10, # Интервал повторной отправки 10 секунд
    keepalives_count=5      # 5 повторных попыток
)

# Счетчики для мониторинга
connections_used = 0
connections_returned = 0

def get_db_connection():
    """Берёт соединение из пула с повторными попытками при исчерпании пула"""
    global connections_used
    
    max_retries = 3  # Максимум 3 попытки получить соединение
    retry_delay = 0.5  # Начальная задержка 0.5 секунды
    
    for attempt in range(max_retries):
        try:
            conn = db_pool.getconn()
            connections_used += 1
            
            # Логируем статистику каждые 50 соединений
            if connections_used % 50 == 0:
                active = connections_used - connections_returned
                logger.info(f"Статистика пула: выдано={connections_used}, возвращено={connections_returned}, активно={active}")
            
            return conn
        except pool.PoolError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Пул соединений исчерпан, повторная попытка {attempt+1}/{max_retries} через {retry_delay} сек.")
                time.sleep(retry_delay)
                retry_delay *= 2  # Увеличиваем задержку экспоненциально
            else:
                logger.error(f"Не удалось получить соединение после {max_retries} попыток: {e}")
                raise

def release_db_connection(conn):
    """Возвращает соединение в пул"""
    global connections_returned
    
    if conn:
        try:
            db_pool.putconn(conn)
            connections_returned += 1
        except Exception as e:
            logger.error(f"Ошибка при возврате соединения в пул: {e}")