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
    const sendMessageBtn = document.getElementById("sendMessageBtn");
    const userInfo = document.getElementById("userInfo");
    const profileName = document.getElementById("profileName");
    const profileAvatar = document.getElementById("profileAvatar");
    const activeChatTitle = document.getElementById("activeChatTitle");
    const chatAvatar = document.getElementById("chatAvatar");
    const mainChat = document.getElementById("mainChat");
    const sidebar = document.getElementById("sidebar");
    const profileSidebar = document.getElementById("profileSidebar");
    const messageInputContainer = document.querySelector(".message-input");
    
    // Мобильная навигация
    const showChats = document.getElementById("showChats");
    const showMessages = document.getElementById("showMessages");
    const showProfile = document.getElementById("showProfile");
    const backButton = document.getElementById("backButton");

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
    
            // Показываем UI чата
            mainChat.classList.add('active');
            
            // Активируем поле ввода сообщений
            messageInputContainer.classList.add('active');
            
            // На десктопе также показываем профиль
            if (window.innerWidth >= 768) {
                profileSidebar.classList.add('active');
            }
            
            // Обновляем заголовок, аватар и статус онлайн
            activeChatTitle.textContent = data.username;
            if (chatAvatar) {
                chatAvatar.src = data.avatar || "/static/images/user.png";
            }
            
            // Обновляем статус онлайн
            const onlineStatus = document.querySelector('.online-status');
            if (onlineStatus) {
                onlineStatus.textContent = data.online_status;
                // Добавляем класс для онлайн-статуса
                if (data.online_status === "Онлайн") {
                    onlineStatus.classList.add('status-online');
                } else {
                    onlineStatus.classList.remove('status-online');
                }
            }
            
            // Обновляем профиль собеседника
            profileName.textContent = data.username;
            profileAvatar.src = data.avatar || "/static/images/user.png";
            
            // Сохраняем данные пользователя в кэш
            chatCache.set(`userData_${data.user_id}`, data);
    
            // Загружаем сообщения
            loadChatMessages(data.user_id);
    
            // Заполняем информацию о пользователе
            userInfo.innerHTML = `<p>Имя: ${data.username}</p>
                                 <p>Регистрация: ${formatDate(data.created_at)}</p>
                                 <p>${data.online_status}</p>`;
    
            // Устанавливаем текущий ID чата
            currentChatUserId = data.user_id;
            lastSelectedUserId = data.user_id;
        })
        .catch(error => console.error("❌ Ошибка загрузки чата:", error));
    };

    // Проверяем, был ли запрос на открытие чата до загрузки DOM
    if (window.pendingChatId) {
        openChatById(window.pendingChatId);
        window.pendingChatId = null;
    }
    
    // Получаем имя текущего пользователя для идентификации сообщений
    fetch('/profile/info')
        .then(response => response.json())
        .then(data => {
            if (data.username) {
                currentUserName = data.username;
            }
        })
        .catch(error => console.error("❌ Ошибка получения имени пользователя:", error));

    // Проверка URL на наличие chat_id
    if (pathParts.length === 3 && pathParts[1] === "chat") {
        const chatId = parseInt(pathParts[2], 10);
        if (!isNaN(chatId)) {
            openChatById(chatId);
        }
    }

    function showWelcomeMessage() {
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i class="fas fa-comments"></i>
                </div>
                <h3>Выберите диалог</h3>
                <p>Уверены, у вас всё получится</p>
            </div>
        `;
    }
    
    showWelcomeMessage();
    
    function loadChatList() {
        fetch("/chat/list")
            .then(response => response.json())
            .then(chats => {
                chatListElement.innerHTML = "";
                chats.forEach(chat => {
                    const listItem = document.createElement("li");
                    listItem.setAttribute("data-user-id", chat.user_id);

                    const avatarImg = document.createElement("img");
                    avatarImg.src = chat.avatar;
                    avatarImg.alt = "Аватар";
                    avatarImg.classList.add("chat-avatar");

                    const textContainer = document.createElement("div");
                    textContainer.classList.add("chat-text");
                    
                    // Время в правом верхнем углу
                    const timeElement = document.createElement("span");
                    timeElement.classList.add("last-message-time");
                    timeElement.textContent = chat.last_message_date;

                    textContainer.innerHTML = `
                        <b>${chat.username}</b>
                        <span class="last-message">${chat.last_message || "Нет сообщений"}</span>
                    `;

                    listItem.appendChild(avatarImg);
                    listItem.appendChild(textContainer);
                    listItem.appendChild(timeElement);
                    listItem.addEventListener("click", () => {
                        selectChat(chat.user_id, chat.username, chat.avatar);
                        
                        // На мобильных устройствах переключаемся на чат
                        if (window.innerWidth < 768) {
                            sidebar.classList.remove('active');
                            mainChat.classList.add('active');
                            profileSidebar.classList.remove('active');
                            updateActiveNav(showMessages);
                        }
                    });

                    chatListElement.appendChild(listItem);
                });
                
                // После загрузки чатов, предзагрузим первые несколько для быстрого переключения
                if (chats.length > 0 && !currentChatUserId) {
                    prefetchFirstChats(chats);
                }
            });
    }
    
    // Обновляем активную навигацию на мобильных устройствах
    function updateActiveNav(activeButton) {
        if (showChats && showMessages && showProfile) {
            [showChats, showMessages, showProfile].forEach(btn => {
                btn.classList.remove('active');
            });
            activeButton.classList.add('active');
        }
    }
    
    // Предзагрузка данных первых чатов для быстрого первого переключения
    function prefetchFirstChats(chats) {
        const prefetchCount = Math.min(3, chats.length);
        for (let i = 0; i < prefetchCount; i++) {
            prefetchChatData(chats[i].user_id);
        }
    }
    
    function selectChat(userId, username, avatar) {
        // Предотвращаем множественные клики на того же пользователя
        if (userId === lastSelectedUserId) {
            return;
        }
        lastSelectedUserId = userId;
    
        // Отменяем предыдущий активный запрос, если есть
        if (activeRequest) {
            activeRequest.abort();
            activeRequest = null;
        }
    
        currentChatUserId = userId;
    
        // Удаляем приветственное сообщение
        messagesContainer.innerHTML = '';
    
        // Обновляем заголовок и аватары
        activeChatTitle.textContent = username;
        if (chatAvatar) {
            chatAvatar.src = avatar || "/static/images/user.png";
        }
        
        // Активируем поле ввода сообщений
        messageInputContainer.classList.add('active');
        
        // Обновляем профиль собеседника
        profileName.textContent = username;
        profileAvatar.src = avatar || "/static/images/user.png";
        
        // Обновляем статус онлайн из кеша или показываем временное значение
        const onlineStatus = document.querySelector('.online-status');
        if (onlineStatus) {
            const cachedUserData = chatCache.get(`userData_${userId}`);
            if (cachedUserData && cachedUserData.online_status) {
                onlineStatus.textContent = cachedUserData.online_status;
                if (cachedUserData.online_status === "Онлайн") {
                    onlineStatus.classList.add('status-online');
                } else {
                    onlineStatus.classList.remove('status-online');
                }
            } else {
                onlineStatus.textContent = "Загрузка статуса...";
                onlineStatus.classList.remove('status-online');
            }
        }
        
        // На десктопе показываем профиль
        if (window.innerWidth >= 768) {
            profileSidebar.classList.add('active');
            
            // Убедимся, что сообщения видны (исправляем возможные проблемы с прокруткой)
            setTimeout(() => {
                scrollToBottom();
            }, 100);
        }
    
        // Проверяем, есть ли кэшированные сообщения
        const cachedMessages = chatCache.get(`messages_${userId}`);
        if (cachedMessages) {
            // Мгновенно отображаем кэшированные сообщения
            messagesContainer.innerHTML = "";
            cachedMessages.forEach(msg => {
                appendMessage(
                    msg.sender, 
                    msg.message, 
                    msg.timestamp, 
                    msg.reply_to,
                    msg.message_id
                );
            });
            scrollToBottom();
        } else {
            // Показываем плейсхолдер
            messagesContainer.innerHTML = `<div class="loading-placeholder">Загрузка сообщений...</div>`;
        }
    
        // Проверяем, есть ли данные о пользователе в кэше
        const cachedUserData = chatCache.get(`userData_${userId}`);
        if (cachedUserData) {
            userInfo.innerHTML = `
                <p>Имя: ${cachedUserData.username}</p>
                <p>Регистрация: ${formatDate(cachedUserData.created_at)}</p>
                <p>${cachedUserData.online_status || "Статус неизвестен"}</p>
            `;
        } else {
            userInfo.innerHTML = `<p class="loading-placeholder">Загрузка данных...</p>`;
        }
    
        // Оптимизированная последовательность запросов
        Promise.all([
            optimizedFetch(`/chat/get_chat_id/${userId}`, `chatId_${userId}`),
            optimizedFetch(`/chat/user/${userId}`, `userData_${userId}`),
            optimizedFetch(`/chat/messages/${userId}`, `messages_${userId}`, !cachedMessages)
        ])
        .then(([chatIdData, userData, messages]) => {
            // Обновляем URL чата только если это актуальный запрос
            if (currentChatUserId === userId && chatIdData.chat_id) {
                window.history.pushState({}, "", `/chat/${chatIdData.chat_id}`);
            }
    
            // Обновляем данные только если это актуальный запрос
            if (currentChatUserId === userId) {
                // Обновляем заголовок, если были изменения
                activeChatTitle.textContent = userData.username;
                
                // Обновляем статус онлайн
                if (onlineStatus) {
                    onlineStatus.textContent = userData.online_status || "Статус неизвестен";
                    if (userData.online_status === "Онлайн") {
                        onlineStatus.classList.add('status-online');
                    } else {
                        onlineStatus.classList.remove('status-online');
                    }
                }
                
                // Загружаем сообщения
                messagesContainer.innerHTML = "";
                messages.forEach(msg => {
                    appendMessage(
                        msg.sender, 
                        msg.message, 
                        msg.timestamp, 
                        msg.reply_to,
                        msg.message_id
                    );
                });
                scrollToBottom();
    
                // Обновляем информацию о пользователе
                userInfo.innerHTML = `
                    <p>Имя: ${userData.username}</p>
                    <p>Регистрация: ${formatDate(userData.created_at)}</p>
                    <p>${userData.online_status || "Статус неизвестен"}</p>
                `;
                
                // Предзагружаем данные соседних чатов для мгновенного переключения
                setTimeout(() => prefetchNearbyChatData(), 300);
            }
        })
        .catch(error => {
            if (error.name !== 'AbortError' && currentChatUserId === userId) {
                console.error("Ошибка загрузки чата:", error);
                messagesContainer.innerHTML = `<div class="error-message">Не удалось загрузить чат. Попробуйте позже.</div>`;
            }
        });
    }

    // Оптимизированный запрос с использованием кэша
    function optimizedFetch(url, cacheKey, forceRefresh = false) {
        if (!forceRefresh) {
            const cachedData = chatCache.get(cacheKey);
            if (cachedData) {
                return Promise.resolve(cachedData);
            }
        }

        const controller = new AbortController();
        activeRequest = controller;

        return fetch(url, { signal: controller.signal })
            .then(response => response.json())
            .then(data => {
                chatCache.set(cacheKey, data);
                activeRequest = null;
                return data;
            })
            .catch(error => {
                if (error.name !== 'AbortError') {
                    console.error("Ошибка загрузки:", error);
                }
                activeRequest = null;
                throw error;
            });
    }

    // Предзагрузка соседних чатов для быстрого переключения
    function prefetchNearbyChatData() {
        const chatItems = document.querySelectorAll("#chatList li");
        let currentIndex = -1;
        
        // Находим текущий чат в списке
        chatItems.forEach((item, index) => {
            if (parseInt(item.getAttribute("data-user-id")) === currentChatUserId) {
                currentIndex = index;
            }
        });
        
        if (currentIndex !== -1) {
            // Предзагружаем 2 чата до и 2 после текущего
            for (let i = 1; i <= 2; i++) {
                // Следующие чаты
                if (currentIndex + i < chatItems.length) {
                    const nextId = parseInt(chatItems[currentIndex + i].getAttribute("data-user-id"));
                    prefetchChatData(nextId);
                }
                
                // Предыдущие чаты
                if (currentIndex - i >= 0) {
                    const prevId = parseInt(chatItems[currentIndex - i].getAttribute("data-user-id"));
                    prefetchChatData(prevId);
                }
            }
        }
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
        
        // Предзагружаем ID чата для быстрого переключения
        if (!chatCache.get(`chatId_${userId}`)) {
            fetch(`/chat/get_chat_id/${userId}`)
                .then(response => response.json())
                .then(data => {
                    chatCache.set(`chatId_${userId}`, data);
                })
                .catch(() => {});
        }
    }

    // Функция загрузки сообщений
    function loadChatMessages(userId) {
        return fetch(`/chat/messages/${userId}`)
            .then(response => response.json())
            .then(messages => {
                // Сохраняем в кэш
                chatCache.set(`messages_${userId}`, messages);
                
                // Отображаем только если это текущий активный чат
                if (currentChatUserId === userId) {
                    messagesContainer.innerHTML = "";
                    
                    // Сортируем сообщения по timestamp, чтобы они шли в правильном хронологическом порядке
                    messages.sort((a, b) => {
                        // Преобразуем строки даты/времени в объекты Date для сравнения
                        const dateA = new Date(a.timestamp);
                        const dateB = new Date(b.timestamp);
                        return dateA - dateB; // Сортировка по возрастанию (от старых к новым)
                    });
                    
                    // Отображаем все сообщения в отсортированном порядке
                    messages.forEach(msg => {
                        appendMessage(
                            msg.sender, 
                            msg.message, 
                            msg.timestamp, 
                            msg.reply_to,
                            msg.message_id
                        );
                    });
                    
                    scrollToBottom();
                }
            })
            .catch(error => {
                console.error("Ошибка загрузки сообщений:", error);
            });
    }

    // Обработчик новых сообщений
    function handleNewMessage(data) {
        const currentUserId = parseInt(document.cookie.replace(/(?:(?:^|.*;\s*)user_id\s*=\s*([^;]*).*$)|^.*$/, "$1"));
        
        // Воспроизводим звук только если сообщение адресовано текущему пользователю
        if (data.recipient_id === currentUserId) {
            requestNotificationSound();
        }
        
        // Если сообщение относится к текущему чату - отображаем его
        if (data.recipient_id === currentChatUserId || data.sender_id === currentChatUserId) {
            // Инвалидируем кэш сообщений
            chatCache.invalidate(`messages_${currentChatUserId}`);
            
            // Добавляем сообщение в интерфейс с поддержкой ответов
            appendMessage(
                data.sender, 
                data.message, 
                new Date().toISOString(), 
                data.reply_to,
                data.message_id
            );
            scrollToBottom();
        }
        
        // Обновляем список чатов
        updateChatList(data.sender_id, data.recipient_id, data.message);
    }
    
    // Функция добавления сообщения в интерфейс
    function appendMessage(sender, text, timestamp, replyTo = null, messageId = null) {
        // Проверяем, существует ли уже сообщение с таким ID
        if (messageId) {
            const existingMessage = document.querySelector(`[data-message-id="${messageId}"]`);
            if (existingMessage) {
                // Если сообщение уже существует, удаляем его для предотвращения дубликатов
                existingMessage.remove();
            }
        }
        
        // Если ID не передан, генерируем новый
        if (!messageId) {
            messageId = `msg_${Date.now()}_${messageIdCounter++}`;
        }
        
        // Получаем имя собеседника из заголовка чата
        const chatRecipientName = document.getElementById("activeChatTitle").textContent;
        
        // Определяем, сообщение от текущего пользователя (мое) или от собеседника
        const isSentByMe = sender !== chatRecipientName;
        
        const messageElement = document.createElement("div");
        messageElement.classList.add("message");
        messageElement.classList.add(isSentByMe ? "sent" : "received");
        messageElement.setAttribute("data-message-id", messageId);
        messageElement.setAttribute("data-sender", sender);
        messageElement.setAttribute("data-timestamp", timestamp); // Добавляем атрибут с временем для сортировки
        
        // Сохраняем текст в безопасном виде для атрибута
        const shortText = text.replace(/"/g, '&quot;').substring(0, 100);
        messageElement.setAttribute("data-text", shortText);

        // Добавляем меню действий с сообщением
        const messageActions = document.createElement("div");
        messageActions.classList.add("message-actions");
        messageActions.innerHTML = `
            <button class="reply-btn" title="Ответить">
                <i class="fas fa-reply"></i>
            </button>
        `;
        
        // Добавляем обработчик для кнопки ответа
        messageElement.appendChild(messageActions);
        
        // Находим кнопку ответа и добавляем обработчик
        const replyBtn = messageActions.querySelector(".reply-btn");
        replyBtn.addEventListener("click", () => {
            setReplyTo(messageId, sender, text);
        });

        const messageHeader = document.createElement("div");
        messageHeader.classList.add("message-header");

        const senderElement = document.createElement("div");
        senderElement.classList.add("sender");
        senderElement.textContent = sanitizeHTML(sender);

        const timestampElement = document.createElement("div");
        timestampElement.classList.add("timestamp");
        timestampElement.textContent = formatDateTime(timestamp);

        // Проверяем, является ли сообщение ответом на другое
        if (replyTo) {
            // Создаем элемент ответа
            const replyElement = document.createElement("div");
            replyElement.classList.add("reply-to");
            
            // Поиск оригинального сообщения
            const originalMsg = document.querySelector(`[data-message-id="${replyTo.id}"]`);
            
            // Если оригинальное сообщение существует, устанавливаем класс на основе отправителя
            if (originalMsg) {
                const isOriginalFromMe = originalMsg.classList.contains("sent");
                replyElement.classList.add(isOriginalFromMe ? "reply-sent" : "reply-received");
                
                // Добавляем кнопку для перехода к оригинальному сообщению
                replyElement.style.cursor = "pointer";
                replyElement.addEventListener("click", () => {
                    // Прокручиваем к оригинальному сообщению и делаем его заметным
                    originalMsg.scrollIntoView({ behavior: "smooth", block: "center" });
                    originalMsg.classList.add("highlighted");
                    setTimeout(() => {
                        originalMsg.classList.remove("highlighted");
                    }, 2000);
                });
            } else {
                // Если оригинальное сообщение не найдено, используем базовую стилизацию
                // и добавляем класс, указывающий на отсутствие связи
                replyElement.classList.add("reply-orphaned");
                
                // Добавляем подсказку, что сообщение удалено или недоступно
                replyElement.title = "Исходное сообщение недоступно";
            }
            
            replyElement.innerHTML = `
                <div class="reply-sender">${sanitizeHTML(replyTo.sender)}</div>
                <div class="reply-text">${sanitizeHTML(replyTo.text).substr(0, 50)}${replyTo.text.length > 50 ? '...' : ''}</div>
            `;
            
            messageElement.appendChild(replyElement);
        }

        const textElement = document.createElement("div");
        textElement.classList.add("text");
        
        // Очистка от XSS и сохранение переносов строк
        const sanitizedText = sanitizeHTML(text);
        textElement.innerHTML = sanitizedText.replace(/\n/g, '<br>');

        messageHeader.appendChild(senderElement);
        messageHeader.appendChild(timestampElement);

        messageElement.appendChild(messageHeader);
        messageElement.appendChild(textElement);

        messagesContainer.appendChild(messageElement);
        
        return messageId;
    }

// Функция для установки режима ответа
function setReplyTo(messageId, sender, text) {
    currentReplyTo = {
        id: messageId,
        sender: sender,
        text: text
    };
    
    // Показываем блок с информацией об ответе
    const replyContainer = document.createElement("div");
    replyContainer.id = "replyContainer";
    replyContainer.classList.add("reply-container");
    
    replyContainer.innerHTML = `
        <div class="reply-preview">
            <div class="reply-info">
                <span class="reply-to-sender">${sanitizeHTML(sender)}</span>
                <span class="reply-to-text">${sanitizeHTML(text).substr(0, 30)}${text.length > 30 ? '...' : ''}</span>
            </div>
            <button class="cancel-reply" title="Отменить ответ">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    // Удаляем предыдущий контейнер ответа, если он существует
    const existingReplyContainer = document.getElementById("replyContainer");
    if (existingReplyContainer) {
        existingReplyContainer.remove();
    }
    
    // Находим контейнер ввода сообщения и вставляем перед ним блок ответа
    const messageInputContainer = document.querySelector(".message-input");
    messageInputContainer.prepend(replyContainer);
    
    // Добавляем обработчик для отмены ответа
    const cancelReplyBtn = replyContainer.querySelector(".cancel-reply");
    cancelReplyBtn.addEventListener("click", cancelReply);
    
    // Фокусируемся на поле ввода сообщения
    document.getElementById("messageInput").focus();
}

