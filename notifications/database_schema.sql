-- Таблица для хранения профилей Telegram
CREATE TABLE IF NOT EXISTS telegram_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL UNIQUE,
    telegram_username VARCHAR(255),
    telegram_first_name VARCHAR(255),
    telegram_last_name VARCHAR(255),
    notifications_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица для временных токенов привязки Telegram
CREATE TABLE IF NOT EXISTS telegram_tokens (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица для логов уведомлений
CREATE TABLE IF NOT EXISTS notification_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS telegram_profiles_telegram_id_idx ON telegram_profiles(telegram_id);
CREATE INDEX IF NOT EXISTS telegram_tokens_token_idx ON telegram_tokens(token);
CREATE INDEX IF NOT EXISTS notification_log_user_id_idx ON notification_log(user_id);
CREATE INDEX IF NOT EXISTS notification_log_created_at_idx ON notification_log(created_at);