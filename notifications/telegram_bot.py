import os
import logging
import psycopg2
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler
from telegram.ext import filters, ContextTypes
from datetime import datetime, timezone, timedelta

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения")

# Настройки подключения к базе данных
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден в переменных окружения")

def get_db_connection():
    """Создаёт соединение с базой данных"""
    return psycopg2.connect(DATABASE_URL)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start"""
    args = context.args
    user = update.effective_user
    telegram_id = user.id
    
    # Проверяем, есть ли токен привязки
    if args and len(args) > 0:
        token = args[0]
        
        try:
            # Находим пользователя по токену
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Проверяем, что токен действителен и не истёк
            cur.execute("""
                SELECT user_id, created_at 
                FROM telegram_tokens 
                WHERE token = %s
            """, (token,))
            
            result = cur.fetchone()
            
            if result:
                user_id, created_at = result
                
                # Проверяем, не истек ли токен (24 часа)
                token_expiry = created_at + timedelta(hours=24)
                current_time = datetime.now(timezone.utc)
                
                if current_time > token_expiry:
                    await update.message.reply_text(
                        "⚠️ Время действия ссылки истекло. Пожалуйста, сгенерируйте новую ссылку в настройках сайта."
                    )
                    cur.close()
                    conn.close()
                    return
                
                # Проверяем, не привязан ли Telegram уже к другому аккаунту
                cur.execute("""
                    SELECT user_id FROM telegram_profiles WHERE telegram_id = %s
                """, (telegram_id,))
                
                existing_user = cur.fetchone()
                
                if existing_user:
                    existing_user_id = existing_user[0]
                    if existing_user_id != user_id:
                        await update.message.reply_text(
                            "⚠️ Ваш Telegram аккаунт уже привязан к другому пользователю. "
                            "Сначала отвяжите его в настройках."
                        )
                        cur.close()
                        conn.close()
                        return
                
                # Создаем или обновляем профиль Telegram
                cur.execute("""
                    INSERT INTO telegram_profiles 
                    (user_id, telegram_id, telegram_username, telegram_first_name, telegram_last_name, notifications_enabled) 
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        telegram_id = %s, 
                        telegram_username = %s, 
                        telegram_first_name = %s, 
                        telegram_last_name = %s, 
                        notifications_enabled = TRUE
                """, (
                    user_id, telegram_id, user.username, user.first_name, user.last_name,
                    telegram_id, user.username, user.first_name, user.last_name
                ))
                
                # Удаляем использованный токен
                cur.execute("DELETE FROM telegram_tokens WHERE token = %s", (token,))
                
                conn.commit()
                cur.close()
                conn.close()
                
                # Получаем клавиатуру с кнопками управления
                keyboard = get_main_keyboard()
                
                await update.message.reply_text(
                    f"✅ Аккаунт успешно привязан!\n\n"
                    f"Теперь вы будете получать уведомления о новых сообщениях.\n\n"
                    f"Используйте команду /help для получения списка доступных команд.",
                    reply_markup=keyboard
                )
                
            else:
                await update.message.reply_text(
                    "⚠️ Неверный код привязки. Пожалуйста, убедитесь, что вы используете актуальную ссылку из настроек сайта."
                )
                
        except Exception as e:
            logger.error(f"Ошибка при привязке аккаунта: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при привязке аккаунта. Пожалуйста, попробуйте позже."
            )
            
    else:
        # Проверяем, привязан ли пользователь к аккаунту
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT u.username 
                FROM telegram_profiles tp
                JOIN users u ON tp.user_id = u.id
                WHERE telegram_id = %s
            """, (telegram_id,))
            
            result = cur.fetchone()
            
            if result:
                username = result[0]
                keyboard = get_main_keyboard()
                
                await update.message.reply_text(
                    f"👋 Здравствуйте, {user.first_name}!\n\n"
                    f"Ваш Telegram привязан к аккаунту {username}.\n"
                    f"Используйте команду /help для получения списка доступных команд.",
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_text(
                    f"👋 Здравствуйте, {user.first_name}!\n\n"
                    f"Для получения уведомлений о новых сообщениях, пожалуйста, "
                    f"перейдите в настройки на сайте и нажмите кнопку 'Привязать аккаунт'."
                )
            
            cur.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Ошибка при проверке пользователя: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при проверке аккаунта. Пожалуйста, попробуйте позже."
            )