// Функция отмены ответа
function cancelReply() {
    currentReplyTo = null;
    const replyContainer = document.getElementById("replyContainer");
    if (replyContainer) {
        replyContainer.remove();
    }
}

// Debounce функция для предотвращения частых вызовов
function debounce(func, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}

// Прокрутка чата к последнему сообщению
function scrollToBottom() {
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

// Форматирование времени
function formatDateTime(isoDate) {
    const date = new Date(isoDate);
    return date.toLocaleString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit"
    });
}

// Форматирование даты
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: 'long', 
        day: 'numeric'
    });
}

// Загрузка информации о пользователе
function loadUserInfo(userId) {
    return fetch(`/chat/user/${userId}`)
        .then(response => response.json())
        .then(data => {
            chatCache.set(`userData_${userId}`, data);
            
            if (currentChatUserId === userId) {
                userInfo.innerHTML = `<p>Имя: ${data.username}</p><p>Регистрация: ${formatDate(data.created_at)}</p>`;
            }
        });
}

// Функция отправки сообщения
function sendMessage() {
    const messageText = messageInput.value.trim();

    if (!messageText || !currentChatUserId) return;

    // Добавляем информацию об ответе, если текущее сообщение является ответом
    const replyData = currentReplyTo ? {
        id: currentReplyTo.id,
        sender: currentReplyTo.sender,
        text: currentReplyTo.text
    } : null;

    // Генерируем ID сообщения
    const messageId = `msg_${Date.now()}_${messageIdCounter++}`;

    // Отправляем сообщение с дополнительными данными
    socket.emit("send_message", { 
        message: messageText, 
        user_id: currentChatUserId,
        reply_to: replyData,
        message_id: messageId
    });

    // Очищаем поле ввода и отменяем режим ответа
    messageInput.value = "";
    cancelReply();
    
    // Сбрасываем высоту textarea после отправки сообщения
    messageInput.style.height = '';
}

