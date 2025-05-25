from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from database.connection import get_db_connection, DatabaseConnection
from datetime import datetime, timezone
import uuid
import decimal
import os
import json
from decimal import Decimal
from integrations.cryptobot import CryptoBotClient

finances_bp = Blueprint('finances', __name__)

# Инициализация клиента CryptoBot
cryptobot_api_key = os.environ.get('CRYPTOBOT_API_KEY', 'demo_mode')
cryptobot_app_name = os.environ.get('CRYPTOBOT_APP_NAME', 'ROXIN Studio')
CRYPTOBOT_SUCCESS_URL = os.environ.get('CRYPTOBOT_SUCCESS_URL', '/finances/deposit/success')

# Отладочный вывод для проверки значения ключа
print(f"[DEBUG] CryptoBot API Key: {cryptobot_api_key[:10]}... (length: {len(cryptobot_api_key)})")

# Демо-режим для работы без реального API ключа
DEMO_MODE = cryptobot_api_key == 'demo_mode' or not cryptobot_api_key
print(f"[DEBUG] CryptoBot DEMO_MODE: {DEMO_MODE}")

# Если не в демо-режиме, используем реальный клиент
cryptobot_client = CryptoBotClient(cryptobot_api_key, cryptobot_app_name) if not DEMO_MODE else None

