-- Скрипт для создания таблицы восстановления паролей

-- Проверяем, существует ли таблица, если нет - создаем
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Создаем индекс для быстрого поиска по токену
CREATE INDEX IF NOT EXISTS idx_password_reset_token ON password_reset_tokens(token);

-- Добавляем уникальный индекс для предотвращения дублирования токенов
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_token ON password_reset_tokens(token) WHERE used = FALSE;
