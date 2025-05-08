from functools import wraps
from flask import request, redirect, url_for, abort
from enum import Enum, auto

class UserRole(Enum):
    GUEST = auto()
    USER = auto()
    CODER = auto()
    ADMIN = auto()

# Маппинг строковых статусов в роли
STATUS_TO_ROLE = {
    None: UserRole.GUEST,
    "user": UserRole.USER,
    "coder": UserRole.CODER,
    "admin": UserRole.ADMIN
}

def require_role(min_role):
    """Декоратор для проверки минимальной роли пользователя"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = request.cookies.get('user_id')
            
            # Если пользователь не авторизован
            if not user_id and min_role != UserRole.GUEST:
                return redirect(url_for('login.login'))
                
            # Если требуется роль выше гостя, проверяем роль из БД
            if min_role != UserRole.GUEST:
                from database.connection import get_db_connection, release_db_connection
                
                conn = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
                    result = cursor.fetchone()
                    
                    user_status = result[0] if result else None
                    user_role = STATUS_TO_ROLE.get(user_status, UserRole.GUEST)
                    
                    if user_role.value < min_role.value:
                        abort(403)  # Доступ запрещен
                        
                finally:
                    if cursor:
                        cursor.close()
                    if conn:
                        release_db_connection(conn)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator