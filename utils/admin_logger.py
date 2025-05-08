import json
import logging
from database.connection import get_db_connection, release_db_connection
from socketio_config import emit_log
from datetime import datetime
from flask import request

class AdminLogger:
    """
    Класс для логирования в админ-панели.
    Записывает логи в базу данных и отправляет их через Socket.IO.
    """
    
    @staticmethod
    def log(level, source, message, details=None, user_id=None):
        """
        Записывает лог в базу данных и отправляет его через Socket.IO.
        
        Args:
            level (str): Уровень лога (INFO, WARNING, ERROR, CRITICAL).
            source (str): Источник лога (auth, orders, users и т.д.).
            message (str): Сообщение лога.
            details (dict, optional): Дополнительные детали в формате JSON.
            user_id (int, optional): ID пользователя.
        """
        # Проверяем уровень лога
        if level not in ['INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            level = 'INFO'
        
        # Получаем IP-адрес, если доступен
        ip_address = None
        try:
            if request:
                ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        except:
            pass
        
        # Если user_id не указан, пытаемся получить из cookies
        if user_id is None:
            try:
                if request:
                    user_id = request.cookies.get('user_id')
            except:
                pass
        
        # Создаем соединение с базой данных
        conn = None
        cursor = None
        log_id = None
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Записываем лог в базу данных
            cursor.execute(
                """
                INSERT INTO system_logs 
                (level, source, message, details, ip_address, user_id) 
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    level,
                    source,
                    message,
                    json.dumps(details) if details else None,
                    ip_address,
                    user_id
                )
            )
            
            log_id, created_at = cursor.fetchone()
            conn.commit()
            
            # Формируем данные для отправки через Socket.IO
            log_data = {
                'id': log_id,
                'level': level,
                'source': source,
                'message': message,
                'details': details,
                'ip_address': ip_address,
                'user_id': user_id,
                'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Отправляем лог через Socket.IO
            emit_log(log_data)
            
            # Логируем в стандартный логгер Python
            python_level = getattr(logging, level)
            logging.log(python_level, f"[{source}] {message}")
            
            return log_id
        except Exception as e:
            # Если произошла ошибка, логируем её стандартным логгером
            logging.error(f"Ошибка при записи лога: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                release_db_connection(conn)
    
    @staticmethod
    def info(source, message, details=None, user_id=None):
        """Записывает информационный лог."""
        return AdminLogger.log('INFO', source, message, details, user_id)
    
    @staticmethod
    def warning(source, message, details=None, user_id=None):
        """Записывает предупреждающий лог."""
        return AdminLogger.log('WARNING', source, message, details, user_id)
    
    @staticmethod
    def error(source, message, details=None, user_id=None):
        """Записывает лог об ошибке."""
        return AdminLogger.log('ERROR', source, message, details, user_id)
    
    @staticmethod
    def critical(source, message, details=None, user_id=None):
        """Записывает критический лог."""
        return AdminLogger.log('CRITICAL', source, message, details, user_id)
