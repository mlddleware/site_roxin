from flask import request, jsonify
from database.connection import get_db_connection, release_db_connection
import time

# Простая реализация защиты от брутфорса
class BruteForceProtection:
    # Ключ - IP, значение - [счетчик_попыток, время_первой_попытки]
    attempts = {}
    
    # Максимум 5 попыток за 10 минут
    MAX_ATTEMPTS = 5
    WINDOW_SECONDS = 600
    
    @classmethod
    def check(cls, email):
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        key = f"{ip}:{email}"
        current_time = time.time()
        
        # Очищаем старые записи
        cls._clean_old_records(current_time)
        
        # Получаем счетчик попыток и время первой попытки
        if key not in cls.attempts:
            cls.attempts[key] = [1, current_time]
            return True
        
        # Проверяем, не превышен ли лимит
        attempts, first_attempt_time = cls.attempts[key]
        
        # Если прошло больше WINDOW_SECONDS с первой попытки, сбрасываем счетчик
        if current_time - first_attempt_time > cls.WINDOW_SECONDS:
            cls.attempts[key] = [1, current_time]
            return True
        
        # Инкрементируем счетчик
        cls.attempts[key][0] += 1
        
        # Проверяем, не превышен ли лимит
        if cls.attempts[key][0] > cls.MAX_ATTEMPTS:
            # Записываем в базу данных для дальнейшего анализа
            cls._log_blocked_attempt(ip, email)
            return False
            
        return True
    
    @classmethod
    def _clean_old_records(cls, current_time):
        # Очищаем старые записи
        keys_to_remove = []
        for key, (_, first_time) in cls.attempts.items():
            if current_time - first_time > cls.WINDOW_SECONDS:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del cls.attempts[key]
    
    @classmethod
    def _log_blocked_attempt(cls, ip, email):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO failed_logins (email, ip_address) VALUES (%s, %s)",
                (email, ip)
            )
            conn.commit()
        except Exception as e:
            print(f"Ошибка при логировании заблокированной попытки: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                release_db_connection(conn)