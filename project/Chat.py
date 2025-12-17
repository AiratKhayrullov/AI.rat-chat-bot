import logging
import openai
import time
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import json
import requests
from typing import List, Dict, Any
import aiohttp
import asyncio

from project.Config import (
    TELEGRAM_BOT_TOKEN,
    YANDEX_CLOUD_FOLDER,
    YANDEX_CLOUD_API_KEY,
    YANDEX_CLOUD_MODEL,
    MAX_TOKENS,
    TEMPERATURE,
    YANDEX_MODELS,
    MODEL_NAMES,
    MODEL_PRICES,
    DAY_1_STATE,
    DAY_2_STATE,
    DAY_3_STATE,
    DAY_12_MCP_STATE,
    COMPRESSION_THRESHOLD,
    MAX_HISTORY_LENGTH,
    MAX_MESSAGE_LENGTH,
    MCP_SERVER_URL,
    YANDEX_API_BASE_URL,
    LOGGING_CONFIG,
    print_config_summary
)

from project.Promts import (
    DEFAULT_SYSTEM_PROMPT,
    DAY2_SYSTEM_PROMPT,
    DAY3_SYSTEM_PROMPT,
)


from project.tg.TelegramHandlers import (
    start,
    help_command,
    about,
    factory_reset,
    cancel,
    error_handler
)

# Настраиваем логирование
logging.basicConfig(**LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Инициализация клиента Yandex GPT
yandex_client = openai.OpenAI(
    api_key=YANDEX_CLOUD_API_KEY,
    base_url=YANDEX_API_BASE_URL,
    project=YANDEX_CLOUD_FOLDER
)

# Создаем клиента
mcp_client = openai.OpenAI(
    api_key=YANDEX_CLOUD_API_KEY,
    base_url="https://rest-assistant.api.cloud.yandex.net/v1",
    project=YANDEX_CLOUD_FOLDER
)


######################################################################################################
# MCP Functions
######################################################################################################
async def get_mcp_tools() -> List[Dict[str, Any]]:
    """
    Получает список доступных инструментов от MCP-сервера
    """
    try:
        # Используем Responses API для получения инструментов MCP
        response = mcp_client.responses.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            input=[
                {
                    "role": "user",
                    "content": "Покажи список доступных инструментов"
                }
            ],
            # Указываем MCP-сервер
            tools=[
                {
                    "server_label": "airat-mcp",
                    "server_url": MCP_SERVER_URL,
                    "type": "mcp",
                    "metadata": {
                        "description": "MCP сервер с доступными инструментами"
                    }
                }
            ]
        )

        # Парсим ответ для получения информации об инструментах
        tools_info = []

        # Проверяем, есть ли информация об инструментах в ответе
        if hasattr(response, 'output_text'):
            # Если есть текстовый ответ с описанием инструментов
            tools_info.append({
                "name": "mcp_tools",
                "description": response.output_text[:1000] + "..." if len(
                    response.output_text) > 1000 else response.output_text,
                "type": "mcp",
                "server_url": MCP_SERVER_URL
            })

        return tools_info

    except Exception as e:
        logger.error(f"Ошибка при получении инструментов MCP: {e}")
        return []


async def get_mcp_tools_direct() -> List[Dict[str, Any]]:
    """
    Прямое получение инструментов от MCP-сервера через HTTP запрос
    """
    try:
        # Проверяем доступность MCP-сервера
        response = requests.get(f"{MCP_SERVER_URL}/.well-known/mcp.json", timeout=10)

        if response.status_code == 200:
            mcp_info = response.json()
            tools = []

            if "tools" in mcp_info:
                for tool_name, tool_info in mcp_info["tools"].items():
                    tools.append({
                        "name": tool_name,
                        "description": tool_info.get("description", "Описание отсутствует"),
                        "input_schema": tool_info.get("inputSchema", {}),
                        "type": "mcp"
                    })

            return tools
        else:
            logger.warning(f"MCP сервер не вернул инструменты. Status: {response.status_code}")
            return []

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка подключения к MCP-серверу: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка при обработке ответа MCP: {e}")
        return []


