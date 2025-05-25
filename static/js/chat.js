console.log("Загрузка chat.js...");

// Единое соединение WebSocket
let socket;
let currentChatUserId = null;

// Глобальные переменные для отслеживания состояния
let activeRequest = null;
let lastSelectedUserId = null;
let currentUserName = null; // Имя текущего пользователя для определения своих сообщений

// Глобальные переменные для отслеживания ответов
let currentReplyTo = null; // ID сообщения, на которое отвечаем
let messageIdCounter = 1; // Счетчик для уникальных ID сообщений

// Функция для очистки HTML (защита от XSS)
function sanitizeHTML(text) {
    if (!text) return '';
    return text.toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Функции, которые нужно вызывать извне DOMContentLoaded
let openChatByIdImpl = null;

function openChatById(chatId) {
    if (openChatByIdImpl) {
        openChatByIdImpl(chatId);
    } else {
        // Если DOM ещё не загружен, сохраняем ID для последующего открытия
        window.pendingChatId = chatId;
    }
}

// Улучшенный кэш с управлением временем жизни
const chatCache = {
    data: {},
    maxAge: {
        messages: 30000,    // 30 секунд для сообщений
        user: 300000,       // 5 минут для данных пользователя
        chatId: 3600000     // 1 час для ID чатов
    },
    
    get(key) {
        const item = this.data[key];
        if (!item) return null;
        if (Date.now() - item.timestamp > this.getMaxAge(key)) {
            delete this.data[key];
            return null;
        }
        return item.value;
    },
    
    set(key, value) {
        this.data[key] = {
            value,
            timestamp: Date.now()
        };
    },
    
    getMaxAge(key) {
        if (key.startsWith('messages_')) return this.maxAge.messages;
        if (key.startsWith('userData_')) return this.maxAge.user;
        if (key.startsWith('chatId_')) return this.maxAge.chatId;
        return this.maxAge.messages;
    },
    
    invalidate(key) {
        delete this.data[key];
    }
};

// Инициализация сокета
if (typeof io === "undefined") {
    console.error("❌ Ошибка: io() не определён! Проверь загрузку socket.io.js.");
} else {
    socket = io(window.location.origin, { transports: ["websocket"] });
    
    socket.on("connect", () => {
        console.log("🔗 Подключено к WebSocket!");
    });

    socket.on("disconnect", () => {
        console.log("❌ WebSocket отключён!");
    });
}

// Функция воспроизведения звука уведомлений
function requestNotificationSound() {
    const audio = new Audio("/static/sounds/notification.mp3");

    if (document.hidden) {
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                audio.play().catch(error => console.warn("Ошибка воспроизведения звука:", error));
            }
        }, { once: true });
    } else {
        audio.play().catch(error => console.warn("Ошибка воспроизведения звука:", error));
    }
}

// Обработчик события openChatById
window.addEventListener('openChatById', function(e) {
    const chatId = e.detail.chatId;
    if (chatId) {
        openChatById(chatId);
    }
});