@finances_bp.route("/finances")
def finances():
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect('/login')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные пользователя
        cursor.execute(
            """
            SELECT u.username, u.status, u.avatar, p.balance, 
                   COALESCE(p.monthly_deposit, 0) as monthly_deposit, 
                   COALESCE(p.monthly_withdraw, 0) as monthly_withdraw 
            FROM users u
            LEFT JOIN user_profiles p ON u.id = p.user_id
            WHERE u.id = %s
            """, 
            (user_id,)
        )
        user_data = cursor.fetchone()
        
        if not user_data:
            return redirect('/login')
        
        username = user_data[0]
        user_status = user_data[1]
        avatar = user_data[2] if user_data[2] else "user.png"
        balance = user_data[3] if user_data[3] is not None else 0
        monthly_deposit = user_data[4]
        monthly_withdraw = user_data[5]
        
        # Получаем доступные методы оплаты
        cursor.execute(
            """
            SELECT id, name, type, icon, fee, enabled
            FROM payment_methods
            ORDER BY type, name
            """
        )
        payment_methods = []
        for row in cursor.fetchall():
            payment_methods.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'icon': row[3],
                'fee': row[4],
                'enabled': row[5]
            })
            
        # Получаем историю транзакций пользователя
        cursor.execute(
            """
            SELECT id, user_id, type, amount, fee_amount, payment_method, status, 
                   description, created_at, details
            FROM financial_transactions
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user_id,)
        )
        
        transactions = []
        for row in cursor.fetchall():
            transactions.append({
                'id': row[0],
                'user_id': row[1],
                'type': row[2],
                'amount': row[3],
                'fee_amount': row[4],
                'payment_method': row[5],
                'status': row[6],
                'description': row[7],
                'created_at': row[8].strftime('%d.%m.%Y %H:%M'),
                'details': row[9]
            })
            
        # Получаем количество транзакций
        cursor.execute(
            "SELECT COUNT(*) FROM financial_transactions WHERE user_id = %s",
            (user_id,)
        )
        transactions_count = cursor.fetchone()[0]
        
        return render_template(
            "finances.html",
            username=username,
            user_status=user_status,
            avatar=avatar,
            balance=balance,
            monthly_deposit=monthly_deposit,
            monthly_withdraw=monthly_withdraw,
            payment_methods=payment_methods,
            transactions=transactions,
            transactions_count=transactions_count
        )
    
    except Exception as e:
        print(f"Ошибка при загрузке страницы финансов: {e}")
        return redirect('/')
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@finances_bp.route("/finances/deposit", methods=["POST"])
def deposit():
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect('/login')
    
    try:
        # Преобразуем в Decimal вместо float для точных финансовых расчетов
        amount = Decimal(request.form.get('amount'))
        payment_method_id = request.form.get('payment_method')
        
        # Проверяем минимальную сумму
        if amount < 500:
            flash("Минимальная сумма пополнения - 500 ₽", "error")
            return redirect('/finances')
        
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Получаем данные пользователя
            cursor.execute(
                "SELECT username FROM users WHERE id = %s",
                (user_id,)
            )
            user_data = cursor.fetchone()
            username = user_data[0] if user_data else "Пользователь"
            
            # Получаем информацию о методе оплаты
            cursor.execute(
                "SELECT name, fee, enabled FROM payment_methods WHERE id = %s",
                (payment_method_id,)
            )
            method = cursor.fetchone()
            
            if not method or not method[2]:  # enabled
                flash("Выбранный способ оплаты недоступен", "error")
                return redirect('/finances')
            
            method_name = method[0]
            fee_percentage = method[1]
            
            # Проверяем, является ли метод CryptoBot
            if 'cryptobot' in method_name.lower() or 'crypto bot' in method_name.lower():
                # Рассчитываем комиссию (2.5%)
                fee_amount = amount * Decimal('0.025')
                
                # Создаем уникальный ID транзакции
                transaction_id = str(uuid.uuid4())
                
                # Формируем полезную нагрузку для передачи в callback
                payload = json.dumps({
                    "transaction_id": transaction_id,
                    "user_id": user_id,
                    "amount": str(amount),
                    "fee_amount": str(fee_amount)
                })
                
                # Описание платежа
                description = f"Пополнение баланса на сайте ROXIN - {username} (ID: {user_id})"
                
                if DEMO_MODE:
                    # Демо-режим, перенаправляем на демо-страницу
                    # Сохраняем демо-транзакцию в БД
                    cursor.execute(
                        """
                        INSERT INTO financial_transactions 
                        (id, user_id, type, amount, fee_amount, payment_method, status, description, details)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            transaction_id,
                            user_id,
                            "deposit",
                            float(amount),
                            float(fee_amount),
                            method_name,
                            "pending",
                            description,
                            json.dumps({"demo": True})
                        )
                    )
                    db.commit()
                    
                    # Перенаправляем на демо-страницу
                    return redirect(f"/finances/demo/cryptobot?transaction_id={transaction_id}&amount={amount}&fee={fee_amount}")
                else:
                    # Реальный режим, создаем инвойс в CryptoBot
                    
                    # Переводим сумму из рублей в USDT по примерному курсу
                    # Примерный курс: 1 USDT ≈ 90 RUB
                    usdt_amount = round(float(amount) / 90, 2)
                    
                    # Создаем инвойс через API
                    invoice = cryptobot_client.create_invoice(
                        amount=usdt_amount,
                        description=description,
                        currency="USDT",  # Используем USDT вместо RUB
                        success_url=CRYPTOBOT_SUCCESS_URL,
                        payload=payload
                    )
                    
                    print(f"DEBUG: Создание инвойса CryptoBot: {amount} RUB -> {usdt_amount} USDT")
                    
                    # Если есть ошибка, показываем её
                    if "error" in invoice:
                        flash(f"Ошибка при создании счета: {invoice['error']}", "danger")
                        return redirect("/finances")
                    
                    # Получаем данные об инвойсе
                    # Структура ответа: {"ok":true,"result":{"invoice_id":25899774,"hash":"IVEE1sC4GLXM",...}}
                    result = invoice.get("result", {})
                    invoice_id = result.get("invoice_id", "")
                    invoice_hash = result.get("hash", "")
                    
                    # Создаем формат ссылки для Телеграм
                    # По формату https://t.me/send?start=HASH
                    if invoice_hash:
                        pay_url = f"https://t.me/send?start={invoice_hash}"
                    else:
                        # Запасной вариант - используем любой URL из ответа
                        pay_url = result.get("pay_url", result.get("bot_invoice_url", result.get("web_app_invoice_url", "")))
                    
                    print(f"DEBUG: Извлеченные данные: invoice_id={invoice_id}, hash={invoice_hash}, pay_url={pay_url}")
                    
                    if not pay_url:
                        flash("Ошибка при создании счета в CryptoBot", "danger")
                        return redirect("/finances")
                    
                    # Сохраняем транзакцию в БД
                    cursor.execute(
                        """
                        INSERT INTO financial_transactions 
                        (id, user_id, type, amount, fee_amount, payment_method, status, description, details)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            transaction_id,
                            user_id,
                            "deposit",
                            float(amount),
                            float(fee_amount),
                            method_name,
                            "pending",
                            description,
                            json.dumps({"invoice_id": invoice_id, "pay_url": pay_url, "usdt_amount": usdt_amount})
                        )
                    )
                    db.commit()
                    
                    # Перенаправляем на страницу оплаты CryptoBot
                    print(f"INFO: Перенаправление на URL оплаты: {pay_url}")
                    
                    # Для отладки показываем страницу с кнопкой для перехода
                    return render_template('payment_redirect.html', 
                                           payment_url=pay_url, 
                                           amount=amount,
                                           usdt_amount=usdt_amount,
                                           invoice_id=invoice_id)
            else:
                # Логика для других методов оплаты
                flash("Выбранный способ оплаты временно недоступен", "error")
                return redirect('/finances')
    except Exception as e:
        print(f"Ошибка при пополнении баланса: {e}")
        flash("Произошла ошибка при пополнении баланса", "error")
        return redirect('/finances')


@finances_bp.route("/finances/deposit/success")
def deposit_success():
    """Обработка успешного возврата после оплаты"""
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect('/login')
    
    flash("Спасибо за пополнение! Средства поступят на ваш баланс после подтверждения платежа.", "success")
    return redirect('/finances')


@finances_bp.route("/api/cryptobot/demo/pay")
def cryptobot_demo_payment():
    """Демо-страница для симуляции платежа через CryptoBot"""
    if not DEMO_MODE:
        return redirect('/finances')
    
    invoice_id = request.args.get('invoice_id')
    amount = request.args.get('amount')
    transaction_id = request.args.get('transaction_id')
    user_id = request.args.get('user_id')
    
    if not all([invoice_id, amount, transaction_id, user_id]):
        flash("Некорректные параметры платежа", "error")
        return redirect('/finances')
    
    return render_template(
        "cryptobot_demo.html",
        invoice_id=invoice_id,
        amount=amount,
        transaction_id=transaction_id,
        user_id=user_id
    )

@finances_bp.route("/api/cryptobot/demo/complete", methods=["POST"])
def cryptobot_demo_complete():
    """Обработка демо-платежа через CryptoBot"""
    if not DEMO_MODE:
        return redirect('/finances')
    
    transaction_id = request.form.get('transaction_id')
    user_id = request.form.get('user_id')
    amount = request.form.get('amount')
    
    if not all([transaction_id, user_id, amount]):
        flash("Некорректные параметры платежа", "error")
        return redirect('/finances')
    
    try:
        amount = Decimal(amount)
        
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, существует ли транзакция
            cursor.execute(
                "SELECT status, fee_amount FROM financial_transactions WHERE id = %s",
                (transaction_id,)
            )
            transaction = cursor.fetchone()
            
            if not transaction:
                flash("Транзакция не найдена", "error")
                return redirect('/finances')
            
            # Если транзакция уже обработана, возвращаем на страницу финансов
            if transaction[0] == "completed":
                flash("Платеж уже был обработан", "success")
                return redirect('/finances')
            
            fee_amount = transaction[1]
            
            # Обновляем статус транзакции
            cursor.execute(
                "UPDATE financial_transactions SET status = 'completed', updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), transaction_id)
            )
            
            # Обновляем баланс пользователя
            cursor.execute(
                """
                UPDATE user_profiles 
                SET balance = balance + %s,
                    monthly_deposit = monthly_deposit + %s
                WHERE user_id = %s
                """,
                (amount - fee_amount, amount, user_id)
            )
            
            # Создаем уведомление для пользователя
            cursor.execute(
                """
                INSERT INTO user_notifications 
                (user_id, title, message, severity, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    "Успешное пополнение баланса",
                    f"Ваш баланс успешно пополнен на {amount - fee_amount} ₽ через CryptoBot (ДЕМО)",
                    "info",
                    False,
                    datetime.now(timezone.utc)
                )
            )
            
            db.commit()
        
        flash(f"Баланс успешно пополнен на {amount - fee_amount} ₽ (ДЕМО)", "success")
        return redirect('/finances')
    
    except Exception as e:
        print(f"Ошибка при обработке демо-платежа: {e}")
        flash("Произошла ошибка при обработке платежа", "error")
        return redirect('/finances')