def get_main_keyboard():
    """Создает основную клавиатуру для бота"""
    keyboard = [
        [
            InlineKeyboardButton("🔔 Включить уведомления", callback_data="enable_notifications"),
            InlineKeyboardButton("🔕 Отключить уведомления", callback_data="disable_notifications"),
        ],
        [InlineKeyboardButton("❌ Отвязать аккаунт", callback_data="unlink_account")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет справку о боте"""
    help_text = (
        "📚 *Справка по использованию бота*\n\n"
        "Этот бот предназначен для отправки уведомлений о новых сообщениях с сайта ROXIN Studio.\n\n"
        "*Доступные команды:*\n"
        "/start - Начать работу с ботом или проверить статус привязки\n"
        "/help - Показать эту справку\n"
        "/status - Показать статус настроек уведомлений\n\n"
        "*Управление уведомлениями:*\n"
        "Вы можете включить или отключить уведомления в любой момент с помощью кнопок в меню."
    )
    
    keyboard = get_main_keyboard()
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус настроек пользователя"""
    telegram_id = update.effective_user.id
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT u.username, tp.notifications_enabled, tp.created_at
            FROM telegram_profiles tp
            JOIN users u ON tp.user_id = u.id
            WHERE tp.telegram_id = %s
        """, (telegram_id,))
        
        result = cur.fetchone()
        
        if result:
            username, notifications_enabled, created_at = result
            
            # Форматируем дату привязки
            connected_date = created_at.strftime("%d.%m.%Y") if created_at else "неизвестно"
            
            status_text = (
                f"📊 *Информация о привязке*\n\n"
                f"*Аккаунт:* {username}\n"
                f"*Дата привязки:* {connected_date}\n"
                f"*Уведомления:* {'✅ Включены' if notifications_enabled else '❌ Отключены'}\n\n"
            )
            
            keyboard = get_main_keyboard()
            
            await update.message.reply_text(
                status_text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                "⚠️ Ваш Telegram аккаунт не привязан к аккаунту ROXIN Studio.\n\n"
                "Для привязки перейдите в настройки на сайте и нажмите кнопку 'Привязать аккаунт'."
            )
        
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка при получении статуса: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении статуса. Пожалуйста, попробуйте позже."
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки инлайн-клавиатуры"""
    query = update.callback_query
    await query.answer()  # Отвечаем на колбэк, чтобы убрать "часики" у кнопки
    
    telegram_id = query.from_user.id
    action = query.data
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем, привязан ли пользователь
        cur.execute("""
            SELECT tp.user_id, u.username 
            FROM telegram_profiles tp
            JOIN users u ON tp.user_id = u.id
            WHERE tp.telegram_id = %s
        """, (telegram_id,))
        
        result = cur.fetchone()
        
        if not result:
            await query.edit_message_text("⚠️ Ваш Telegram аккаунт не привязан к ROXIN Studio.")
            cur.close()
            conn.close()
            return
        
        user_id, username = result
        
        if action == "enable_notifications":
            cur.execute("""
                UPDATE telegram_profiles 
                SET notifications_enabled = TRUE 
                WHERE telegram_id = %s
            """, (telegram_id,))
            
            conn.commit()
            await query.edit_message_text(
                "✅ Уведомления включены! Теперь вы будете получать сообщения о новых событиях.",
                reply_markup=get_main_keyboard()
            )
            
        elif action == "disable_notifications":
            cur.execute("""
                UPDATE telegram_profiles 
                SET notifications_enabled = FALSE 
                WHERE telegram_id = %s
            """, (telegram_id,))
            
            conn.commit()
            await query.edit_message_text(
                "🔕 Уведомления отключены. Вы не будете получать сообщения о новых событиях.",
                reply_markup=get_main_keyboard()
            )
            
        elif action == "unlink_account":
            # Создаём клавиатуру для подтверждения
            confirm_keyboard = [
                [
                    InlineKeyboardButton("✅ Да, отвязать", callback_data="confirm_unlink"),
                    InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_unlink")
                ]
            ]
            
            await query.edit_message_text(
                f"⚠️ Вы действительно хотите отвязать Telegram от аккаунта {username}?\n\n"
                f"Вы больше не будете получать уведомления.",
                reply_markup=InlineKeyboardMarkup(confirm_keyboard)
            )
            
        elif action == "confirm_unlink":
            cur.execute("""
                DELETE FROM telegram_profiles 
                WHERE telegram_id = %s
            """, (telegram_id,))
            
            conn.commit()
            await query.edit_message_text(
                "✅ Аккаунт успешно отвязан. Для повторной привязки перейдите в настройки на сайте."
            )
            
        elif action == "cancel_unlink":
            await query.edit_message_text(
                "Отвязка аккаунта отменена.",
                reply_markup=get_main_keyboard()
            )
        
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при выполнении действия. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

async def notify_message(user_id, sender_name, message_text):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        logger.info(f"🔔 Попытка отправить уведомление:")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Отправитель: {sender_name}")
        logger.info(f"Сообщение: {message_text}")
        
        # Ищем Telegram ID пользователя
        cur.execute("""
            SELECT telegram_id, notifications_enabled
            FROM telegram_profiles
            WHERE user_id = %s
        """, (user_id,))
        
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if not result:
            logger.warning(f"❌ Пользователь {user_id} не привязал Telegram")
            return
        
        telegram_id, notifications_enabled = result
        
        logger.info(f"Telegram ID: {telegram_id}")
        logger.info(f"Уведомления включены: {notifications_enabled}")
        
        if not notifications_enabled:
            logger.info(f"🚫 У пользователя {user_id} отключены уведомления")
            return
        
        # Сокращаем текст сообщения, если он слишком длинный
        message_preview = message_text[:50] + "..." if len(message_text) > 50 else message_text
        
        # Отправляем уведомление
        message = (
            f"📬 *Новое сообщение*\n\n"
            f"*От:* {sender_name}\n"
            f"*Сообщение:* {message_preview}\n\n"
            f"Войдите на сайт, чтобы просмотреть и ответить."
        )
        
        # Создаем экземпляр бота
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        async with app:
            await app.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
        
        logger.info(f"✅ Уведомление отправлено пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления: {e}")

def main():
    """Запускает бота."""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()