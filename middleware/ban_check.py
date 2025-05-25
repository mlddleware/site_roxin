from flask import request, redirect, url_for
from functools import wraps
from routes.ban import check_user_ban
from database.connection import DatabaseConnection

def check_ban_middleware():
    """
    Middleware для проверки бана пользователя перед каждым запросом.
    Если пользователь забанен, он будет перенаправлен на страницу бана.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Исключаем страницу бана и выхода из проверки
            if request.endpoint in ['ban.banned', 'logout.logout', 'static']:
                return f(*args, **kwargs)
            
            user_id = request.cookies.get('user_id')
            
            # Если пользователь не авторизован, продолжаем запрос
            if not user_id:
                return f(*args, **kwargs)
            
            # Проверяем, забанен ли пользователь непосредственно здесь,
            # чтобы избежать создания вложенных контекстов соединений
            try:
                with DatabaseConnection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT EXISTS(
                                SELECT 1 FROM user_bans 
                                WHERE user_id = %s 
                                AND active = TRUE 
                                AND (expires_at IS NULL OR expires_at > NOW())
                            )
                            """,
                            (user_id,)
                        )
                        
                        is_banned = cursor.fetchone()[0]
                        if is_banned:
                            return redirect(url_for('ban.banned'))
            except Exception as e:
                print(f"Ошибка при проверке бана пользователя в middleware: {str(e)}")
                # В случае ошибки продолжаем выполнение запроса
            
            # Пользователь не забанен, продолжаем запрос
            return f(*args, **kwargs)
        return decorated_function
    return decorator