async def test_mcp_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Тестирует подключение к MCP-серверу и показывает доступные инструменты
    """
    await update.message.reply_text("🔌 Тестирую подключение к MCP-серверу...")

    try:
        # Пробуем прямое подключение
        await update.message.reply_text(f"📡 Проверяю MCP-сервер: {MCP_SERVER_URL}")

        direct_tools = await get_mcp_tools_direct()

        if direct_tools:
            response_text = "✅ MCP-сервер доступен!\n\n"
            response_text += "📋 Доступные инструменты (прямое подключение):\n\n"

            for i, tool in enumerate(direct_tools, 1):
                response_text += f"{i}. 🔧 **{tool['name']}**\n"
                response_text += f"   📝 Описание: {tool.get('description', 'Нет описания')}\n"

                if 'input_schema' in tool and tool['input_schema']:
                    response_text += f"   📋 Параметры: {json.dumps(tool['input_schema'], ensure_ascii=False, indent=2)}\n"

                response_text += "\n"

            await update.message.reply_text(response_text)
        else:
            # Пробуем через Responses API
            await update.message.reply_text("🔄 Пробую получить инструменты через Responses API...")

            api_tools = await get_mcp_tools()

            if api_tools:
                response_text = "✅ MCP-инструменты получены через Responses API!\n\n"
                response_text += "📋 Доступные инструменты:\n\n"

                for i, tool in enumerate(api_tools, 1):
                    response_text += f"{i}. 🔧 **{tool['name']}**\n"
                    response_text += f"   📝 Описание: {tool.get('description', 'Нет описания')}\n"
                    response_text += f"   🌐 Сервер: {tool.get('server_url', 'Не указан')}\n\n"

                await update.message.reply_text(response_text)
            else:
                await update.message.reply_text(
                    "❌ Не удалось получить инструменты MCP.\n"
                    "Проверьте:\n"
                    "1. URL MCP-сервера в конфигурации\n"
                    "2. Доступность MCP-сервера\n"
                    "3. API ключ с правильной областью действия\n\n"
                    f"Текущий URL: {MCP_SERVER_URL}"
                )

    except Exception as e:
        logger.error(f"Ошибка при тестировании MCP: {e}")
        await update.message.reply_text(f"❌ Критическая ошибка при тестировании MCP: {str(e)}")


async def use_mcp_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Использование инструмента MCP через бота
    """
    user_message = update.message.text

    if not user_message or user_message.startswith('/'):
        await update.message.reply_text(
            "🔧 Использование MCP инструментов\n\n"
            "Доступные команды:\n"
            "/mcp_tools - Показать доступные инструменты\n"
            "/mcp_test - Протестировать подключение к MCP\n\n"
            "Чтобы использовать инструмент, напишите его название и параметры.\n"
            "Например: 'crm_lookup Иван Иванов'"
        )
        return

    await update.message.reply_text("🔧 Использую MCP инструмент...")

    try:
        # Используем Responses API для вызова MCP инструмента
        response = yandex_client.responses.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            input=[
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            tools=[
                {
                    "server_label": "mcp_tools",
                    "server_url": MCP_SERVER_URL,
                    "type": "mcp",
                    "metadata": {
                        "description": "Различные инструменты через MCP"
                    }
                }
            ]
        )

        if hasattr(response, 'output_text'):
            await update.message.reply_text(f"✅ Результат MCP инструмента:\n\n{response.output_text}")
        else:
            await update.message.reply_text("ℹ️ MCP инструмент выполнен, но не вернул текстовый результат.")

    except Exception as e:
        logger.error(f"Ошибка при использовании MCP инструмента: {e}")
        await update.message.reply_text(f"❌ Ошибка при использовании MCP инструмента: {str(e)}")

######################################################################################################
######################################################################################################

