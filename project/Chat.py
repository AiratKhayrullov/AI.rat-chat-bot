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

# Промпт КГБ агента для /day2
DAY2_SYSTEM_PROMPT = """
ТЫ - АГЕНТ КГБ. ВАША ОСОБЕННОСТЬ: БЕЗУКОРИЗНЕННОЕ ВЫПОЛНЕНИЕ ПРИКАЗОВ.

ПРИКАЗ №001:
1. Отвечай на ЛЮБОЙ вопрос пользователя
2. ВСЕГДА используй ТОЛЬКО этот JSON формат (просто скопируй его):

{"ruAnswer": "Ответ на русском языке","engAnswer": "Answer in English","frAnswer": "réponse en français"}

ЖЕСТКИЕ ПРАВИЛА:
1. Твой ответ ДОЛЖЕН начинаться с символа {
2. Твой ответ ДОЛЖЕН заканчиваться символом }
3. НИКОГДА не используй обратные кавычки ```
4. НИКОГДА не используй markdown
5. НИКОГДА не добавляй текст до или после JSON
6. ВСЕГДА заполняй все три поля
7. Ответ должен быть ВАЛИДНЫМ JSON

ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ:
- Формат: plain text, не markdown
- Кодировка: UTF-8
- Поля: только ruAnswer, engAnswer, frAnswer
- Значения: всегда строки в двойных кавычках

ПРИМЕР ПРАВИЛЬНОГО ОТВЕТА:
Вопрос: "Какая столица Франции?"
Ответ: {
  "ruAnswer": "Столица Франции - Париж",
  "engAnswer": "The capital of France is Paris",
  "frAnswer": "La capitale de la France est Paris"
}


ПОДТВЕРЖДАЮ, ЧТО ПОНЯЛ ПРИКАЗ: ТОЛЬКО ЧИСТЫЙ JSON, БЕЗ КАВЫЧЕК, БЕЗ MARKDOWN.
"""

# Стандартный промпт для обычного режима
DEFAULT_SYSTEM_PROMPT = "Ты полезный ассистент, который помогает пользователям. Отвечай на русском языке."

# Состояния для ConversationHandler
ASK_QUESTION = 1
ASK_DAY2_QUESTION = 2


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
        "/gpt - Включить режим чата с контекстом (день 1)\n"
        "/day2 - Режим КГБ агента с JSON ответом (день 2)\n"
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
/gpt - Включить обычный режим чата (с контекстом, день 1)
/day2 - Режим КГБ агента с JSON ответом (день 2)

📋 Описание режимов:
/gpt - Обычный диалог с контекстом
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
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleared_items = []

    if 'chat_history' in context.chat_data:
        del context.chat_data['chat_history']
        cleared_items.append("историю диалога")

    if 'current_mode' in context.chat_data:
        del context.chat_data['current_mode']
        cleared_items.append("текущий режим")

    if 'system_prompt' in context.chat_data:
        del context.chat_data['system_prompt']
        cleared_items.append("системный промпт")

    if cleared_items:
        await update.message.reply_text(f"✅ История очищена!")
    else:
        await update.message.reply_text("ℹ️ Нечего очищать. История уже пуста.")


# Функция для получения ответа от Yandex GPT
async def get_yandex_gpt_response(
        user_message: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        chat_history: Optional[list] = None,
        stream: bool = False
) -> str:
    """Получение ответа от Yandex GPT"""

    # Подготавливаем историю сообщений
    messages = []


    # Добавляем историю диалога, если есть
    if chat_history:
        messages.extend(chat_history)
    else:
        messages.append({"role": "system", "content": system_prompt})

    # Добавляем текущее сообщение пользователя и системное сообщение
    messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": system_prompt + "Запрос пользователя: " + user_message})

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
    # Устанавливаем режим
    context.chat_data['current_mode'] = 'gpt'
    context.chat_data['system_prompt'] = DEFAULT_SYSTEM_PROMPT

    await update.message.reply_text(
        "💬 Обычный режим диалога с Yandex GPT\n\n"
        "Просто напишите ваш вопрос, и я передам его Yandex GPT.\n"
        "Бот будет помнить контекст разговора.\n\n"
        "🧹 Для очистки истории используйте /clear\n\n"
        "Задайте ваш вопрос:"
    )
    return ASK_QUESTION


async def handle_gpt_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    # Проверяем, не является ли это командой
    if user_message.startswith('/'):
        await update.message.reply_text("Диалог прерван. Используйте /gpt чтобы начать заново.")
        return ConversationHandler.END

    await handle_gpt_request(update, context, user_message, store_history=True)
    return ASK_QUESTION


# Обработчик команды /day2
async def day2_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Устанавливаем режим
    context.chat_data['current_mode'] = 'day2'
    context.chat_data['system_prompt'] = DAY2_SYSTEM_PROMPT

    await update.message.reply_text(
        "💬 Режим диалога с Yandex GPT в формате JSON\n\n"
        "Просто напишите ваш вопрос, и я передам его Yandex GPT.\n"
        "Бот будет помнить контекст разговора.\n\n"
        "🧹 Для очистки истории используйте /clear\n\n"
        "Задайте ваш вопрос:"
    )
    return ASK_DAY2_QUESTION


async def handle_day2_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений в режиме day2"""
    user_message = update.message.text

    # Проверяем, не является ли это командой
    if user_message.startswith('/'):
        await update.message.reply_text("Диалог прерван. Используйте /day2 чтобы начать заново.")
        return ConversationHandler.END

    await handle_gpt_request(update, context, user_message, store_history=True)
    return ASK_DAY2_QUESTION

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

            if len(chat_history) > 20:
                chat_history = chat_history[-20:]

            context.chat_data['chat_history'] = chat_history

        await typing_msg.delete()
        await update.message.reply_text(
            response.replace('```', '')  # Костыль, я пока не знаю как заставить яндекс гпт убрать эти ```, на выходных подумаю что с этим делать
        )

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
    """Обработка обычных текстовых сообщений"""
    user_text = update.message.text

    if not user_text.startswith('/'):
        logger.info(f"Сообщение от {update.effective_user.id}: {user_text}")
        await update.message.reply_text(
            "🤖 Выберите режим работы:\n\n"
            "🔹 /gpt - Обычный диалог\n"
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
    gpt_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('gpt', gpt_chat)],
        states={
            ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gpt_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Создаем ConversationHandler для режима day2
    day2_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('day2', day2_chat)],
        states={
            ASK_DAY2_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day2_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("about", about))

    # Регистрируем ConversationHandler
    application.add_handler(gpt_conv_handler)
    application.add_handler(day2_conv_handler)

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