document.addEventListener("DOMContentLoaded", () => {
    const pathParts = window.location.pathname.split("/");
    const chatListElement = document.getElementById("chatList");
    const messagesContainer = document.getElementById("messagesContainer");
    const messageInput = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    const chatHeader = document.getElementById("chatHeader");
    const chatName = document.getElementById("chatName");
    const chatAvatar = document.getElementById("chatAvatar");
    const onlineStatus = document.getElementById("onlineStatus");
    const statusDot = document.getElementById("statusDot");
    const messageInputContainer = document.getElementById("messageInputContainer");
    
    // Мобильная навигация
    const navChats = document.getElementById("navChats");
    const navChat = document.getElementById("navChat");
    const chatSidebar = document.getElementById("chatSidebar");

    // Реализуем функцию openChatById
    openChatByIdImpl = function(chatId) {
        fetch(`/chat/info/${chatId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.warn(`⚠️ Ошибка: ${data.error}`);
                window.history.pushState({}, "", "/chat"); // Если чата нет — редирект
                return;
            }
    
            // Показываем заголовок чата и поле ввода
            chatHeader.style.display = 'flex';
            messageInputContainer.style.display = 'block';
            
            // Обновляем заголовок, аватар и статус онлайн
            chatName.textContent = data.username;
            if (chatAvatar) {
                chatAvatar.src = data.avatar || "/static/images/user.png";
            }
            
            // Обновляем статус онлайн
            if (onlineStatus) {
                onlineStatus.textContent = data.online_status;
                // Добавляем класс для онлайн-статуса
                if (data.online_status === "Онлайн") {
                    statusDot.classList.remove('offline');
                } else {
                    statusDot.classList.add('offline');
                }
            }
            
            // Сохраняем данные пользователя в кэш
            chatCache.set(`userData_${data.user_id}`, data);
    
            // Загружаем сообщения
            loadChatMessages(data.user_id);
    
            // Устанавливаем текущий ID чата
            currentChatUserId = data.user_id;
            lastSelectedUserId = data.user_id;
        })
        .catch(error => console.error("❌ Ошибка загрузки чата:", error));
    };

    // Проверяем, был ли запрос на открытие чата до загрузки DOM
    if (window.pendingChatId) {
        openChatByIdImpl(window.pendingChatId);
        delete window.pendingChatId;
    }
    
    // Показать приветственное сообщение
    function showWelcomeMessage() {
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i data-lucide="message-circle"></i>
                </div>
                <h2 class="welcome-title">Выберите диалог</h2>
                <p class="welcome-subtitle">Начните общение с коллегами и клиентами</p>
            </div>
        `;
        // Переинициализируем иконки Lucide
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
    
    // Загрузка списка чатов с кэшированием
    function loadChatList() {
        const cacheKey = 'chatList';
        const cachedData = chatCache.get(cacheKey);
        
        if (cachedData) {
            console.log("📋 Список чатов получен из кэша");
            displayChatList(cachedData);
            return;
        }

        console.log("📋 Загружаем список чатов...");
        fetch("/chat/list")
            .then(response => response.json())
            .then(chats => {
                chatCache.set(cacheKey, chats);
                displayChatList(chats);
                prefetchFirstChats(chats);
            })
            .catch(error => {
                console.error("❌ Ошибка загрузки списка чатов:", error);
                chatListElement.innerHTML = '<div class="error-message">Ошибка загрузки чатов</div>';
            });
    }

    function displayChatList(chats) {
        if (!chatListElement) return;

        if (chats.length === 0) {
            chatListElement.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="message-circle"></i>
                    <p>Нет активных чатов</p>
                </div>
                    `;
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
            return;
        }

        chatListElement.innerHTML = chats.map(chat => `
            <div class="chat-item" onclick="selectChat(${chat.user_id}, '${sanitizeHTML(chat.username)}', '${chat.avatar}')">
                <img src="${chat.avatar}" alt="${sanitizeHTML(chat.username)}" class="chat-avatar">
                <div class="chat-info">
                    <div class="chat-name">${sanitizeHTML(chat.username)}</div>
                    <div class="chat-last-message">${chat.last_message ? sanitizeHTML(chat.last_message) : 'Нет сообщений'}</div>
                </div>
                <div class="chat-meta">
                    <div class="chat-time">${chat.last_message_date || ''}</div>
                </div>
            </div>
        `).join('');
    }

    // Предзагрузка первых нескольких чатов
    function prefetchFirstChats(chats) {
        const topChats = chats.slice(0, 3);
        topChats.forEach(chat => {
            prefetchChatData(chat.user_id);
        });
    }
    
    // Предзагрузка данных чата
    function prefetchChatData(userId) {
        // Если данных еще нет в кэше, загружаем их
        if (!chatCache.get(`userData_${userId}`)) {
            fetch(`/chat/user/${userId}`)
                .then(response => response.json())
                .then(data => {
                    chatCache.set(`userData_${userId}`, data);
                })
                .catch(() => {});
        }
    }

    // Выбор чата
    function selectChat(userId, username, avatar) {
        console.log(`💬 Открываем чат с пользователем ${username} (ID: ${userId})`);
    
        // Отменяем предыдущий запрос, если он есть
        if (activeRequest) {
            activeRequest.abort();
        }

        // Обновляем активный элемент списка
        document.querySelectorAll('.chat-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');
    
        // Показываем заголовок чата и поле ввода
        chatHeader.style.display = 'flex';
        messageInputContainer.style.display = 'block';
    
        // Обновляем заголовок и аватар
        chatName.textContent = username;
        if (chatAvatar) {
            chatAvatar.src = avatar || "/static/images/user.png";
        }
        
        // На мобильных устройствах скрываем боковую панель
        if (window.innerWidth <= 768) {
            chatSidebar.classList.remove('mobile-active');
            navChat.classList.add('active');
            navChats.classList.remove('active');
        }
        
        // Создаем новый AbortController для текущего запроса
        const controller = new AbortController();
        activeRequest = controller;
        
        // Загружаем информацию о пользователе
        loadUserInfo(userId)
            .then(() => {
                // Загружаем сообщения
                return loadChatMessages(userId);
            })
            .then(() => {
                currentChatUserId = userId;
                lastSelectedUserId = userId;
                
                // Обновляем URL
                const newUrl = `/chat/${userId}`;
                if (window.location.pathname !== newUrl) {
                    window.history.pushState({}, '', newUrl);
                }
                
                activeRequest = null;
            })
            .catch(error => {
                if (error.name !== 'AbortError') {
                    console.error("❌ Ошибка при выборе чата:", error);
                }
                activeRequest = null;
            });
    }

    // Загрузка сообщений чата
    function loadChatMessages(userId) {
        const cacheKey = `messages_${userId}`;
        const cachedMessages = chatCache.get(cacheKey);
        
        if (cachedMessages) {
            console.log(`💬 Сообщения для пользователя ${userId} получены из кэша`);
            displayMessages(cachedMessages);
            return Promise.resolve();
        }

        console.log(`💬 Загружаем сообщения для пользователя ${userId}...`);
        
        return fetch(`/chat/messages/${userId}`, {
            signal: activeRequest?.signal
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
            .then(messages => {
            chatCache.set(cacheKey, messages);
            displayMessages(messages);
            })
            .catch(error => {
            if (error.name !== 'AbortError') {
                console.error(`❌ Ошибка загрузки сообщений для пользователя ${userId}:`, error);
                messagesContainer.innerHTML = '<div class="error-message">Ошибка загрузки сообщений</div>';
            }
            throw error;
        });
    }

    function displayMessages(messages) {
        if (!messagesContainer) return;

        if (messages.length === 0) {
            messagesContainer.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">
                        <i data-lucide="message-circle"></i>
                    </div>
                    <h2 class="welcome-title">Начните беседу</h2>
                    <p class="welcome-subtitle">Отправьте первое сообщение</p>
                </div>
            `;
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
        }
            return;
        }

        messagesContainer.innerHTML = messages.map(msg => `
            <div class="message ${msg.is_mine ? 'sent' : 'received'}">
                <div class="message-bubble">
                    <div class="message-header">
                        <span class="message-sender">${sanitizeHTML(msg.sender)}</span>
                        <span class="message-time">${msg.timestamp}</span>
                    </div>
                    <div class="message-text">${sanitizeHTML(msg.message)}</div>
                </div>
            </div>
        `).join('');

            scrollToBottom();
        }
        
    // Обработка новых сообщений через WebSocket
    function handleNewMessage(data) {
        console.log("📨 Получено новое сообщение:", data);
        
        // Инвалидируем кэш сообщений для обоих пользователей
        chatCache.invalidate(`messages_${data.sender_id}`);
        chatCache.invalidate(`messages_${data.recipient_id}`);
        
        // Если это сообщение в активном чате, добавляем его
        if (currentChatUserId === data.sender_id || currentChatUserId === data.recipient_id) {
            const isMyMessage = data.sender_id.toString() === getCookie('user_id');
            appendMessage(data.sender, data.message, new Date().toLocaleString(), null, data.message_id, isMyMessage);
        }
        
        // Обновляем список чатов
        updateChatList(data.sender_id, data.recipient_id, data.message);
        
        // Воспроизводим звук уведомления
        requestNotificationSound();
    }

    // Добавление сообщения в интерфейс
    function appendMessage(sender, text, timestamp, replyTo = null, messageId = null, isMyMessage = false) {
        if (!messagesContainer) return;
        
        // Удаляем приветственное сообщение если есть
        const welcomeMessage = messagesContainer.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.remove();
        }

        const messageElement = document.createElement('div');
        messageElement.className = `message ${isMyMessage ? 'sent' : 'received'}`;
        messageElement.innerHTML = `
            <div class="message-bubble">
                <div class="message-header">
                    <span class="message-sender">${sanitizeHTML(sender)}</span>
                    <span class="message-time">${timestamp}</span>
            </div>
                <div class="message-text">${sanitizeHTML(text)}</div>
        </div>
    `;
    
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }
    
    // Загрузка информации о пользователе
    function loadUserInfo(userId) {
        const cacheKey = `userData_${userId}`;
        const cachedData = chatCache.get(cacheKey);
        
        if (cachedData) {
            updateUserStatus(cachedData.online_status);
            return Promise.resolve();
}

    return fetch(`/chat/user/${userId}`)
        .then(response => response.json())
        .then(data => {
                chatCache.set(cacheKey, data);
                updateUserStatus(data.online_status);
            })
            .catch(error => {
                console.error("❌ Ошибка загрузки информации о пользователе:", error);
            });
    }

    function updateUserStatus(status) {
        if (onlineStatus) {
            onlineStatus.textContent = status;
            if (status === "Онлайн") {
                statusDot.classList.remove('offline');
            } else {
                statusDot.classList.add('offline');
            }
        }
}

    // Отправка сообщения
function sendMessage() {
    const messageText = messageInput.value.trim();
    if (!messageText || !currentChatUserId) return;

        console.log(`📤 Отправляем сообщение пользователю ${currentChatUserId}: ${messageText}`);

        const messageData = {
        user_id: currentChatUserId,
            message: messageText,
            message_id: messageIdCounter++
        };

        // Отправляем через WebSocket
        if (socket && socket.connected) {
            socket.emit("send_message", messageData);
        } else {
            console.warn("⚠️ WebSocket не подключён, отправляем через API...");
            fetch("/chat/send", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(messageData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error("❌ Ошибка отправки сообщения:", data.error);
                } else {
                    console.log("✅ Сообщение отправлено через API");
                }
            })
            .catch(error => console.error("❌ Ошибка API:", error));
        }

        // Очищаем поле ввода
        messageInput.value = '';
        messageInput.style.height = 'auto';
        sendBtn.disabled = true;

        // Инвалидируем кэш сообщений
        chatCache.invalidate(`messages_${currentChatUserId}`);
    }

    // Обновление списка чатов после нового сообщения
function updateChatList(senderId, recipientId, message) {
        const chatItems = document.querySelectorAll('.chat-item');
    chatItems.forEach(item => {
            const userId = item.getAttribute('onclick')?.match(/selectChat\((\d+)/)?.[1];
            if (userId && (userId === senderId.toString() || userId === recipientId.toString())) {
                const lastMessageElement = item.querySelector('.chat-last-message');
                const timeElement = item.querySelector('.chat-time');
                if (lastMessageElement) {
                    lastMessageElement.textContent = message.length > 30 ? message.substring(0, 30) + '...' : message;
                }
            if (timeElement) {
                    timeElement.textContent = new Date().toLocaleTimeString().slice(0, 5);
            }
                // Перемещаем чат наверх списка
                item.parentNode.insertBefore(item, item.parentNode.firstChild);
        }
    });
}

    // Вспомогательные функции
    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
}

    function formatDateTime(isoDate) {
        const date = new Date(isoDate);
        return date.toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }

    // Инициализация
    loadChatList();
    showWelcomeMessage();

    // Обработчики событий
    if (sendBtn) {
        sendBtn.addEventListener('click', sendMessage);
    }

    if (messageInput) {
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
        sendMessage();
    }
        });

        messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
            sendBtn.disabled = !this.value.trim();
        });
    }
    
    // WebSocket обработчики
    if (socket) {
        socket.on("new_message", handleNewMessage);
}

    // Глобальная функция для вызова из HTML
    window.selectChat = selectChat;

    console.log("✅ Chat.js успешно загружен!");
});