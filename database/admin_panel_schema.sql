-- Схема базы данных для админ-панели

-- Таблица для хранения логов системы
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(10) NOT NULL, -- INFO, WARNING, ERROR, CRITICAL
    source VARCHAR(50) NOT NULL, -- Источник лога: auth, orders, users и т.д.
    message TEXT NOT NULL,
    details JSONB, -- Дополнительные детали в формате JSON
    ip_address VARCHAR(45), -- IPv4 или IPv6
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска по логам
CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_source ON system_logs(source);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON system_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_user_id ON system_logs(user_id);

-- Таблица для отслеживания действий администраторов
CREATE TABLE IF NOT EXISTS admin_actions (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL, -- user_create, user_update, user_delete, etc.
    entity_type VARCHAR(50) NOT NULL, -- user, order, etc.
    entity_id INTEGER,
    old_data JSONB, -- Предыдущие данные в формате JSON
    new_data JSONB, -- Новые данные в формате JSON
    ip_address VARCHAR(45), -- IPv4 или IPv6
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска действий администраторов
CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_id ON admin_actions(admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_actions_action_type ON admin_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_admin_actions_entity_type ON admin_actions(entity_type);
CREATE INDEX IF NOT EXISTS idx_admin_actions_created_at ON admin_actions(created_at);

-- Таблица статистики системы
CREATE TABLE IF NOT EXISTS system_stats (
    id SERIAL PRIMARY KEY,
    stat_date DATE NOT NULL,
    total_users INTEGER NOT NULL DEFAULT 0,
    total_orders INTEGER NOT NULL DEFAULT 0,
    new_users INTEGER NOT NULL DEFAULT 0,
    new_orders INTEGER NOT NULL DEFAULT 0,
    completed_orders INTEGER NOT NULL DEFAULT 0,
    avg_completion_time INTERVAL,
    revenue DECIMAL(12,2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stat_date)
);

-- Таблица уведомлений для админов
CREATE TABLE IF NOT EXISTS admin_notifications (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL, -- info, warning, error
    is_read BOOLEAN DEFAULT FALSE,
    admin_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрого поиска непрочитанных уведомлений
CREATE INDEX IF NOT EXISTS idx_admin_notifications_unread ON admin_notifications(admin_id, is_read) WHERE is_read = FALSE;

-- Таблица для уведомлений пользователей
CREATE TABLE IF NOT EXISTS user_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_id
        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- Индекс для быстрого поиска уведомлений по пользователю
CREATE INDEX IF NOT EXISTS idx_user_notifications_user_id ON user_notifications(user_id);
