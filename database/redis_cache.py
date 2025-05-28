import json
import os
import logging
from datetime import timedelta
from functools import wraps
from dotenv import load_dotenv

# Попытка импорта Redis - если не удается, используем заглушки
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('redis_cache')

# Подключение к Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client = None

if REDIS_AVAILABLE:
    try:
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()  # Проверяем соединение
        logger.info("Успешное подключение к Redis")
    except Exception as e:
        logger.warning(f"Не удалось подключиться к Redis: {str(e)}. Кэширование отключено.")
        redis_client = None
else:
    logger.warning("Redis не установлен. Кэширование отключено.")

def is_redis_available():
    """Проверяет доступность Redis"""
    if not REDIS_AVAILABLE or redis_client is None:
        return False
    
    try:
        redis_client.ping()
        return True
    except:
        return False

def cache_set(key, value, expiration=3600):
    """
    Сохраняет данные в Redis-кэш
    
    Args:
        key (str): Ключ для хранения данных
        value (any): Данные для кэширования (будут сериализованы в JSON)
        expiration (int): Время жизни кэша в секундах (по умолчанию 1 час)
    """
    if not is_redis_available():
        return False
    
    try:
        # Используем пользовательский JSONEncoder для работы с Decimal
        class DecimalEncoder(json.JSONEncoder):
            def default(self, obj):
                from decimal import Decimal
                if isinstance(obj, Decimal):
                    return float(obj)  # Преобразуем Decimal в float
                return super(DecimalEncoder, self).default(obj)
        
        serialized_value = json.dumps(value, cls=DecimalEncoder)
        redis_client.setex(key, expiration, serialized_value)
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении в кэш: {str(e)}")
        return False

def cache_get(key):
    """
    Получает данные из Redis-кэша
    
    Args:
        key (str): Ключ для получения данных
        
    Returns:
        any: Десериализованные данные из кэша или None, если данных нет
    """
    if not is_redis_available():
        return None
    
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении из кэша: {str(e)}")
        return None

def cache_delete(key):
    """Удаляет данные из кэша по ключу"""
    if not is_redis_available():
        return False
    
    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении из кэша: {str(e)}")
        return False

def cache_clear_pattern(pattern):
    """Очищает кэш по шаблону ключа"""
    if not is_redis_available():
        return False
    
    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
        return True
    except Exception as e:
        logger.error(f"Ошибка при очистке кэша по шаблону: {str(e)}")
        return False

def cached(key_prefix, expiration=3600):
    """
    Декоратор для кэширования результатов функций
    
    Args:
        key_prefix (str): Префикс для ключа кэша
        expiration (int): Время жизни кэша в секундах
        
    Example:
        @cached('user_profile', 300)
        def get_user_profile(user_id):
            # Логика получения профиля пользователя
            return profile_data
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_redis_available():
                # Если Redis недоступен, просто вызываем функцию без кэширования
                return func(*args, **kwargs)
            
            # Создаем уникальный ключ на основе аргументов функции
            key_parts = [key_prefix]
            if args:
                key_parts.extend([str(arg) for arg in args])
            if kwargs:
                key_parts.extend([f"{k}_{v}" for k, v in kwargs.items()])
            
            cache_key = ":".join(key_parts)
            
            # Пытаемся получить данные из кэша
            cached_data = cache_get(cache_key)
            if cached_data is not None:
                logger.info(f"Данные получены из кэша: {cache_key}")
                return cached_data
            
            # Если данных нет в кэше, вызываем функцию
            result = func(*args, **kwargs)
            
            # Сохраняем результат в кэш
            if result is not None:
                cache_set(cache_key, result, expiration)
                logger.info(f"Данные сохранены в кэш: {cache_key}")
            
            return result
        return wrapper
    return decorator

def invalidate_cache(key_prefix, *args, **kwargs):
    """
    Инвалидирует кэш для конкретного ключа
    
    Args:
        key_prefix (str): Префикс ключа кэша
        args, kwargs: Аргументы, которые были переданы в функцию
    """
    if not is_redis_available():
        return
    
    key_parts = [key_prefix]
    if args:
        key_parts.extend([str(arg) for arg in args])
    if kwargs:
        key_parts.extend([f"{k}_{v}" for k, v in kwargs.items()])
    
    cache_key = ":".join(key_parts)
    cache_delete(cache_key)
    logger.info(f"Кэш инвалидирован: {cache_key}")
