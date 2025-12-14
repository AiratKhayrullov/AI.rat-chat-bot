import logging
from typing import List, Dict, Any
import os
import openai
import time
from typing import Optional
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from project.Promts import DEFAULT_SYSTEM_PROMPT, DAY2_SYSTEM_PROMPT, DAY3_SYSTEM_PROMPT
from project.TestCasesForDay8 import test_cases

from project.tg.TelegramHandlers import (
    start,
    help_command,
    about,
    factory_reset,
    cancel,
    error_handler
)

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

# Функция для подсчета токенов (примерная оценка)
def estimate_tokens(text: str) -> int:
    """Примерная оценка количества токенов в тексте"""
    # Примерная оценка: 1 токен ≈ 4 символа для русского текста
    return len(text) // 4

# Константа для сжатия диалога
COMPRESSION_THRESHOLD = 10  # Сжимать каждые N сообщений


# Функция для сжатия истории диалога
async def compress_dialog_history(chat_history: List[Dict[str, str]], context: ContextTypes.DEFAULT_TYPE) -> List[
    Dict[str, str]]:
    """Сжимает историю диалога, заменяя старые сообщения summary"""

    if len(chat_history) <= COMPRESSION_THRESHOLD:
        return chat_history

    # Получаем сохраненные summary из контекста
    compressed_history = context.chat_data.get('compressed_history', [])
    messages_to_compress = chat_history[len(compressed_history):]

    if len(messages_to_compress) < COMPRESSION_THRESHOLD:
        # Еще не набралось достаточно сообщений для сжатия
        return compressed_history + messages_to_compress

    try:
        # Создаем промпт для суммаризации
        summary_prompt = """
        Пожалуйста, создай краткое summary (краткое содержание) следующего диалога.
        Сохрани ключевые моменты, решения, важные детали и контекст для продолжения беседы.
        Summary должно быть на русском языке и содержать примерно 100-200 слов.

        Диалог для суммаризации:
        """

        # Формируем текст для суммаризации
        dialog_text = ""
        for msg in messages_to_compress:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            dialog_text += f"{role}: {msg['content']}\n\n"

        # Вызываем модель для создания summary
        response = yandex_client.chat.completions.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            messages=[
                {"role": "system",
                 "content": "Ты эксперт по суммаризации диалогов. Твоя задача - создавать краткие, информативные summary для продолжения беседы."},
                {"role": "user", "content": f"{summary_prompt}\n\n{dialog_text}"}
            ],
            max_tokens=300,
            temperature=0.3
        )

        summary = response.choices[0].message.content

        # Создаем сообщение-summary для истории
        summary_message = {
            "role": "system",
            "content": f"📚 Сжатая история предыдущего диалога (сохранены ключевые моменты):\n{summary}"
        }

        # Обновляем сжатую историю
        compressed_history.append(summary_message)

        # Сохраняем последнее сообщение ассистента для контекста
        if messages_to_compress and messages_to_compress[-1]["role"] == "assistant":
            compressed_history.append(messages_to_compress[-1])

        # Сохраняем сжатую историю в контексте
        context.chat_data['compressed_history'] = compressed_history

        # Логируем сжатие
        logger.info(
            f"История диалога сжата. Сообщений до сжатия: {len(chat_history)}, после: {len(compressed_history)}")

        return compressed_history

    except Exception as e:
        logger.error(f"Ошибка при сжатии истории диалога: {e}")
        # В случае ошибки возвращаем оригинальную историю
        return chat_history


