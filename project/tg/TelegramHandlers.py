import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import os

logger = logging.getLogger(__name__)


YANDEX_CLOUD_MODEL = os.getenv('YANDEX_CLOUD_MODEL')
MAX_TOKENS = int(os.getenv('MAX_TOKENS'))
TEMPERATURE = float(os.getenv('TEMPERATURE'))

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"Привет, {user.first_name}! Я твой телеграм-бот с Yandex GPT.\n\n"
        "🔹 Основные команды:\n"
        "/start - Начать общение\n"
        "/help - Показать справку\n"
        "/about - Данные о модели \n\n"
        "🔹 Режимы работы:\n"
        "/day1 - Включить режим чата с контекстом (день 1)\n"
        "/day2 - Режим диалога с форматом ответа в JSON на трех языках (день 2)\n"
        "/day3 - Режим редактора писем (день 3)\n"
        "📋 Анализ:\n"
        "/test_models - Тестирование моделей (день 7)\n"
        "/test_tokens - Тестирование токенов (день 8)\n"
        "/compression_stats - Показать статистику сжатия истории диалога (день 9)\n"
        "/clear - Очистить историю диалога и сбросить режим\n\n"
        "⚡ Выбери режим и начинай общение!"
    )
    await update.message.reply_text(welcome_text)


# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 Доступные команды:

🔹 Основные:
/help - Показать эту справку
/about - Данные о текущей модели
/clear - Очистить историю диалога и сбросить режим

🔹 Режимы работы:
/day1 - Включить обычный режим чата (с контекстом, день 1)
/day2 - Режим диалога с форматом ответа в JSON на трех языках (день 2)
/day3 - Режим редактора писем (день 3)

📋 Анализ:
/test_models - Сравнение разных моделей Yandex GPT
/test_tokens - Сравнительной анализ токенов
/compression_stats - Показать статистику сжатия истории диалога"
    """
    await update.message.reply_text(help_text)


# Команда /about
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = {
        'YANDEX_CLOUD_MODEL': YANDEX_CLOUD_MODEL,
        'MAX_TOKENS': MAX_TOKENS,
        'TEMPERATURE': TEMPERATURE
    }
    
    model_info_text = (
        f"📊 Информация о модели:\n"
        f"• Модель: {config.get('YANDEX_CLOUD_MODEL', 'Не указана')}\n"
        f"• Макс. токенов: {config.get('MAX_TOKENS', 'Не указано')}\n"
        f"• Температура: {config.get('TEMPERATURE', 'Не указано')}\n"
    )
    await update.message.reply_text(model_info_text)


# Команда /clear - очистка истории диалога и сброс режима
async def factory_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем все данные в chat_data
    context.chat_data.clear()

    # Также очищаем user_data на всякий случай
    context.user_data.clear()

    await update.message.reply_text("✅ История полностью очищены!")

    # Возвращаем END для завершения активных диалогов
    return ConversationHandler.END


# Отмена диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    await update.message.reply_text("Диалог завершен.")
    return ConversationHandler.END


# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка: {context.error}")

    # Отправляем сообщение об ошибке пользователю
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "😔 Произошла ошибка. Попробуйте еще раз позже."
        )