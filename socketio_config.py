from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")

# Обработчик для отправки логов в реальном времени
@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

# Функция для отправки логов всем подключенным клиентам
def emit_log(log_data):
    socketio.emit('new_log', log_data)