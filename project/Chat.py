import logging
import os
import openai
import time
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

YANDEX_MODELS = [
    "yandexgpt-lite/latest", # YandexGPT 5 Lite
    "yandexgpt/latest", # YandexGPT 5 Pro
    "yandexgpt/rc", # YandexGPT 5.1 Pro
    "aliceai-llm/latest", # Alice AI LLM
]

MODEL_NAMES = {
    "yandexgpt-lite/latest": "YandexGPT 5 Lite",
    "yandexgpt/latest": "YandexGPT 5 Pro",
    "yandexgpt/rc": "YandexGPT 5.1 Pro",
    "aliceai-llm/latest": "Alice AI LLM",
}

MODEL_PRICES = {
    "yandexgpt-lite/latest": {"input":0.10, "output": 0.10},    # 0,10 ₽ за 1K токенов
    "yandexgpt/latest": {"input": 0.60, "output": 0.60},    # 0,60 ₽ за 1K токенов
    "yandexgpt/rc": {"input": 0.20, "output": 0.20},    # 0,20 ₽ за 1K токенов
    "aliceai-llm/latest": {"input": 0.25, "output": 1.00},  # 0,25 ₽ ввод, 1,00 ₽ вывод
}

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
        "/day3 - Режим редактора писем (день 3)\n"
        "/test_models - Тестирование моделей (день 7)\n"  # Добавлена новая команда
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
/day3 - Редактор писем с автостопом
/test_models - Сравнение разных моделей Yandex GPT
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

