from flask import Blueprint, request, jsonify, redirect, url_for, render_template
from database.connection import get_db_connection
from utils.auth import require_role, UserRole
from datetime import datetime, timezone, timedelta
import json

admin_bans_bp = Blueprint('admin_bans', __name__)

@admin_bans_bp.route('/api/admin/users/<int:user_id>/ban', methods=['POST'])
@require_role(UserRole.ADMIN)
def ban_user(user_id):
    """API для бана пользователя"""
    admin_id = request.cookies.get('user_id')
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'Не авторизован'}), 401
    
    data = request.json
    reason = data.get('reason', '')
    duration_days = data.get('duration_days', None)
    
    if not reason:
        return jsonify({'success': False, 'error': 'Необходимо указать причину бана'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование пользователя
        cursor.execute("SELECT id, status FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        # Проверяем, не пытаемся ли мы забанить админа
        if user[1] == 'admin':
            return jsonify({'success': False, 'error': 'Невозможно забанить администратора'}), 403
        
        # Вычисляем дату окончания бана, если указана длительность
        expires_at = None
        if duration_days and duration_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
        
        # Деактивируем все активные баны пользователя
        cursor.execute(
            "UPDATE user_bans SET active = FALSE WHERE user_id = %s AND active = TRUE",
            (user_id,)
        )
        
        # Добавляем новый бан
        cursor.execute(
            """
            INSERT INTO user_bans (user_id, reason, admin_id, expires_at, active)
            VALUES (%s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (user_id, reason, admin_id, expires_at)
        )
        
        ban_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Пользователь успешно забанен',
            'ban_id': ban_id
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@admin_bans_bp.route('/api/admin/users/<int:user_id>/unban', methods=['POST'])
@require_role(UserRole.ADMIN)
def unban_user(user_id):
    """API для разбана пользователя"""
    admin_id = request.cookies.get('user_id')
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'Не авторизован'}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование пользователя
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        # Деактивируем все активные баны пользователя
        cursor.execute(
            "UPDATE user_bans SET active = FALSE WHERE user_id = %s AND active = TRUE",
            (user_id,)
        )
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'У пользователя нет активных банов'}), 400
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Пользователь успешно разбанен'
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@admin_bans_bp.route('/api/admin/bans', methods=['GET'])
@require_role(UserRole.ADMIN)
def get_all_bans():
    """API для получения списка всех банов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT ub.id, ub.user_id, u.username, ub.reason, ub.admin_id, 
                   a.username as admin_username, ub.banned_at, ub.expires_at, ub.active
            FROM user_bans ub
            JOIN users u ON ub.user_id = u.id
            JOIN users a ON ub.admin_id = a.id
            ORDER BY ub.banned_at DESC
            """
        )
        
        bans = []
        for row in cursor.fetchall():
            ban = {
                'id': row[0],
                'user_id': row[1],
                'username': row[2],
                'reason': row[3],
                'admin_id': row[4],
                'admin_username': row[5],
                'banned_at': row[6].isoformat() if row[6] else None,
                'expires_at': row[7].isoformat() if row[7] else None,
                'active': row[8]
            }
            bans.append(ban)
        
        return jsonify({
            'success': True,
            'bans': bans
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@admin_bans_bp.route('/api/admin/users/<int:user_id>/bans', methods=['GET'])
@require_role(UserRole.ADMIN)
def get_user_bans(user_id):
    """API для получения всех банов конкретного пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование пользователя
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        cursor.execute(
            """
            SELECT ub.id, ub.reason, ub.admin_id, a.username as admin_username, 
                   ub.banned_at, ub.expires_at, ub.active
            FROM user_bans ub
            JOIN users a ON ub.admin_id = a.id
            WHERE ub.user_id = %s
            ORDER BY ub.banned_at DESC
            """,
            (user_id,)
        )
        
        bans = []
        for row in cursor.fetchall():
            ban = {
                'id': row[0],
                'reason': row[1],
                'admin_id': row[2],
                'admin_username': row[3],
                'banned_at': row[4].isoformat() if row[4] else None,
                'expires_at': row[5].isoformat() if row[5] else None,
                'active': row[6]
            }
            bans.append(ban)
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'bans': bans
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
