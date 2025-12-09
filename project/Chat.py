import logging
import os
import openai
from typing import Optional
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from project.Promts import DEFAULT_SYSTEM_PROMPT
from project.Promts import DAY2_SYSTEM_PROMPT
from project.Promts import DAY3_SYSTEM_PROMPT

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

# Инициализация клиента Yandex GPT
yandex_client = openai.OpenAI(
    api_key=YANDEX_CLOUD_API_KEY,
    base_url="https://llm.api.cloud.yandex.net/v1",  # Используем chat/completions API
    project=YANDEX_CLOUD_FOLDER
)

# Состояния для ConversationHandler
DAY_1_STATE = 1
DAY_2_STATE = 2
DAY_3_STATE = 3

######################################################################################################
######################################################################################################

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
        "/day3 - Режим редактора писем (день 3)\n"  # Добавьте эту строку
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

📋 Описание режимов:
/day1 - Обычный диалог с контекстом
/day2 - Бот отвечает только в формате JSON с тремя языками с контекстом
    """
    await update.message.reply_text(help_text)


# Команда /about
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model_info_text = (
        f"📊 Информация о модели:\n"
        f"• Модель: {YANDEX_CLOUD_MODEL}\n"
        f"• Макс. токенов: {MAX_TOKENS}\n"
        f"• Температура: {TEMPERATURE}\n"
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

######################################################################################################
######################################################################################################

async def handle_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str, next_state: int):
    user_message = update.message.text

    # Проверяем, не является ли это командой
    if user_message.startswith('/'):
        await update.message.reply_text(
            f"Диалог прерван. Используйте {command} чтобы начать заново."
        )
        return ConversationHandler.END

    await handle_gpt_request(update, context, user_message, store_history=True)
    return next_state

# Теперь отдельные обработчики просто вызывают универсальную функцию:
async def handle_day1_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_dialog(update, context, '/day1', DAY_1_STATE)


async def handle_day2_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_dialog(update, context, '/day2', DAY_2_STATE)


async def handle_day3_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_dialog(update, context, '/day3', DAY_3_STATE)

######################################################################################################
######################################################################################################

# Обработчик команды /day1
async def day1_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Устанавливаем режим
    context.chat_data['current_mode'] = 'day1'
    context.chat_data['system_prompt'] = DEFAULT_SYSTEM_PROMPT

    await update.message.reply_text(
        "💬 Обычный режим диалога с Yandex GPT\n\n"
        "Просто напишите ваш вопрос, и я передам его Yandex GPT.\n"
        "Бот будет помнить контекст разговора.\n\n"
        "🧹 Для очистки истории используйте /clear\n\n"
        "Задайте ваш вопрос:"
    )
    return DAY_1_STATE

# Обработчик команды /day2
async def day2_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data['current_mode'] = 'day2'
    context.chat_data['system_prompt'] = DAY2_SYSTEM_PROMPT

    await update.message.reply_text(
        "💬 Режим диалога с Yandex GPT в формате JSON\n\n"
        "Просто напишите ваш вопрос, и я передам его Yandex GPT.\n"
        "Бот будет помнить контекст разговора.\n\n"
        "🧹 Для очистки истории используйте /clear\n\n"
        "Задайте ваш вопрос:"
    )
    return DAY_2_STATE

# Обработчик команды /day3
async def day3_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data['current_mode'] = 'day3'
    context.chat_data['system_prompt'] = DAY3_SYSTEM_PROMPT

    await update.message.reply_text(
        "💬 Режим диалога <<Умный редактор писем с автостопом>>\n\n"
        "Отправьте мне текст письма, а я помогу его отредактировать.\n"
        "Сначала я спрошу о стиле редактирования, затем отредактирую текст.\n\n"
        "🧹 Для очистки истории используйте /clear\n\n"
        "Отправьте текст письма:"
    )
    return DAY_3_STATE

######################################################################################################
######################################################################################################

# Функция для получения ответа от Yandex GPT
async def get_yandex_gpt_response(
        user_message: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        chat_history: Optional[list] = None,
) -> str:
    # Подготавливаем историю сообщений
    messages = []

    # Если истории нет - создаем новую с системным промптом
    if not chat_history:
        messages.append({"role": "system", "content": system_prompt})
    else:
        # Если история есть - используем ее как есть
        # (системный промпт уже должен быть в начале истории)
        messages.extend(chat_history)

    # Добавляем текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})

    try:
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


######################################################################################################
######################################################################################################

# Основная функция обработки запросов к GPT
async def handle_gpt_request(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_message: str,
        store_history: bool = False
):
    """Общая функция обработки запросов к GPT"""
    typing_msg = await update.message.reply_text("🤔 Думаю...")

    try:
        # Получаем текущий системный промпт
        system_prompt = context.chat_data.get('system_prompt', DEFAULT_SYSTEM_PROMPT)

        # Получаем историю диалога
        chat_history = context.chat_data.get('chat_history', [])

        # Получаем ответ
        response = await get_yandex_gpt_response(
            user_message=user_message,
            system_prompt=system_prompt,
            chat_history=chat_history
        )

        # Обновляем историю диалога, если нужно
        if store_history:
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": response})

            if len(chat_history) > 50:
                chat_history = chat_history[-50:]

            context.chat_data['chat_history'] = chat_history

        await typing_msg.delete()

        if context.chat_data['current_mode'] != 'day2':
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(response.replace('```', ''))

    except Exception as e:
        await typing_msg.delete()
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(
            f"⚠️ Произошла ошибка при обращении к Yandex GPT:\n\n{str(e)}"
        )


# Отмена диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    await update.message.reply_text("Диалог завершен.")
    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if not user_text.startswith('/'):
        logger.info(f"Сообщение от {update.effective_user.id}: {user_text}")
        await update.message.reply_text(
            "🤖 Выберите режим работы:\n\n"
            "🔹 /day1 - Обычный диалог\n"
            "🔹 /day2 - Диалог с JSON ответом\n"
            "🔹 /help - Справка по командам"
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

    # Создаем ConversationHandler для обычного режима
    day1_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('day1', day1_chat)],
        states={
            DAY_1_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day1_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Создаем ConversationHandler для режима day2
    day2_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('day2', day2_chat)],
        states={
            DAY_2_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day2_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Создаем ConversationHandler для режима day3
    day3_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('day3', day3_chat)],  # Исправлено на 'day3'
        states={
            DAY_3_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day3_dialog)]  # Исправлено на ASK_DAY3_QUESTION
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", factory_reset))
    application.add_handler(CommandHandler("about", about))

    # Регистрируем ConversationHandler
    application.add_handler(day1_conv_handler)
    application.add_handler(day2_conv_handler)
    application.add_handler(day3_conv_handler)

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