# Тестовый маршрут для эмуляции webhook от CryptoBot
@finances_bp.route("/api/cryptobot/test-webhook", methods=["GET"])
def cryptobot_test_webhook():
    """Эмуляция webhook от CryptoBot для тестирования
    
    Параметры URL:
    - transaction_id: ID транзакции, которую нужно обработать
    
    Пример: /api/cryptobot/test-webhook?transaction_id=your_transaction_id
    """
    transaction_id = request.args.get('transaction_id')
    
    if not transaction_id:
        return jsonify({
            "success": False,
            "error": "Отсутствует обязательный параметр 'transaction_id'"
        }), 400
    
    try:
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, существует ли транзакция
            cursor.execute(
                """
                SELECT ft.id, ft.user_id, ft.amount, ft.fee_amount, ft.status, ft.details,
                       u.username
                FROM financial_transactions ft
                JOIN users u ON ft.user_id = u.id
                WHERE ft.id = %s
                """,
                (transaction_id,)
            )
            transaction = cursor.fetchone()
            
            if not transaction:
                return jsonify({
                    "success": False,
                    "error": "Транзакция не найдена"
                }), 404
            
            # Получаем данные транзакции
            trans_id, user_id, amount, fee_amount, status, details_json, username = transaction
            
            # Если транзакция уже завершена, возвращаем успех
            if status == "completed":
                return jsonify({
                    "success": True,
                    "message": "Транзакция уже была обработана",
                    "transaction": {
                        "id": trans_id,
                        "user_id": user_id,
                        "amount": float(amount),
                        "username": username
                    }
                })
            
            # Обновляем статус транзакции
            cursor.execute(
                "UPDATE financial_transactions SET status = 'completed', updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), transaction_id)
            )
            
            # Обновляем баланс пользователя
            cursor.execute(
                """
                UPDATE user_profiles 
                SET balance = balance + %s,
                    monthly_deposit = monthly_deposit + %s
                WHERE user_id = %s
                """,
                (amount - fee_amount, amount, user_id)
            )
            
            # Создаем уведомление для пользователя
            cursor.execute(
                """
                INSERT INTO user_notifications 
                (user_id, title, message, severity, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    "Успешное пополнение баланса",
                    f"Ваш баланс успешно пополнен на {amount - fee_amount} ₽ через CryptoBot (Тестовый режим)",
                    "info",
                    False,
                    datetime.now(timezone.utc)
                )
            )
            
            db.commit()
            
            return jsonify({
                "success": True,
                "message": "Транзакция успешно обработана",
                "transaction": {
                    "id": trans_id,
                    "user_id": user_id,
                    "amount": float(amount),
                    "fee_amount": float(fee_amount),
                    "net_amount": float(amount - fee_amount),
                    "username": username
                }
            })
    
    except Exception as e:
        print(f"Ошибка при обработке тестового webhook: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Обработка уведомлений от CryptoBot
@finances_bp.route("/api/cryptobot/callback", methods=["POST"])
def cryptobot_callback():
    """Обработка уведомлений от CryptoBot"""
    try:
        # Получаем данные запроса
        callback_data = request.get_data(as_text=True)
        signature = request.headers.get('Crypto-Pay-API-Signature')
        
        # Проверяем подпись (только если не в демо-режиме)
        if not DEMO_MODE and not cryptobot_client.verify_callback(callback_data, signature):
            return jsonify({"error": "Invalid signature"}), 400
        
        data = json.loads(callback_data)
        
        # Проверяем, что это обновление invoice
        if data.get("update_type") != "invoice_paid":
            return jsonify({"status": "ok"})
        
        invoice = data.get("payload", {})
        invoice_id = invoice.get("invoice_id")
        
        if not invoice_id:
            return jsonify({"error": "Invalid payload"}), 400
        
        # Получаем payload, который мы передали при создании invoice
        custom_payload = invoice.get("payload")
        if not custom_payload:
            return jsonify({"error": "Missing payload"}), 400
        
        try:
            payload_data = json.loads(custom_payload)
            transaction_id = payload_data.get("transaction_id")
            user_id = payload_data.get("user_id")
            amount = Decimal(payload_data.get("amount"))
            fee_amount = Decimal(payload_data.get("fee_amount"))
        except Exception as e:
            return jsonify({"error": f"Invalid payload format: {str(e)}"}), 400
        
        with DatabaseConnection() as db:
            cursor = db.cursor()
            
            # Проверяем, существует ли транзакция
            cursor.execute(
                "SELECT status FROM financial_transactions WHERE id = %s",
                (transaction_id,)
            )
            transaction = cursor.fetchone()
            
            if not transaction:
                return jsonify({"error": "Transaction not found"}), 404
            
            # Если транзакция уже обработана, возвращаем успех
            if transaction[0] == "completed":
                return jsonify({"status": "ok"})
            
            # Обновляем статус транзакции
            cursor.execute(
                "UPDATE financial_transactions SET status = 'completed', updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), transaction_id)
            )
            
            # Обновляем баланс пользователя
            cursor.execute(
                """
                UPDATE user_profiles 
                SET balance = balance + %s,
                    monthly_deposit = monthly_deposit + %s
                WHERE user_id = %s
                """,
                (amount - fee_amount, amount, user_id)
            )
            
            # Создаем уведомление для пользователя
            cursor.execute(
                """
                INSERT INTO user_notifications 
                (user_id, title, message, severity, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    "Успешное пополнение баланса",
                    f"Ваш баланс успешно пополнен на {amount - fee_amount} ₽ через CryptoBot",
                    "info",
                    False,
                    datetime.now(timezone.utc)
                )
            )
            
            db.commit()
        
        return jsonify({"status": "ok"})
    
    except Exception as e:
        print(f"Ошибка при обработке webhook от CryptoBot: {e}")
        return jsonify({"error": str(e)}), 500

