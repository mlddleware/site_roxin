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

# Для Render: если DATABASE_URL не найден в .env, используем значение по умолчанию для разработки
if not DATABASE_URL:
    # Для локальной разработки
    if os.path.exists('.env'):
        logger.error("DATABASE_URL не найден в переменных окружения!")
        raise EnvironmentError("DATABASE_URL не найден. Проверьте файл .env")
    else:
        # На Render DATABASE_URL должен быть автоматически установлен
        logger.warning("DATABASE_URL не найден. Возможно, это не продакшен окружение.")
        # Устанавливаем URL по умолчанию для разработки (если нужно)
        DATABASE_URL = "postgresql://localhost:5432/roxin_dev"

# Для Render: корректируем URL если нужно
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    logger.info("Конвертировали postgres:// в postgresql:// для psycopg2")

url = up.urlparse(DATABASE_URL)

# Определяем настройки пула в зависимости от окружения
if os.environ.get('FLASK_ENV') == 'production':
    # Настройки для продакшена на Render
    MIN_CONNECTIONS = 5
    MAX_CONNECTIONS = 20
    logger.info("Используются настройки базы данных для продакшена")
else:
    # Настройки для разработки
    MIN_CONNECTIONS = 2
    MAX_CONNECTIONS = 10
    logger.info("Используются настройки базы данных для разработки")

# Используем ThreadedConnectionPool для многопоточной среды
try:
    db_pool = pool.ThreadedConnectionPool(
        MIN_CONNECTIONS, MAX_CONNECTIONS,
        host=url.hostname,
        database=url.path[1:],
        user=url.username,
        password=url.password,
        port=url.port or 5432,
        # Дополнительные настройки для стабильности
        connect_timeout=10,      # 10 секунд на подключение для Render
        keepalives=1,           # Включаем keepalive
        keepalives_idle=30,     # Проверка keepalive каждые 30 секунд
        keepalives_interval=10, # Интервал повторной отправки 10 секунд
        keepalives_count=5,     # 5 повторных попыток
        sslmode='require' if os.environ.get('FLASK_ENV') == 'production' else 'prefer'  # SSL для продакшена
    )
    logger.info(f"Пул соединений создан успешно: {MIN_CONNECTIONS}-{MAX_CONNECTIONS} соединений")
except Exception as e:
    logger.error(f"Ошибка при создании пула соединений: {e}")
    raise

# Счетчики для мониторинга
connections_used = 0
connections_returned = 0

def get_db_connection():
    """Берёт соединение из пула с повторными попытками при исчерпании пула"""
    global connections_used
    
    max_retries = 5  # Увеличиваем количество попыток для Render
    retry_delay = 1.0  # Увеличиваем начальную задержку
    
    for attempt in range(max_retries):
        try:
            conn = db_pool.getconn()
            connections_used += 1
            
            # Логируем статистику каждые 10 соединений
            if connections_used % 10 == 0:
                active = connections_used - connections_returned
                logger.info(f"Статистика пула: выдано={connections_used}, возвращено={connections_returned}, активно={active}")
                
                # Предупреждение о возможной утечке соединений
                if active > MAX_CONNECTIONS * 0.8:
                    logger.warning(f"Обнаружено {active} активных соединений - возможна утечка!")
            
            return conn
        except pool.PoolError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Пул соединений исчерпан, повторная попытка {attempt+1}/{max_retries} через {retry_delay} сек.")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Увеличиваем задержку
            else:
                logger.error(f"Не удалось получить соединение после {max_retries} попыток: {e}")
                raise

def release_db_connection(conn):
    """Возвращает соединение в пул"""
    global connections_returned
    
    if conn:
        try:
            # Сначала проверим, закрыто ли соединение
            if conn.closed:
                logger.warning("Попытка вернуть закрытое соединение")
                return
                
            # Вернем соединение в пул
            db_pool.putconn(conn)
            connections_returned += 1
        except Exception as e:
            logger.error(f"Ошибка при возврате соединения в пул: {e}")
            # В случае ошибки "unkeyed connection", просто закроем соединение
            if "unkeyed connection" in str(e):
                try:
                    conn.close()
                    logger.info("Соединение закрыто вручную")
                except:
                    pass