// Обновление списка чатов
function updateChatList(senderId, recipientId, message) {
    const chatItems = document.querySelectorAll("#chatList li");

    chatItems.forEach(item => {
        const userId = parseInt(item.getAttribute("data-user-id"));
        if (userId === senderId || userId === recipientId) {
            const lastMessageSpan = item.querySelector(".last-message");
            const timeElement = item.querySelector(".last-message-time");
            
            if (lastMessageSpan) {
                const truncatedMessage = message.length > 25 ? message.substring(0, 25) + '...' : message;
                lastMessageSpan.textContent = truncatedMessage;
            }
            
            if (timeElement) {
                timeElement.textContent = new Date().toLocaleTimeString('ru-RU', {hour: '2-digit', minute:'2-digit'});
            }
            
            // Перемещаем чат с новым сообщением вверх списка
            const parent = item.parentElement;
            if (parent.firstChild !== item) {
                parent.insertBefore(item, parent.firstChild);
            }
        }
    });
}

// Функция для проверки и исправления порядка сообщений на странице
function fixMessagesOrder() {
    const messages = Array.from(document.querySelectorAll('.message'));
    
    // Если на странице меньше 2 сообщений, сортировка не нужна
    if (messages.length < 2) return;
    
    // Сортируем сообщения по временной метке
    messages.sort((a, b) => {
        const timestampA = new Date(a.getAttribute('data-timestamp'));
        const timestampB = new Date(b.getAttribute('data-timestamp'));
        return timestampA - timestampB;
    });
    
    // Удаляем все сообщения из контейнера
    messagesContainer.innerHTML = '';
    
    // Добавляем сообщения в правильном порядке
    messages.forEach(msg => {
        messagesContainer.appendChild(msg);
    });
}

