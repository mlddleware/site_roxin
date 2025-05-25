from functools import wraps
from flask import redirect, url_for
from database.redis_cache import invalidate_cache

def invalidate_cache_on_action(cache_patterns=None):
    """
    Декоратор для автоматической инвалидации кэша при выполнении действий.
    
    Args:
        cache_patterns (list): Список паттернов кэша для инвалидации.
                              Может содержать {order_id} для замены на реальный ID заказа.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Получаем user_id из cookies
            from flask import request
            user_id = request.cookies.get('user_id')
            
            # Инвалидируем кэш для пользователя
            if user_id:
                invalidate_cache(f"my_orders:{user_id}*")
            
            # Инвалидируем дополнительные паттерны кэша
            if cache_patterns:
                for pattern in cache_patterns:
                    # Заменяем {order_id} на реальный ID заказа, если он есть в kwargs
                    if '{order_id}' in pattern and 'order_id' in kwargs:
                        pattern = pattern.format(order_id=kwargs['order_id'])
                    invalidate_cache(pattern)
            
            # Вызываем оригинальную функцию
            response = f(*args, **kwargs)
            
            # Если ответ - редирект, добавляем параметр refresh=true
            if hasattr(response, 'location'):
                if '?' in response.location:
                    response.location += '&refresh=true'
                else:
                    response.location += '?refresh=true'
            
            return response
        return decorated_function
    return decorator 