async def test_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_prompt = "Объясни, что такое квантовая запутанность, простыми словами. Приведи аналогию из повседневной жизни."

    await update.message.reply_text(
        "🧪 Начинаю тестирование разных моделей Yandex GPT...\n"
        f"Тестовый промпт: '{test_prompt}'\n\n"
        f"Тестирую модели: {', '.join(MODEL_NAMES.values())}\n"
    )

    results = []

    for model_name in YANDEX_MODELS:
        try:
            await update.message.reply_text(f"🚀 Тестирую модель: {MODEL_NAMES[model_name]}...")

            # Замер времени
            start_time = time.time()

            logger.info(f"Вызов API: model={model_name}, folder={YANDEX_CLOUD_FOLDER}")

            # Делаем запрос
            response = yandex_client.chat.completions.create(
                model=f"gpt://{YANDEX_CLOUD_FOLDER}/{model_name}",
                messages=[
                    {"role": "system", "content": "Ты полезный ассистент"},
                    {"role": "user", "content": test_prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE
            )

            end_time = time.time()
            response_time = end_time - start_time

            # Получаем информацию о токенах
            completion = response
            input_tokens = completion.usage.prompt_tokens
            output_tokens = completion.usage.completion_tokens
            total_tokens = completion.usage.total_tokens

            # Рассчитываем стоимость
            price_info = MODEL_PRICES.get(model_name, {"input": 0, "output": 0})
            cost = (input_tokens * price_info["input"] / 1000) + (output_tokens * price_info["output"] / 1000)

            result = {
                "model": model_name,
                "model_display_name": MODEL_NAMES[model_name],
                "time": response_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
                "response": completion.choices[0].message.content[:MAX_TOKENS] + "..." if len(
                    completion.choices[0].message.content) > MAX_TOKENS else completion.choices[0].message.content
            }

            results.append(result)

            # Отправляем промежуточный результат
            await update.message.reply_text(
                f"✅ Модель: {MODEL_NAMES[model_name]}\n"
                f"⏱ Время: {response_time:.2f} сек\n"
                f"🔢 Токены: {input_tokens}(вх) + {output_tokens}(вых) = {total_tokens}\n"
                f"💰 Стоимость: {cost:.6f} ₽\n"
                f"📝 Ответ:\n{result['response']}"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при тестировании модели {MODEL_NAMES[model_name]}: {str(e)}")
            results.append({
                "model": model_name,
                "model_display_name": MODEL_NAMES[model_name],
                "error": str(e)
            })

    # Сравниваем результаты
    await update.message.reply_text("📊 ИТОГОВОЕ СРАВНЕНИЕ МОДЕЛЕЙ:")

    comparison_text = "🔍 Сравнение по времени:\n"
    for result in sorted(results, key=lambda x: x.get('time', 999)):
        if 'error' not in result:
            comparison_text += f"• {result['model_display_name']}: {result['time']:.2f} сек\n"

    comparison_text += "\n🔢 Сравнение по токенам:\n"
    for result in sorted(results, key=lambda x: x.get('total_tokens', 999)):
        if 'error' not in result:
            comparison_text += f"• {result['model_display_name']}: {result['total_tokens']} токенов\n"

    comparison_text += "\n💰 Сравнение по стоимости:\n"
    for result in sorted(results, key=lambda x: x.get('cost', 999)):
        if 'error' not in result:
            # Форматируем стоимость для красивого отображения в Telegram
            if result['cost'] < 0.001:
                cost_display = f"{result['cost']:.8f}".rstrip('0').rstrip('.') + " ₽"
            elif result['cost'] < 0.01:
                cost_display = f"{result['cost']:.6f}".rstrip('0').rstrip('.') + " ₽"
            elif result['cost'] < 0.1:
                cost_display = f"{result['cost']:.4f}".rstrip('0').rstrip('.') + " ₽"
            elif result['cost'] < 1:
                cost_display = f"{result['cost']:.3f}".rstrip('0').rstrip('.') + " ₽"
            else:
                cost_display = f"{result['cost']:.2f} ₽"

            comparison_text += f"• {result['model_display_name']}: {cost_display}\n"

    await update.message.reply_text(comparison_text)

    # Отправляем данные в AI для анализа
    await send_to_ai_for_analysis(update, results)


async def send_to_ai_for_analysis(update: Update, results: list):

    # Формируем промпт для анализа
    analysis_prompt = """
    Проанализируйте результаты тестирования разных моделей Yandex GPT по следующим параметрам:
    1. Время ответа
    2. Количество токенов (входных, выходных, общих)
    3. Стоимость выполнения запроса (не одного токена, а всю сумму итоговую)
    4. Качество ответов

    Выведите сравнительный анализ и рекомендации по выбору модели для разных сценариев использования.

    Результаты тестирования:
    """

    for result in results:
        if 'error' not in result:

            # Форматируем стоимость для лучшей читаемости
            if result['cost'] < 0.001:
                cost_display = f"{result['cost']:.8f}".rstrip('0').rstrip('.') + " ₽"
            elif result['cost'] < 0.01:
                cost_display = f"{result['cost']:.6f}".rstrip('0').rstrip('.') + " ₽"
            else:
                cost_display = f"{result['cost']:.4f}".rstrip('0').rstrip('.') + " ₽"
            analysis_prompt += f"""
            Модель: {result['model_display_name']}
            • Время ответа: {result['time']:.2f} секунд
            • Токены: входные={result['input_tokens']}, выходные={result['output_tokens']}, всего={result['total_tokens']}
            • Стоимость: {cost_display}
            • Ответ: {result['response']}
            """
        else:
            analysis_prompt += f"""
            Модель: {result['model_display_name']}
            • ОШИБКА: {result['error']}
            """

    analysis_prompt += """
    Проанализируйте и предоставьте:
    1. Рейтинг моделей по скорости
    2. Рейтинг моделей по экономичности (не одного токена, а всю сумму итоговую)
    3. Рейтинг моделей по качеству ответов (на основе содержания ответов)
    4. Общие рекомендации для разных use-cases

    Предоставьте ответ в структурированном виде с обоснованием.
    """

    await update.message.reply_text("🤖 Запрашиваю анализ результатов у AI...")

    try:
        # Используем основную модель для анализа
        response = yandex_client.chat.completions.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            messages=[
                {"role": "system",
                 "content": "Ты опытный аналитик в области ИИ. Ты анализируешь результаты тестирования моделей и даешь профессиональные рекомендации."},
                {"role": "user", "content": analysis_prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )

        analysis_result = response.choices[0].message.content

        await update.message.reply_text(
            "📈 РЕЗУЛЬТАТЫ АНАЛИЗА AI:\n\n" + analysis_result
        )

    except Exception as e:
        logger.error(f"Ошибка при анализе результатов: {e}")
        await update.message.reply_text(
            f"⚠️ Не удалось получить анализ от AI: {str(e)}"
        )

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
            "🔹 /test_models - Тестирование моделей\n"  # Добавлена новая команда
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
            DAY_3_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day3_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", factory_reset))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("test_models", test_models))  # Добавлена новая команда

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