@finances_bp.route("/finances/withdraw", methods=["POST"])
def withdraw():
    user_id = request.cookies.get("user_id")
    if not user_id:
        return redirect('/login')
    
    try:
        # Преобразуем в Decimal вместо float для точных финансовых расчетов
        amount = Decimal(request.form.get('amount'))
        payment_method_id = request.form.get('payment_method')
        details = request.form.get('details')
        
        # Проверяем минимальную сумму
        if amount < 500:
            flash("Минимальная сумма вывода - 500 ₽", "error")
            return redirect('/finances')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем баланс пользователя
        cursor.execute(
            "SELECT balance FROM user_profiles WHERE user_id = %s",
            (user_id,)
        )
        balance = cursor.fetchone()
        
        if not balance or balance[0] < amount:
            flash("Недостаточно средств для вывода", "error")
            return redirect('/finances')
        
        # Получаем информацию о методе вывода
        cursor.execute(
            "SELECT name, fee, enabled FROM payment_methods WHERE id = %s",
            (payment_method_id,)
        )
        method = cursor.fetchone()
        
        if not method or not method[2]:  # enabled
            flash("Выбранный способ вывода недоступен", "error")
            return redirect('/finances')
        
        method_name = method[0]
        fee_percentage = method[1]
        
        # Преобразуем fee_percentage в Decimal и рассчитываем комиссию
        fee_percentage_decimal = Decimal(str(fee_percentage))
        fee_amount = amount * (fee_percentage_decimal / Decimal('100'))
        net_amount = amount - fee_amount
        
        # Создаем запись о транзакции
        transaction_id = str(uuid.uuid4())
        
        cursor.execute(
            """
            INSERT INTO financial_transactions 
            (id, user_id, type, amount, fee_amount, payment_method, status, description, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                transaction_id,
                user_id,
                "withdraw",
                amount,
                fee_amount,
                method_name,
                "pending",
                f"Вывод через {method_name}",
                details
            )
        )
        
        # Обновляем баланс пользователя
        cursor.execute(
            """
            UPDATE user_profiles 
            SET balance = balance - %s,
                monthly_withdraw = monthly_withdraw + %s
            WHERE user_id = %s
            """,
            (amount, amount, user_id)
        )
        
        # В реальной системе здесь был бы код ручной проверки и подтверждения вывода
        # Для демонстрации создаем запись для администратора о необходимости проверки
        
        cursor.execute(
            """
            INSERT INTO admin_notifications 
            (title, message, severity, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (
                "Новый запрос на вывод средств",
                f"Пользователь (ID: {user_id}) запросил вывод {amount} ₽ через {method_name}. \n"
                f"Транзакция: {transaction_id}\n"
                f"Реквизиты: {details}\n"
                f"Требуется проверка.",
                "warning",
                datetime.now(timezone.utc)
            )
        )
        
        conn.commit()
        
        flash(f"Запрос на вывод {net_amount} ₽ успешно создан и ожидает проверки", "success")
        return redirect('/finances')
    
    except Exception as e:
        print(f"Ошибка при выводе средств: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
        flash("Произошла ошибка при выводе средств", "error")
        return redirect('/finances')
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()