class DatabaseConnection:
    """Контекстный менеджер для автоматического возврата соединений в пул"""
    
    def __init__(self):
        self.conn = None
        self.returned = False
        self.cursors = []
    
    def __enter__(self):
        try:
            # Получаем новое соединение из пула
            self.conn = get_db_connection()
            self.returned = False
            
            # Проверяем, открыто ли соединение
            if self.conn.closed:
                logger.warning("Получено закрытое соединение из пула, пытаемся получить новое")
                self.conn = get_db_connection()
                
            return self.conn
        except Exception as e:
            logger.error(f"Ошибка при получении соединения в __enter__: {e}")
            # В случае ошибки возвращаем None и обрабатываем это в коде приложения
            self.returned = True
            raise
            
    def cursor(self):
        """
        Создаёт и возвращает курсор для текущего соединения.
        Этот метод можно использовать вместо прямого вызова conn.cursor().
        
        Например:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            cursor.execute(...)
        """
        if not self.conn or self.conn.closed:
            raise ValueError("Попытка создать курсор для закрытого или несуществующего соединения")
        
        cursor = self.conn.cursor()
        self.cursors.append(cursor)
        return cursor
        
    def commit(self):
        """
        Фиксирует изменения в базе данных.
        Этот метод можно использовать вместо прямого вызова conn.commit().
        
        Например:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            cursor.execute("UPDATE ...")
            db.commit()
        """
        if not self.conn or self.conn.closed:
            raise ValueError("Попытка выполнить commit для закрытого или несуществующего соединения")
        
        self.conn.commit()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn and not self.returned:
            # Закрываем все курсоры, если они остались открытыми
            for cursor in self.cursors:
                try:
                    if cursor and not cursor.closed:
                        cursor.close()
                except Exception as cursor_err:
                    logger.error(f"Ошибка при закрытии курсора: {cursor_err}")
                
            # Очищаем список курсоров
            self.cursors = []
                
            # Отмечаем соединение как возвращенное
            self.returned = True
            
            try:
                # Только если соединение не закрыто, возвращаем его в пул
                if not self.conn.closed:
                    release_db_connection(self.conn)
                else:
                    logger.warning("Попытка вернуть уже закрытое соединение в __exit__")
            except Exception as e:
                logger.error(f"Ошибка в __exit__ при возврате соединения: {e}")
        

def with_db_connection(func):
    """Декоратор для автоматического управления соединениями"""
    def wrapper(*args, **kwargs):
        # Вместо прямого использования get_db_connection и release_db_connection
        # используем контекстный менеджер, который лучше обрабатывает ошибки
        with DatabaseConnection() as conn:
            # Проверяем, что соединение не закрыто перед использованием
            if conn.closed:
                logger.warning("Попытка использовать закрытое соединение в декораторе with_db_connection")
                # Вместо использования закрытого соединения, создаем новый контекст
                with DatabaseConnection() as new_conn:
                    return func(new_conn, *args, **kwargs)
            return func(conn, *args, **kwargs)
    return wrapper


def cleanup_connections():
    """Функция для проверки и очистки неиспользуемых соединений"""
    global connections_used, connections_returned
    
    active = connections_used - connections_returned
    logger.info(f"Очистка соединений... Активно: {active}")
    
    # Сбрасываем счетчики
    connections_used = 0
    connections_returned = 0
    
    try:
        # Перезапускаем пул соединений в критических случаях
        if active > MAX_CONNECTIONS:
            logger.warning("Критическое количество активных соединений, перезапуск пула...")
            db_pool.closeall()
            logger.info("Пул соединений перезапущен")
    except Exception as e:
        logger.error(f"Ошибка при очистке соединений: {e}")


# Функция для проверки соединения с базой данных
def test_database_connection():
    """Тестирует соединение с базой данных"""
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result and result[0] == 1:
                    logger.info("Соединение с базой данных успешно установлено")
                    return True
                else:
                    logger.error("Неожиданный результат тестового запроса")
                    return False
    except Exception as e:
        logger.error(f"Ошибка при тестировании соединения с базой данных: {e}")
        return False