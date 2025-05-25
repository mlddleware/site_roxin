from flask import Blueprint, render_template, request, redirect, url_for
from database.connection import get_db_connection, release_db_connection, DatabaseConnection
from datetime import datetime, timezone
import os

ban_bp = Blueprint('ban', __name__)

@ban_bp.route('/banned')
def banned():
    """Отображает страницу бана для заблокированного пользователя"""
    user_id = request.cookies.get('user_id')
    
    if not user_id:
        return redirect(url_for('login.login'))
    
    try:
        with DatabaseConnection() as conn:
            # Получаем информацию о пользователе для navbar
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.username, u.email, u.status, u.avatar
                    FROM users u
                    WHERE u.id = %s
                    """,
                    (user_id,)
                )
                
                user_info = cursor.fetchone()
                
                if not user_info:
                    # Если пользователь не найден, перенаправляем на страницу входа
                    return redirect(url_for('login.login'))
                    
                username, email, user_status, avatar = user_info
                
                # Если у пользователя нет аватара, используем стандартный
                if not avatar:
                    avatar = 'user.png'
                
                # Получаем информацию о последнем активном бане пользователя
                cursor.execute(
                    """
                    SELECT reason, banned_at, expires_at
                    FROM user_bans
                    WHERE user_id = %s AND active = TRUE
                    ORDER BY banned_at DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                
                ban_info = cursor.fetchone()
                
                if not ban_info:
                    # Если нет активного бана, перенаправляем на главную
                    return redirect(url_for('/.home'))
                
                reason, banned_at, expires_at = ban_info
                
                # Форматируем даты для отображения
                ban_date = banned_at.strftime('%d.%m.%Y %H:%M')
                ban_expires = expires_at.strftime('%d.%m.%Y %H:%M') if expires_at else None
                
                return render_template('banned.html', 
                                   ban_reason=reason, 
                                   ban_date=ban_date, 
                                   ban_expires=ban_expires,
                                   user_id=user_id,
                                   username=username,
                                   email=email,
                                   user_status=user_status,
                                   avatar=avatar)
    except Exception as e:
        print(f"Ошибка при получении информации о бане: {str(e)}")
        return redirect(url_for('logout.logout'))

def check_user_ban(user_id):
    """
    Проверяет, забанен ли пользователь.
    
    Возвращает:
        bool: True если забанен, False если нет
    """
    if not user_id:
        return False
    
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                # Проверяем, есть ли активный бан
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
                return is_banned
                
    except Exception as e:
        print(f"Ошибка при проверке бана пользователя: {str(e)}")
        return False
