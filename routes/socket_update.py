from asyncio.log import logger
from socketio_config import socketio
from notifications.message_notifier import notify_new_message

@socketio.on("send_message")
def handle_send_message_with_notification(data):
    # Убедитесь, что в data есть все необходимые поля
    sender_id = data.get("sender_id")
    recipient_id = data.get("user_id")
    message = data.get("message")
    
    logger.info(f"Получено сообщение: {data}")
    
    # Проверяем наличие необходимых данных
    if not sender_id or not recipient_id or not message:
        logger.warning("Недостаточно данных для отправки уведомления")
        return
    
    # Отправляем уведомление в Telegram
    notify_new_message(sender_id, recipient_id, message)