// Регистрируем обработчик new_message
if (socket) {
    socket.on("new_message", handleNewMessage);
}

// Обработчик поиска чатов
const searchInput = document.getElementById("searchChats");
if (searchInput) {
    searchInput.addEventListener("input", debounce(function() {
        const searchTerm = this.value.toLowerCase();
        const chatItems = document.querySelectorAll("#chatList li");
        
        chatItems.forEach(item => {
            const username = item.querySelector(".chat-text b").textContent.toLowerCase();
            const lastMessage = item.querySelector(".last-message").textContent.toLowerCase();
            
            if (username.includes(searchTerm) || lastMessage.includes(searchTerm)) {
                item.style.display = "flex";
            } else {
                item.style.display = "none";
            }
        });
    }, 300));
}

// Обработчики событий мобильной навигации
if (backButton) {
    backButton.addEventListener("click", () => {
        sidebar.classList.add('active');
        mainChat.classList.remove('active');
        if (showChats) updateActiveNav(showChats);
    });
}

if (showChats) {
    showChats.addEventListener("click", () => {
        sidebar.classList.add('active');
        mainChat.classList.remove('active');
        profileSidebar.classList.remove('active');
        updateActiveNav(showChats);
    });
}

if (showMessages) {
    showMessages.addEventListener("click", () => {
        sidebar.classList.remove('active');
        mainChat.classList.add('active');
        profileSidebar.classList.remove('active');
        updateActiveNav(showMessages);
    });
}