async def check_compression(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_history = context.chat_data.get('chat_history', [])
    compressed_history = context.chat_data.get('compressed_history', [])

    if not chat_history:
        await update.message.reply_text("📊 История диалога пуста.")
        return

    # Подсчитываем примерное количество токенов
    original_tokens = sum(estimate_tokens(msg["content"]) for msg in chat_history)

    if compressed_history:
        compressed_tokens = sum(estimate_tokens(msg["content"]) for msg in compressed_history)

        # Добавляем токены системного промпта
        system_prompt = context.chat_data.get('system_prompt', DEFAULT_SYSTEM_PROMPT)
        compressed_tokens += estimate_tokens(system_prompt)

        compression_ratio = (1 - compressed_tokens / original_tokens) * 100 if original_tokens > 0 else 0

        stats_text = (
            f"📊 Статистика сжатия истории:\n\n"
            f"• Оригинальных сообщений: {len(chat_history)}\n"
            f"• Сжатых сообщений: {len(compressed_history)}\n"
            f"• Примерно токенов (оригинал): {original_tokens}\n"
            f"• Примерно токенов (сжато): {compressed_tokens}\n"
            f"• Экономия токенов: {compression_ratio:.1f}%\n"
            f"• Порог сжатия: каждые {COMPRESSION_THRESHOLD} сообщений\n\n"
            f"════════════════════════════════\n"
            f"📜 СЖАТАЯ ИСТОРИЯ ДИАЛОГА:\n"
            f"════════════════════════════════\n"
        )

        # Добавляем сжатую историю
        for i, msg in enumerate(compressed_history, 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖" if msg["role"] == "assistant" else "📚"
            role_text = "Пользователь" if msg["role"] == "user" else "Ассистент" if msg["role"] == "assistant" else "Сжатая история"

            # Обрезаем длинные сообщения для отображения
            content_preview = msg["content"]
            if len(content_preview) > 300:
                content_preview = content_preview[:300] + "..."

            stats_text += f"\n{i}. {role_emoji} {role_text}:\n{content_preview}\n"
            stats_text += f"   └─ Примерно токенов: {estimate_tokens(msg['content'])}\n"

    else:
        stats_text = (
            f"📊 История диалога:\n\n"
            f"• Сообщений: {len(chat_history)}\n"
            f"• Примерно токенов: {original_tokens}\n"
            f"• Сжатие еще не применялось\n"
            f"• Порог сжатия: {COMPRESSION_THRESHOLD} сообщений\n\n"
            f"📝 Сжатие будет применено после {COMPRESSION_THRESHOLD - len(chat_history)} сообщений\n\n"
            f"════════════════════════════════\n"
            f"📜 ОРИГИНАЛЬНАЯ ИСТОРИЯ ДИАЛОГА:\n"
            f"════════════════════════════════\n"
        )

        # Добавляем оригинальную историю
        for i, msg in enumerate(chat_history, 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_text = "Пользователь" if msg["role"] == "user" else "Ассистент"

            # Обрезаем длинные сообщения для отображения
            content_preview = msg["content"]
            if len(content_preview) > 200:
                content_preview = content_preview[:200] + "..."

            stats_text += f"\n{i}. {role_emoji} {role_text}:\n{content_preview}\n"
            stats_text += f"   └─ Примерно токенов: {estimate_tokens(msg['content'])}\n"

    # Разбиваем сообщение на части, если оно слишком длинное
    max_message_length = 4000  # Лимит Telegram
    if len(stats_text) > max_message_length:
        # Разбиваем на части
        parts = []
        current_part = ""
        lines = stats_text.split('\n')

        for line in lines:
            if len(current_part) + len(line) + 1 > max_message_length:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'

        if current_part:
            parts.append(current_part)

        # Отправляем первую часть с информацией
        await update.message.reply_text(parts[0])

        # Отправляем остальные части
        for part in parts[1:]:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(stats_text)

######################################################################################################
######################################################################################################

async def test_token_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧪 Начинаю тестирование использования токенов...")

    results: List[Dict[str, Any]] = []
    data_for_analytics = []

    for test_case in test_cases:
        try:
            await update.message.reply_text(f"\n{test_case['name']}\nОписание: {test_case['description']}")

            # Замер времени
            start_time = time.time()

            # Подготавливаем сообщения
            messages = [
                {"role": "system", "content": "Ты полезный ассистент"},
                {"role": "user", "content": test_case['prompt']}
            ]

            response = yandex_client.chat.completions.create(
                model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE
            )

            end_time = time.time()
            response_time = end_time - start_time

            # Получаем информацию о токенах из ответа API
            completion = response
            input_tokens = completion.usage.prompt_tokens
            output_tokens = completion.usage.completion_tokens
            total_tokens = completion.usage.total_tokens

            # Проверяем, был ли ответ обрезан
            response_text = completion.choices[0].message.content
            was_truncated = response.choices[0].finish_reason == "length"

            # Рассчитываем процент использования лимита
            limit_usage_percent = (output_tokens / MAX_TOKENS) * 100

            # Рассчитываем стоимость
            price_info = MODEL_PRICES.get("yandexgpt/latest")
            cost = (input_tokens * price_info["input"] / 1000) + (output_tokens * price_info["output"] / 1000)

            result = {
                "name": test_case['name'],
                "description": test_case['description'],
                "success": True,
                "response_time": response_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "limit_usage_percent": limit_usage_percent,
                "was_truncated": was_truncated,
                "cost": cost,
                "response_preview": response_text[:200] + "..." if len(response_text) > 200 else response_text,
                "max_tokens_limit": MAX_TOKENS
            }


            results.append(result)

            status_emoji = "⚠️" if result['was_truncated'] else "✅"

            await update.message.reply_text(
                f"{status_emoji} Результат:\n"
                f"⏱ Время: {result['response_time']:.2f} сек\n"
                f"🔢 Токены запроса: {result['input_tokens']}\n"
                f"🔢 Токены ответа: {result['output_tokens']}\n"
                f"🔢 Всего токенов: {result['total_tokens']}\n"
                f"💰 Стоимость: {cost:.6f} ₽\n"
                f"📊 Использование лимита: {result['limit_usage_percent']:.1f}%\n"
                f"{'⚠️ Ответ был обрезан' if result['was_truncated'] else '✅ Ответ полный'}\n"
                f"📝 Предпросмотр ответа:\n{result['response_preview']}"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Критическая ошибка при выполнении теста: {str(e)}")

    # Анализ и сравнение результатов
    await update.message.reply_text("\n📊 СРАВНИТЕЛЬНЫЙ АНАЛИЗ РЕЗУЛЬТАТОВ:")

    analysis_text = "🔍 Выводы по тестированию токенов:\n\n"

    # Анализируем каждый тест
    for i, result in enumerate(results):
        analysis_text += f"{result['name']}:\n"

        analysis_text += (
            f"  • Токены: {result['input_tokens']} (вх) + {result['output_tokens']} (вых) = {result['total_tokens']}\n"
            f"  • Время: {result['response_time']:.2f} сек\n"
            f"  • Использование лимита: {result['limit_usage_percent']:.1f}%\n"
            f"  • Стоимость: {result['cost']:.6f} ₽\n"
            f"  • Статус: {'⚠️ Обрезан' if result['was_truncated'] else '✅ Полный'}\n"
        )

        analysis_text += "\n"


    await update.message.reply_text(analysis_text)

    await update.message.reply_text("\n🤖 ЗАПРАШИВАЮ ГЛУБОКИЙ АНАЛИЗ У МОДЕЛИ...")

    try:
        ai_analysis = await perform_ai_analysis(analysis_text)
        await update.message.reply_text(f"📊 РЕЗУЛЬТАТЫ АНАЛИЗА МОДЕЛЬЮ:\n\n{ai_analysis}")
    except Exception as e:
        logger.error(f"Ошибка при анализе моделью: {e}")
        await update.message.reply_text(f"⚠️ Не удалось получить анализ от модели: {str(e)}")


async def perform_ai_analysis(analysis_text: str) -> str:

    # Формируем детальный промпт для анализа
    analysis_prompt = """Ты - эксперт по языковым моделям. Проанализируй результаты тестирования работы с токенами.

ДАННЫЕ ТЕСТА:
Были протестированы 3 типа запросов:
1. Короткий запрос
2. Средний запрос
3. Длинный запрос

ЛИМИТ МОДЕЛИ: {max_tokens} токенов

РЕЗУЛЬТАТЫ:
{test_results}

Выполни глубокий анализ на основе вышеизложенных данных о том, как меняется поведение модели в зависимости от токенов

""".format(
        max_tokens=MAX_TOKENS,
        test_results= analysis_text
    )

    try:
        response = yandex_client.chat.completions.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            messages=[
                {
                    "role": "system",
                    "content": """Ты опытный AI-инженер и исследователь языковых моделей. 
Ты специализируешься на оптимизации использования токенов и анализе производительности LLM.
Твоя задача - предоставить глубокий, практический анализ с конкретными рекомендациями."""
                },
                {"role": "user", "content": analysis_prompt}
            ],
            max_tokens=5000,
            temperature=0.7
        )

        return response.choices[0].message.content

    except Exception as e:
        raise Exception(f"Ошибка при анализе моделью: {str(e)}")


def format_test_results_for_analysis(results: List[Dict[str, Any]]) -> str:
    """Форматирует результаты тестирования для анализа моделью"""

    formatted = ""

    for result in results:
        formatted += f"ТЕСТ: {result['name']}\n"
        formatted += f"Описание: {result['description']}\n"
        formatted += f"Статус: {'УСПЕХ' if result.get('success', False) else 'ОШИБКА'}\n"

        formatted += f"\nМЕТРИКИ:\n"
        formatted += f"• Время ответа: {result['response_time']:.2f} сек\n"
        formatted += f"• Токены запроса: {result['input_tokens']}\n"
        formatted += f"• Токены ответа: {result['output_tokens']}\n"
        formatted += f"• Всего токенов: {result['total_tokens']}\n"
        formatted += f"• Использование лимита: {result['limit_usage_percent']:.1f}%\n"
        formatted += f"• Ответ обрезан: {'ДА' if result['was_truncated'] else 'НЕТ'}\n"
        formatted += f"• Причина завершения: {'length (обрезка)' if result['was_truncated'] else 'stop (полный)'}\n"

        formatted += f"\nОТВЕТ: {result['input_tokens']}\n"

    return formatted

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
        cost_display = f"{result['cost']:.3f}".rstrip('0').rstrip('.') + " ₽"
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

# Модифицированная функция handle_gpt_request
async def handle_gpt_request(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_message: str,
        store_history: bool = False
):
    typing_msg = await update.message.reply_text("🤔 Думаю...")

    try:
        # Получаем текущий системный промпт
        system_prompt = context.chat_data.get('system_prompt', DEFAULT_SYSTEM_PROMPT)

        # Получаем историю диалога
        chat_history = context.chat_data.get('chat_history', [])

        # Сжимаем историю при необходимости
        compressed_history = await compress_dialog_history(chat_history, context)

        # Подготавливаем финальную историю для отправки
        final_history = []

        # Добавляем системный промпт
        final_history.append({"role": "system", "content": system_prompt})

        # Добавляем сжатую историю
        final_history.extend(compressed_history)

        # Добавляем текущее сообщение пользователя
        final_history.append({"role": "user", "content": user_message})

        # Получаем ответ
        response = await get_yandex_gpt_response(
            user_message=user_message,
            system_prompt=system_prompt,
            chat_history=final_history[1:]  # Пропускаем первый системный промпт, т.к. он уже в истории
        )

        # Обновляем историю диалога, если нужно
        if store_history:
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": response})

            if len(chat_history) > 50:
                chat_history = chat_history[-50:]

            context.chat_data['chat_history'] = chat_history

        # Добавляем информацию о сжатии в ответ
        compression_info = ""
        if 'compressed_history' in context.chat_data:
            original_count = len(chat_history)
            compressed_count = len(context.chat_data['compressed_history'])
            compression_info = f"\n\n🔍 История диалога сжата: {original_count} → {compressed_count} сообщений"

        await typing_msg.delete()

        if context.chat_data.get('current_mode') != 'day2':
            await update.message.reply_text(response + compression_info)
        else:
            await update.message.reply_text(response.replace('```', '') + compression_info)

    except Exception as e:
        await typing_msg.delete()
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(
            f"⚠️ Произошла ошибка при обращении к Yandex GPT:\n\n{str(e)}"
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
    application.add_handler(CommandHandler("test_models", test_models))
    application.add_handler(CommandHandler("test_tokens", test_token_usage))
    application.add_handler(CommandHandler("compression_stats", check_compression))

    # Регистрируем ConversationHandler
    application.add_handler(day1_conv_handler)
    application.add_handler(day2_conv_handler)
    application.add_handler(day3_conv_handler)

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