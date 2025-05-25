import requests
import json
from datetime import datetime, timedelta
import hashlib
import hmac
import logging

# Настраиваем логирование
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class CryptoBotClient:
    """
    Клиент для интеграции с CryptoBot API (Telegram)
    Документация: https://help.cryptobot.me/en/api
    """
    
    def __init__(self, api_key, app_name):
        """
        Инициализация клиента CryptoBot API
        
        Args:
            api_key (str): API ключ, полученный от @CryptoBot в Telegram
            app_name (str): Название приложения для отображения пользователю
        """
        self.api_key = api_key
        self.app_name = app_name
        self.base_url = "https://pay.crypt.bot/api"
    
    def create_invoice(self, amount, description, currency="RUB", expires_in=3600, 
                       success_url=None, payload=None):
        """
        Создание счета на оплату (invoice)
        
        Args:
            amount (float): Сумма к оплате
            description (str): Описание платежа
            currency (str): Валюта (RUB, USD, EUR, BTC, TON, ETH)
            expires_in (int): Срок действия в секундах
            success_url (str): URL для перенаправления после успешной оплаты
            payload (str): Дополнительные данные для передачи в callback
            
        Returns:
            dict: Ответ от API
        """
        url = f"{self.base_url}/createInvoice"
        
        # Формируем параметры запроса согласно документации CryptoBot
        data = {
            "asset": currency,               # Валюта платежа
            "amount": str(amount),          # Сумма как строка
            "description": description,     # Описание платежа
            "hidden_message": self.app_name, # Скрытое сообщение
            "expires_in": expires_in       # Срок действия в секундах
        }
        
        # Добавляем урл для редиректа после оплаты
        if success_url:
            data["redirect_url"] = success_url
            
        # Добавляем пользовательские данные для callback
        if payload:
            data["payload"] = payload
            
        headers = {
            "Crypto-Pay-API-Token": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Добавляем отладочный вывод запроса
        logger.info(f"Запрос в CryptoBot: URL={url}, Данные={json.dumps(data)}")
        
        try:
            response = requests.post(url, headers=headers, json=data)
            
            # Добавляем отладочный вывод ответа
            logger.info(f"Ответ от CryptoBot: Статус={response.status_code}, Тело={response.text}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка при создании счета в CryptoBot: {e}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f", Тело ответа: {e.response.text}"
            logger.error(error_msg)
            return {"error": str(e)}
    
    def get_invoice(self, invoice_id):
        """
        Получение информации о счете
        
        Args:
            invoice_id (str): ID счета
            
        Returns:
            dict: Ответ от API
        """
        url = f"{self.base_url}/getInvoice"
        
        headers = {
            "Crypto-Pay-API-Token": self.api_key,
            "Content-Type": "application/json"
        }
        
        params = {
            "invoice_id": invoice_id
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении информации о счете в CryptoBot: {e}")
            return {"error": str(e)}
    
    def verify_callback(self, callback_data, signature_header):
        """
        Проверка подписи callback от CryptoBot
        
        Args:
            callback_data (str): Данные callback в формате JSON
            signature_header (str): Значение заголовка Crypto-Pay-API-Signature
            
        Returns:
            bool: True если подпись действительна, иначе False
        """
        if not signature_header:
            return False
        
        # Создаем HMAC подпись с секретным ключом
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            callback_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем подписи
        return hmac.compare_digest(signature, signature_header)
