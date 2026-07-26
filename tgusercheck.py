import asyncio
import random
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.functions.account import CheckUsernameRequest
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# ============ КОНФИГУРАЦИЯ ============
API_ID = 1234567  # Замени на свой api_id
API_HASH = 'your_api_hash'  # Замени на свой api_hash
BOT_TOKEN = 'your_bot_token'  # Замени на токен твоего бота

# Хранилище мониторинга: {user_id: {'username': 'name', 'chat_id': id, 'task': asyncio.Task}}
monitoring_tasks = {}

# Создаем клиент Telethon
client = TelegramClient('session_monitor', API_ID, API_HASH)

# ============ ФУНКЦИИ МОНИТОРИНГА ============
async def monitor_username(user_id: int, username: str, chat_id: int):
    """Фоновый мониторинг юзернейма"""
    check_interval = random.randint(300, 600)  # 5-10 минут в секундах
    attempts = 0
    
    while True:
        try:
            attempts += 1
            # Проверяем доступность
            result = await client(CheckUsernameRequest(username))
            
            if result:  # Юзернейм СВОБОДЕН!
                # Отправляем уведомление
                message = (
                    f"🎉 **ЮЗЕРНЕЙМ ОСВОБОДИЛСЯ!** 🎉\n\n"
                    f"@{username}\n\n"
                    f"✅ Он теперь доступен! Забирай скорее!\n"
                    f"🔗 t.me/{username}\n\n"
                    f"⏱ Проверок: {attempts}\n"
                    f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
                
                # Кнопка для остановки мониторинга
                keyboard = [[InlineKeyboardButton("🛑 Остановить мониторинг", callback_data=f"stop_{user_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await client.send_message(chat_id, message, reply_markup=reply_markup)
                
                # Останавливаем мониторинг после успеха
                if user_id in monitoring_tasks:
                    del monitoring_tasks[user_id]
                break
                
        except errors.FloodWaitError as e:
            wait_time = e.seconds
            await client.send_message(
                chat_id, 
                f"⚠️ Telegram ограничил запросы. Пауза {wait_time} секунд..."
            )
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            error_msg = f"❌ Ошибка мониторинга: {str(e)[:100]}"
            await client.send_message(chat_id, error_msg)
            await asyncio.sleep(60)  # Ждем минуту при ошибке
        
        # Ждем следующий интервал
        await asyncio.sleep(check_interval)
        # Обновляем интервал для разнообразия
        check_interval = random.randint(300, 600)

# ============ ОБРАБОТЧИКИ КОМАНД ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Бот-монитор юзернеймов**\n\n"
        "Я буду проверять юзернейм каждые 5-10 минут и сообщу, "
        "когда он освободится!\n\n"
        "📝 **Как использовать:**\n"
        "1. Отправь мне юзернейм (без @)\n"
        "2. Я начну мониторинг\n"
        "3. Как только юзернейм освободится - я пришлю уведомление!\n\n"
        "⚡️ Юзернейм должен быть от 5 до 32 символов\n"
        "🔤 Только буквы, цифры и _\n\n"
        "🛑 Для остановки используй /stop"
    )

async def stop_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановка мониторинга"""
    user_id = update.effective_user.id
    
    if user_id in monitoring_tasks:
        task = monitoring_tasks[user_id]
        task.cancel()
        del monitoring_tasks[user_id]
        await update.message.reply_text(
            "✅ **Мониторинг остановлен!**\n"
            "Можешь начать новый командой /start"
        )
    else:
        await update.message.reply_text(
            "ℹ️ У тебя нет активного мониторинга.\n"
            "Отправь юзернейм для начала."
        )

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка отправленного юзернейма"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.message.text.strip()
    
    # Проверяем, не мониторит ли уже
    if user_id in monitoring_tasks:
        await update.message.reply_text(
            "⚠️ У тебя уже есть активный мониторинг!\n"
            "Используй /stop чтобы остановить текущий."
        )
        return
    
    # Убираем @
    if username.startswith('@'):
        username = username[1:]
    
    # Валидация
    if len(username) < 5 or len(username) > 32:
        await update.message.reply_text("❌ Юзернейм должен быть от 5 до 32 символов!")
        return
    
    if not username.replace('_', '').isalnum():
        await update.message.reply_text("❌ Только буквы, цифры и _ !")
        return
    
    # Проверяем доступность сейчас
    status_msg = await update.message.reply_text(f"🔍 Проверяю @{username}...")
    
    try:
        result = await client(CheckUsernameRequest(username))
        
        if result:
            await status_msg.edit_text(
                f"✅ Юзернейм @{username} **УЖЕ СВОБОДЕН**! 🎉\n"
                f"Забирай прямо сейчас: t.me/{username}"
            )
            return
        else:
            await status_msg.edit_text(
                f"🔴 Юзернейм @{username} занят.\n\n"
                f"🔄 Начинаю мониторинг...\n"
                f"⏱ Буду проверять каждые 5-10 минут.\n"
                f"📨 Как только освободится - сообщу!\n\n"
                f"🛑 Для остановки используй /stop"
            )
            
            # Запускаем фоновую задачу мониторинга
            task = asyncio.create_task(monitor_username(user_id, username, chat_id))
            monitoring_tasks[user_id] = task
            
    except errors.FloodWaitError as e:
        await status_msg.edit_text(
            f"⚠️ Слишком много запросов! Подожди {e.seconds} секунд."
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith('stop_'):
        user_id = int(data.split('_')[1])
        
        if user_id in monitoring_tasks:
            monitoring_tasks[user_id].cancel()
            del monitoring_tasks[user_id]
            await query.edit_message_text(
                "✅ Мониторинг остановлен!\n"
                "Отправь новый юзернейм для проверки."
            )
        else:
            await query.edit_message_text("ℹ️ Мониторинг уже остановлен.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус мониторинга"""
    user_id = update.effective_user.id
    
    if user_id in monitoring_tasks:
        await update.message.reply_text(
            "🟢 **Мониторинг активен!**\n\n"
            "Я проверяю юзернейм каждые 5-10 минут.\n"
            "Как только он освободится - ты узнаешь первым! 🚀\n\n"
            "Используй /stop чтобы остановить."
        )
    else:
        await update.message.reply_text(
            "🔴 Нет активного мониторинга.\n"
            "Отправь юзернейм для начала."
        )

# ============ ОСНОВНАЯ ФУНКЦИЯ ============
async def main():
    # Запускаем Telethon клиент
    await client.start()
    print("✅ Telethon клиент запущен!")
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop_monitoring))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("help", start))
    
    # Обработка текстовых сообщений (юзернеймов)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))
    
    # Обработка кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    print("✅ Бот-монитор запущен! Нажми Ctrl+C для остановки.")
    print(f"📊 Активных мониторингов: {len(monitoring_tasks)}")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())