# Функция для подсчета токенов (примерная оценка)
def estimate_tokens(text: str) -> int:
    """Примерная оценка количества токенов в тексте"""
    # Примерная оценка: 1 токен ≈ 4 символа для русского текста
    return len(text) // 4


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
    if len(stats_text) > MAX_MESSAGE_LENGTH:
        # Разбиваем на части
        parts = []
        current_part = ""
        lines = stats_text.split('\n')

        for line in lines:
            if len(current_part) + len(line) + 1 > MAX_MESSAGE_LENGTH:
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


# Обработчик команды /day12_mcp
async def day12_mcp_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data['current_mode'] = 'day12_mcp'
    context.chat_data['system_prompt'] = DEFAULT_SYSTEM_PROMPT

    await update.message.reply_text(
        "🔧 **Режим диалога с Yandex GPT и MCP-инструментами**\n\n"
        "Я буду использовать поисковые инструменты для ответов на ваши вопросы.\n"
        "Просто напишите ваш запрос.\n\n"
    )
    return DAY_12_MCP_STATE

# Обработчик сообщений в режиме MCP
async def handle_day12_mcp_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if user_message.startswith('/'):
        await update.message.reply_text("Диалог прерван. Используйте /day1_mcp чтобы начать заново.")
        return ConversationHandler.END

    await handle_gpt_request_mcp(update, context, user_message, store_history=True)
    return DAY_12_MCP_STATE

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
            chat_history=final_history[1:]
        )

        # Обновляем историю диалога, если нужно
        if store_history:
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": response})

            if len(chat_history) > MAX_HISTORY_LENGTH:
                chat_history = chat_history[-MAX_HISTORY_LENGTH:]

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


async def handle_gpt_request_mcp(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_message: str,
        store_history: bool = False
):
    typing_msg = None
    try:
        typing_msg = await update.message.reply_text("🔍 Анализирую запрос и подбираю инструменты...")

        # Получаем системный промпт и историю
        system_prompt = context.chat_data.get('system_prompt', DEFAULT_SYSTEM_PROMPT)
        chat_history = context.chat_data.get('chat_history', [])

        # Подготавливаем входные данные
        messages = []
        if chat_history:
            messages.extend(chat_history)
        else:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        logger.info(f"MCP запрос: {user_message}")

        # Шаг 1: Получаем ответ с инструментами
        response = mcp_client.responses.create(
            model=f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
            input=messages,
            tools=[
                {
                    "web_search": {
                        "filters": {
                            "allowed_domains": [
                                "habr.ru"
                            ]
                        },
                        "user_location": {
                            "region": "213",
                        }
                    }
                },
            ],
            parallel_tool_calls=True
        )

        logger.info(f"Статус ответа: {response.status}")
        logger.info(f"Тип ответа: {type(response)}")

        # Шаг 2: Ищем запросы на выполнение инструментов
        tool_results = []

        for item in response.output:
            # Если это запрос на выполнение инструмента
            if hasattr(item, 'type') and item.type == 'mcp_approval_request':
                logger.info(f"Найден запрос на выполнение инструмента: {item.name}")

                # Извлекаем аргументы
                if hasattr(item, 'arguments'):
                    try:
                        arguments = json.loads(item.arguments)
                        logger.info(f"Аргументы инструмента: {arguments}")

                        # Выполняем инструмент напрямую через MCP сервер
                        tool_result = await execute_mcp_tool_directly(
                            tool_name=item.name,
                            arguments=arguments,
                            server_url=MCP_SERVER_URL
                        )

                        if tool_result:
                            tool_results.append({
                                'tool': item.name,
                                'result': tool_result
                            })
                            logger.info(f"Результат инструмента {item.name} получен")

                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга аргументов: {e}")
                    except Exception as e:
                        logger.error(f"Ошибка выполнения инструмента: {e}")

        # Шаг 3: Формируем финальный ответ
        final_response = ""

        if tool_results:
            # Формируем сводку результатов
            results_text = "🔍 **Результаты поиска:**\n\n"
            for i, result in enumerate(tool_results, 1):
                results_text += f"**{i}. {result['tool']}:**\n"
                # Обрезаем слишком длинные результаты
                result_text = result['result'][:2000] + "..." if len(result['result']) > 2000 else result['result']
                results_text += f"{result_text}\n\n"

        else:
            # Если нет результатов инструментов, используем обычный ответ
            if hasattr(response, 'output_text') and response.output_text:
                final_response = response.output_text
            else:
                final_response = "Не удалось найти информацию по вашему запросу. Попробуйте переформулировать вопрос."

        # Шаг 4: Обновляем историю (БЕЗ роли 'tool')
        if store_history and final_response:
            if not chat_history:
                chat_history = []
            chat_history.append({"role": "user", "content": user_message})
            chat_history.append({"role": "assistant", "content": final_response})
            if len(chat_history) > MAX_HISTORY_LENGTH:
                chat_history = chat_history[-MAX_HISTORY_LENGTH:]
            context.chat_data['chat_history'] = chat_history

        # Удаляем сообщение "Думаю..."
        if typing_msg:
            try:
                await typing_msg.delete()
            except:
                pass

        # Отправляем ответ
        if final_response.strip():
            await update.message.reply_text(final_response[:4000])
        else:
            await update.message.reply_text("🤔 Не удалось получить ответ. Попробуйте еще раз.")

    except Exception as e:
        logger.error(f"Ошибка при запросе с MCP: {e}", exc_info=True)

        if typing_msg:
            try:
                await typing_msg.delete()
            except:
                pass

        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")





