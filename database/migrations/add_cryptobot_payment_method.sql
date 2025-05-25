-- Добавляем метод оплаты CryptoBot в таблицу payment_methods
INSERT INTO payment_methods (id, name, type, icon, fee, enabled)
VALUES (
    gen_random_uuid(), -- Генерируем UUID
    'CryptoBot', 
    'deposit', 
    'credit-card', -- Используем соответствующую иконку
    2.0, -- 2% комиссии
    true -- Активен
)
ON CONFLICT (name, type) DO UPDATE
SET icon = 'credit-card',
    fee = 2.0,
    enabled = true;
