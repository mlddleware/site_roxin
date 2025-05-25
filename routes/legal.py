from flask import Blueprint, render_template, request, redirect, url_for
from datetime import datetime
from database.connection import get_db_connection, release_db_connection

legal_bp = Blueprint('legal', __name__)

# Глобальный словарь аватаров по статусу
avatar_map = {
    "user": "user.png",
    "admin": "admin.png", 
    "coder": "coder.png",
    "designer": "designer.png",
    "intern": "user.png"
}

@legal_bp.route('/terms')
def terms():
    """Страница с пользовательским соглашением"""
    user_id = request.cookies.get('user_id')
    current_date = '08.05.2025'  # Дата последнего обновления соглашения
    current_year = datetime.now().year
    
    # Добавляем данные пользователя для navbar, если пользователь авторизован
    username = None
    status = None
    avatar = None
    
    if user_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT username, status, avatar FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            
            if user_data:
                username, status, user_avatar = user_data
                avatar = user_avatar if user_avatar else avatar_map.get(status, "user.png")
                
            cursor.close()
            release_db_connection(conn)
        except Exception as e:
            print(f"Ошибка при получении данных пользователя: {e}")
    
    return render_template('terms.html', current_date=current_date, current_year=current_year, 
                           username=username, status=status, user_status=status, avatar=avatar)

@legal_bp.route('/rules')
def rules():
    """Страница с правилами сайта"""
    user_id = request.cookies.get('user_id')
    current_date = '08.05.2025'  # Дата последнего обновления правил
    current_year = datetime.now().year
    
    # Добавляем данные пользователя для navbar, если пользователь авторизован
    username = None
    status = None
    avatar = None
    
    if user_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT username, status, avatar FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            
            if user_data:
                username, status, user_avatar = user_data
                avatar = user_avatar if user_avatar else avatar_map.get(status, "user.png")
                
            cursor.close()
            release_db_connection(conn)
        except Exception as e:
            print(f"Ошибка при получении данных пользователя: {e}")
    
    return render_template('rules.html', current_date=current_date, current_year=current_year, 
                           username=username, status=status, user_status=status, avatar=avatar)