async def execute_mcp_tool_directly(tool_name: str, arguments: dict, server_url: str) -> str:
    """
    Выполняет инструмент MCP напрямую через HTTP запрос
    """
    try:
        logger.info(f"Выполняю инструмент {tool_name} с аргументами: {arguments}")

        # Формируем URL для инструмента
        tool_url = f"{server_url}/tools/{tool_name}"

        # Подготавливаем тело запроса
        request_body = arguments.get('body_application_json', {})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    tool_url,
                    json=request_body,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
            ) as response:
                if response.status == 200:
                    result = await response.text()
                    logger.info(f"Успешный ответ от инструмента {tool_name}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка инструмента {tool_name}: {response.status} - {error_text}")
                    return f"Ошибка инструмента {tool_name}: {error_text}"

    except asyncio.TimeoutError:
        logger.error(f"Таймаут при выполнении инструмента {tool_name}")
        return f"Таймаут при выполнении {tool_name}"
    except Exception as e:
        logger.error(f"Ошибка выполнения инструмента {tool_name}: {e}")
        return f"Ошибка: {str(e)}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if not user_text.startswith('/'):
        logger.info(f"Сообщение от {update.effective_user.id}: {user_text}")
        await update.message.reply_text(
            "🤖 Выберите режим работы:\n\n"
            "🔹 /day1 - Обычный диалог\n"
            "🔹 /day2 - Диалог с JSON ответом\n"
            "🔹 /day12_mcp - Диалог с JSON ответом\n"
            "🔹 /compression_stats - Показать статистику сжатия истории диалога\n"
            "🔹 /test_models - Тестирование моделей\n"
            "🔹 /help - Справка по командам"
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
        entry_points=[CommandHandler('day3', day3_chat)],
        states={
            DAY_3_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day3_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Создаем ConversationHandler для режима day1 с MCP
    day12_mcp_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('day12_mcp', day12_mcp_chat)],
        states={
            DAY_12_MCP_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day12_mcp_dialog)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(day12_mcp_conv_handler)

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", factory_reset))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("compression_stats", check_compression))

    # Регистрируем MCP обработчики
    application.add_handler(CommandHandler("mcp_tools", test_mcp_tools))
    application.add_handler(CommandHandler("mcp_test", test_mcp_tools))


    # Регистрируем ConversationHandler
    application.add_handler(day1_conv_handler)
    application.add_handler(day2_conv_handler)
    application.add_handler(day3_conv_handler)

    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("Бот запущен...")
    print_config_summary()

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == '__main__':
    main()