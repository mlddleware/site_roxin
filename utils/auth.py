from flask import request, redirect, url_for
from functools import wraps
from enum import Enum, auto

class UserRole(Enum):
    """Перечисление ролей пользователей"""
    USER = "user"
    CODER = "coder" 
    ADMIN = "admin"

def require_role(role):
    """
    Декоратор для проверки роли пользователя.
    
    Args:
        role (UserRole): Требуемая роль для доступа
        
    Returns:
        function: Декоратор, который проверяет роль пользователя
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from database.connection import get_db_connection
            
            user_id = request.cookies.get('user_id')
            
            if not user_id:
                return redirect(url_for('login.login'))
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
                result = cursor.fetchone()
                
                if not result:
                    return redirect(url_for('login.login'))
                
                user_role = result[0]
                
                # Проверяем, соответствует ли роль пользователя требуемой
                if isinstance(role, UserRole):
                    required_role = role.value
                else:
                    required_role = role
                
                # Администраторы имеют доступ ко всему
                if user_role == UserRole.ADMIN.value:
                    return f(*args, **kwargs)
                
                # Проверяем требуемую роль
                if user_role != required_role:
                    return redirect(url_for('/.home'))
                
                return f(*args, **kwargs)
            except Exception as e:
                print(f"Ошибка при проверке роли: {str(e)}")
                return redirect(url_for('/.home'))
            finally:
                cursor.close()
                conn.close()
        
        return decorated_function
    
    return decorator
