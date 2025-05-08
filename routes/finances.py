from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from database.connection import get_db_connection
from datetime import datetime, timezone
import uuid
import decimal
from decimal import Decimal

finances_bp = Blueprint('finances', __name__)

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
        if amount < 100:
            flash("Минимальная сумма пополнения - 100 ₽", "error")
            return redirect('/finances')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        # Преобразуем fee_percentage в Decimal и рассчитываем комиссию
        fee_percentage_decimal = Decimal(str(fee_percentage))
        fee_amount = amount * (fee_percentage_decimal / Decimal('100'))
        
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
                "deposit",
                amount,
                fee_amount,
                method_name,
                "pending",
                f"Пополнение через {method_name}",
                ""
            )
        )
        
        # В реальной системе здесь был бы код для интеграции с платежным шлюзом
        # Для демонстрации сразу подтверждаем транзакцию
        
        # Обновляем транзакцию
        cursor.execute(
            "UPDATE financial_transactions SET status = 'completed' WHERE id = %s",
            (transaction_id,)
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
        
        conn.commit()
        
        flash(f"Баланс успешно пополнен на {amount - fee_amount} ₽", "success")
        return redirect('/finances')
    
    except Exception as e:
        print(f"Ошибка при пополнении баланса: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
        flash("Произошла ошибка при пополнении баланса", "error")
        return redirect('/finances')
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

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
