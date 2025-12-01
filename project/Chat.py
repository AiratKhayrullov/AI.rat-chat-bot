import logging
import os
import openai
from typing import Optional
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Загружаем переменные из .env файла
load_dotenv()

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
YANDEX_CLOUD_FOLDER = os.getenv('YANDEX_CLOUD_FOLDER')
YANDEX_CLOUD_API_KEY = os.getenv('YANDEX_CLOUD_API_KEY')
YANDEX_CLOUD_MODEL = os.getenv('YANDEX_CLOUD_MODEL')
MAX_TOKENS = int(os.getenv('MAX_TOKENS'))
TEMPERATURE = float(os.getenv('TEMPERATURE'))

# Проверка конфигурации
if not all([TELEGRAM_BOT_TOKEN, YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_API_KEY]):
    missing = []
    if not TELEGRAM_BOT_TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
    if not YANDEX_CLOUD_FOLDER: missing.append("YANDEX_CLOUD_FOLDER")
    if not YANDEX_CLOUD_API_KEY: missing.append("YANDEX_CLOUD_API_KEY")
    logger.error(f"Отсутствуют обязательные переменные: {', '.join(missing)}")
    exit(1)

# Инициализация клиента Yandex GPT
yandex_client = openai.OpenAI(
    api_key=YANDEX_CLOUD_API_KEY,
    base_url="https://llm.api.cloud.yandex.net/v1",  # Используем chat/completions API
    project=YANDEX_CLOUD_FOLDER
)

# Состояния для ConversationHandler
ASK_QUESTION = 1


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"Привет, {user.first_name}! Я твой телеграм-бот с Yandex GPT.\n\n"
        "Доступные команды:\n"
        "/start - Начать общение\n"
        "/help - Показать справку\n"
        "/about - Данные о модели \n\n"
        "/gpt - Включить режим чата (с контекстом)\n"
        "/clear - Очистить историю диалога (забыть контекст)"
    )
    await update.message.reply_text(welcome_text)


# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 Доступные команды:

Основные:
/help - Показать эту справку
/about - Данные о текущей модели
/gpt - Включить режим чата (с контекстом)
/clear - Очистить историю диалога (забыть контекст)
    """
    await update.message.reply_text(help_text)

# Команда /model
async def model_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model_info_text = (
        f"📊 Информация о модели:\n"
        f"• Модель: {YANDEX_CLOUD_MODEL}\n"
        f"• Макс. токенов: {MAX_TOKENS}\n"
        f"• Температура: {TEMPERATURE}\n"
    )
    await update.message.reply_text(model_info_text)

# Команда /clear - очистка истории диалога
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'chat_history' in context.chat_data:
        del context.chat_data['chat_history']
        await update.message.reply_text("✅ История диалога очищена!")
    else:
        await update.message.reply_text("ℹ️ История диалога уже пуста.")


# Функция для получения ответа от Yandex GPT
async def get_yandex_gpt_response(
        user_message: str,
        chat_history: Optional[list] = None,
        stream: bool = False
) -> str:
    """Получение ответа от Yandex GPT"""

    # Подготавливаем историю сообщений
    messages = []

    # Добавляем системное сообщение
    system_message = {
        "role": "system",
        "content": "Ты полезный ассистент, который помогает пользователям. Отвечай на русском языке."
    }

    # Добавляем историю диалога, если есть
    if chat_history:
        messages.extend(chat_history)
    else:
        messages.append(system_message)

    # Добавляем текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})

    try:
        if stream:
            # Потоковый ответ
            response = yandex_client.chat.completions.create(
                model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=True
            )

            # Собираем потоковый ответ
            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    chunk_text = chunk.choices[0].delta.content
                    full_response += chunk_text

            return full_response
        else:
            # Обычный ответ
            response = yandex_client.chat.completions.create(
                model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stream=False
            )

            return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Ошибка при запросе к Yandex GPT: {e}")
        raise


# Обработчик команды /gpt
async def gpt_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать диалог с Yandex GPT"""
    await update.message.reply_text(
        "💬 Режим диалога с Yandex GPT\n\n"
        "Просто напишите ваш вопрос, и я передам его Yandex GPT.\n"
        "Используйте /clear чтобы очистить историю диалога.\n\n"
        "Задайте ваш вопрос:"
    )
    return ASK_QUESTION


