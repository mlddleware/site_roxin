from flask import Blueprint, request, jsonify, make_response
from utils import logging

timezone_bp = Blueprint('set_timezone', __name__)

@timezone_bp.route("/set_timezone", methods=["POST"])
def set_timezone():
    try:
        data = request.get_json()
        user_timezone = data.get("timezone")

        # Сохраняем часовой пояс в cookie
        response = make_response(jsonify({"message": "Timezone set"}))
        response.set_cookie("user_timezone", user_timezone)

        return response
    except Exception as e:
        logging.error(f"Ошибка установки часового пояса: {e}")
        return jsonify({"error": "Не удалось установить часовой пояс"}), 500