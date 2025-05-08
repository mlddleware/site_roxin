from database.connection import get_db_connection

def create_finance_tables():
    """
    Создает необходимые таблицы для финансовой системы:
    - payment_methods: методы оплаты для пополнения и вывода
    - financial_transactions: история финансовых операций
    - Обновляет таблицу user_profiles, добавляя поля для финансовой статистики
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Обновление таблицы user_profiles, добавление полей для финансов
        cursor.execute("""
        ALTER TABLE user_profiles 
        ADD COLUMN IF NOT EXISTS balance DECIMAL(15,2) DEFAULT 0.00,
        ADD COLUMN IF NOT EXISTS monthly_deposit DECIMAL(15,2) DEFAULT 0.00,
        ADD COLUMN IF NOT EXISTS monthly_withdraw DECIMAL(15,2) DEFAULT 0.00,
        ADD COLUMN IF NOT EXISTS total_earnings DECIMAL(15,2) DEFAULT 0.00,
        ADD COLUMN IF NOT EXISTS total_spent DECIMAL(15,2) DEFAULT 0.00;
        """)
        
        # Создание таблицы методов оплаты
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_methods (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(20) NOT NULL, -- 'deposit', 'withdraw' или 'both'
            icon VARCHAR(50) NOT NULL,
            description TEXT,
            fee DECIMAL(5,2) DEFAULT 0.00, -- комиссия в процентах
            min_amount DECIMAL(10,2) DEFAULT 0.00,
            max_amount DECIMAL(15,2) DEFAULT 0.00,
            enabled BOOLEAN DEFAULT TRUE,
            priority INT DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Создание таблицы финансовых транзакций
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_transactions (
            id VARCHAR(36) PRIMARY KEY, -- UUID
            user_id VARCHAR(36) NOT NULL,
            type VARCHAR(20) NOT NULL, -- 'deposit', 'withdraw', 'order_payment', 'order_refund', 'order_completion'
            amount DECIMAL(15,2) NOT NULL,
            fee_amount DECIMAL(15,2) DEFAULT 0.00,
            payment_method VARCHAR(100),
            status VARCHAR(20) NOT NULL, -- 'pending', 'completed', 'failed', 'cancelled'
            description TEXT,
            details TEXT, -- Дополнительные детали (например, реквизиты для вывода)
            related_entity_id VARCHAR(36), -- ID связанного заказа или другой сущности
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Создание индексов для быстрого поиска
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_financial_transactions_user_id ON financial_transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_financial_transactions_type ON financial_transactions(type);
        CREATE INDEX IF NOT EXISTS idx_financial_transactions_status ON financial_transactions(status);
        CREATE INDEX IF NOT EXISTS idx_financial_transactions_created_at ON financial_transactions(created_at);
        """)
        
        # Вставка базовых методов оплаты, если их еще нет
        cursor.execute("SELECT COUNT(*) FROM payment_methods")
        count = cursor.fetchone()[0]
        
        if count == 0:
            payment_methods = [
                # Методы пополнения
                ("Банковская карта", "deposit", "credit-card", "Visa, MasterCard, МИР", 2.5, 100, 100000, True, 10),
                ("ЮMoney", "deposit", "wallet", "Электронный кошелек ЮMoney", 3.0, 100, 50000, True, 20),
                ("СБП", "deposit", "bank", "Система быстрых платежей", 1.0, 100, 500000, True, 15),
                ("Криптовалюта", "deposit", "bitcoin", "Bitcoin, Ethereum, USDT, TON", 1.5, 1000, 1000000, True, 30),
                
                # Методы вывода
                ("Банковская карта", "withdraw", "credit-card", "Visa, MasterCard, МИР", 3.0, 500, 100000, True, 10),
                ("ЮMoney", "withdraw", "wallet", "Электронный кошелек ЮMoney", 2.5, 500, 50000, True, 20),
                ("СБП", "withdraw", "bank", "Система быстрых платежей", 1.5, 500, 500000, True, 15),
                ("Криптовалюта", "withdraw", "bitcoin", "Bitcoin, Ethereum, USDT, TON", 1.0, 1000, 1000000, True, 30),
            ]
            
            for method in payment_methods:
                cursor.execute("""
                INSERT INTO payment_methods 
                (name, type, icon, description, fee, min_amount, max_amount, enabled, priority)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, method)
        
        conn.commit()
        print("Финансовые таблицы успешно созданы")
        
    except Exception as e:
        print(f"Ошибка при создании финансовых таблиц: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    create_finance_tables()