# Обработчик ответов в режиме диалога
async def handle_gpt_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений в режиме диалога"""
    user_message = update.message.text

    # Проверяем, не является ли это командой
    if user_message.startswith('/'):
        await update.message.reply_text("Диалог прерван. Используйте /gpt чтобы начать заново.")
        return ConversationHandler.END

    await handle_gpt_request(update, context, user_message, store_history=True)
    return ASK_QUESTION


# Основная функция обработки запросов к GPT
async def handle_gpt_request(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_message: str,
        store_history: bool = False
):
    """Обработка запроса к Yandex GPT"""

    # Отправляем сообщение "печатает..."
    typing_message = await update.message.reply_text("🤔 Думаю...")

    try:
        # Получаем историю диалога из chat_data
        chat_history = context.chat_data.get('chat_history', [])

        # Получаем ответ от Yandex GPT
        response = await get_yandex_gpt_response(user_message, chat_history)

        # Обновляем историю диалога, если нужно
        if store_history:
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": response})

            # Ограничиваем размер истории (последние 10 сообщений)
            if len(chat_history) > 20:  # 10 пар вопрос-ответ
                chat_history = chat_history[-20:]

            context.chat_data['chat_history'] = chat_history

        # Отправляем ответ
        await typing_message.delete()  # Удаляем сообщение "Думаю..."
        await update.message.reply_text(f"🤖 Yandex GPT:\n\n{response}")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await typing_message.delete()
        await update.message.reply_text(
            f"⚠️ Произошла ошибка при обращении к Yandex GPT:\n\n{str(e)}"
        )


# Отмена диалога
async def cancel(update: Update):
    """Отмена диалога"""
    await update.message.reply_text("Диалог отменен.")
    return ConversationHandler.END


# Обработка обычных текстовых сообщений (без команд)
async def handle_message(update: Update):
    """Обработка обычных текстовых сообщений"""
    user_text = update.message.text

    # Если сообщение начинается не с команды, просто логируем
    if not user_text.startswith('/'):
        logger.info(f"Сообщение от {update.effective_user.id}: {user_text}")
        await update.message.reply_text(
            "Я могу отвечать на команды или помочь с Yandex GPT.\n"
            "Используйте /help для списка команд или /gpt для общения с ИИ."
        )



# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка: {context.error}")

    # Отправляем сообщение об ошибке пользователю
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "😔 Произошла ошибка. Попробуйте еще раз позже."
        )


def main():
    """Запуск бота"""

    # Проверяем соединение с Yandex GPT
    logger.info("Проверка подключения к Yandex GPT...")
    try:
        yandex_client.chat.completions.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            messages=[{"role": "user", "content": "Тестовое сообщение"}],
            max_tokens=10,
            temperature=0.1
        )
        logger.info("✅ Подключение к Yandex GPT успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Yandex GPT: {e}")
        print(f"Ошибка подключения к Yandex GPT: {e}")
        print("Проверьте правильность YANDEX_CLOUD_FOLDER и YANDEX_CLOUD_API_KEY")
        exit(-1)

    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Создаем ConversationHandler для режима диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('gpt', gpt_chat)],
        states={
            ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gpt_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("about", model_info))

    # Регистрируем ConversationHandler
    application.add_handler(conv_handler)

    # Регистрируем обработчик обычных сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("Бот запущен...")
    print("=" * 50)
    print("🤖 Телеграм-бот с Yandex GPT запущен!")
    print(f"📊 Модель: {YANDEX_CLOUD_MODEL}")
    print(f"🔥 Температура: {TEMPERATURE}")
    print(f"🔢 Макс. токенов: {MAX_TOKENS}")
    print("=" * 50)

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == '__main__':
    main()