if (showProfile) {
    showProfile.addEventListener("click", () => {
        sidebar.classList.remove('active');
        mainChat.classList.remove('active');
        profileSidebar.classList.add('active');
        updateActiveNav(showProfile);
    });
}

// Обработчик закрытия профиля на мобильных устройствах
const closeProfile = document.getElementById("closeProfile");
if (closeProfile) {
    closeProfile.addEventListener("click", () => {
        profileSidebar.classList.remove('active');
        mainChat.classList.add('active');
        if (showMessages) updateActiveNav(showMessages);
    });
}

// Обработчик для клавиш - поддержка Shift+Enter
messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
    // Если Shift+Enter, то просто создаем новую строку (браузер обработает по умолчанию)
});

// Функция для автоматического изменения размера textarea
function setupAutoResizeTextarea() {
    const textarea = messageInput;
    if (!textarea) return;
    
    function autoResize() {
        // Сбрасываем высоту, чтобы корректно рассчитать новую
        textarea.style.height = 'auto';
        
        // Устанавливаем новую высоту на основе содержимого
        const newHeight = Math.min(textarea.scrollHeight, 120); // Максимум 120px
        textarea.style.height = `${newHeight}px`;
        
        // Обновляем высоту контейнера сообщений на мобильных устройствах
        if (window.innerWidth < 768) {
            if (messagesContainer) {
                const inputHeight = Math.max(70, newHeight); // Минимум 70px
                messagesContainer.style.maxHeight = `calc(100vh - 130px - 60px - ${inputHeight}px)`;
            }
        }
    }
    
    // Вызываем функцию при вводе текста
    textarea.addEventListener('input', autoResize);
    
    // Инициализируем высоту
    setTimeout(autoResize, 0);
    
    // Переопределяем функцию отправки для сброса высоты
    const originalSendMessage = sendMessage;
    sendMessage = function() {
        originalSendMessage();
        setTimeout(() => {
            textarea.style.height = '';
            if (window.innerWidth < 768) {
                if (messagesContainer) {
                    messagesContainer.style.maxHeight = '';
                }
            }
        }, 0);
    };
}

// Добавляем обработчик для кнопки отправки сообщения
sendMessageBtn.addEventListener("click", sendMessage);

// Загружаем список чатов сразу и обновляем каждые 30 секунд
loadChatList();
setInterval(loadChatList, 30000);

// Инициализируем интерфейс при первой загрузке
function initChatInterface() {
    // Проверяем наличие URL с chat_id
    const chatPath = window.location.pathname.match(/\/chat\/(\d+)/);
    
    // На компьютере 
    if (window.innerWidth >= 768) {
        // Всегда показываем сайдбар
        sidebar.classList.add('active');
        
        // Если URL содержит chat_id или есть последний выбранный чат
        if (chatPath || lastSelectedUserId) {
            mainChat.classList.add('active');
            
            if (chatPath) {
                const chatId = chatPath[1];
                openChatById(chatId);
            } else if (lastSelectedUserId) {
                // Восстанавливаем последний выбранный чат
                const cachedUserData = chatCache.get(`userData_${lastSelectedUserId}`);
                if (cachedUserData) {
                    selectChat(lastSelectedUserId, cachedUserData.username, cachedUserData.avatar);
                }
            }
        }
    } else {
        // На мобильных показываем только сайдбар по умолчанию
        sidebar.classList.add('active');
    }
}

// Вызываем инициализацию
initChatInterface();

// Инициализируем автоматическое изменение размера textarea
setupAutoResizeTextarea();

// Адаптация интерфейса при изменении размера окна
window.addEventListener('resize', function() {
    // Полностью переинициализируем интерфейс
    if (window.innerWidth >= 768) {
        // Компьютер: показываем сайдбар и активный чат
        sidebar.classList.add('active');
        if (currentChatUserId) {
            mainChat.classList.add('active');
            profileSidebar.classList.add('active');
            
            // Также убедимся, что видна область сообщений и поле ввода
            messageInputContainer.classList.add('active');
            
            // Исправление проблемы с прокруткой
            setTimeout(() => {
                scrollToBottom();
            }, 100);
        }
    } else {
        // Мобильные: показываем только один активный экран
        if (mainChat.classList.contains('active')) {
            sidebar.classList.remove('active');
            profileSidebar.classList.remove('active');
        } else if (profileSidebar.classList.contains('active')) {
            sidebar.classList.remove('active');
            mainChat.classList.remove('active');
        } else {
            sidebar.classList.add('active');
            mainChat.classList.remove('active');
            profileSidebar.classList.remove('active');
        }
    }
});
});