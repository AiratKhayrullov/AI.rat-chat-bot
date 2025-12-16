import os
from dotenv import load_dotenv
from typing import Dict, Any

# Загружаем переменные из .env файла
load_dotenv()

# ============================================================================
# НАСТРОЙКИ ИЗ .ENV ФАЙЛА
# ============================================================================

# MCP Server Configuration
MCP_SERVER_URL = os.getenv('MCP_SERVER_URL')  # Замените на реальный URL

# Конфигурация Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Конфигурация Yandex Cloud
YANDEX_CLOUD_FOLDER = os.getenv('YANDEX_CLOUD_FOLDER')
YANDEX_CLOUD_API_KEY = os.getenv('YANDEX_CLOUD_API_KEY')
YANDEX_CLOUD_MODEL = os.getenv('YANDEX_CLOUD_MODEL')

# Параметры модели
MAX_TOKENS = int(os.getenv('MAX_TOKENS', 2000))
TEMPERATURE = float(os.getenv('TEMPERATURE', 0.7))

# ============================================================================
# КОНСТАНТЫ МОДЕЛЕЙ YANDEX GPT
# ============================================================================

YANDEX_MODELS = [
    "yandexgpt-lite/latest",  # YandexGPT 5 Lite
    "yandexgpt/latest",       # YandexGPT 5 Pro
    "yandexgpt/rc",           # YandexGPT 5.1 Pro
    "aliceai-llm/latest",     # Alice AI LLM
]

MODEL_NAMES = {
    "yandexgpt-lite/latest": "YandexGPT 5 Lite",
    "yandexgpt/latest": "YandexGPT 5 Pro",
    "yandexgpt/rc": "YandexGPT 5.1 Pro",
    "aliceai-llm/latest": "Alice AI LLM",
}

MODEL_PRICES = {
    "yandexgpt-lite/latest": {"input": 0.10, "output": 0.10},    # 0,10 ₽ за 1K токенов
    "yandexgpt/latest": {"input": 0.60, "output": 0.60},         # 0,60 ₽ за 1K токенов
    "yandexgpt/rc": {"input": 0.20, "output": 0.20},            # 0,20 ₽ за 1K токенов
    "aliceai-llm/latest": {"input": 0.25, "output": 1.00},      # 0,25 ₽ ввод, 1,00 ₽ вывод
}

# ============================================================================
# НАСТРОЙКИ ДИАЛОГА И СЖАТИЯ
# ============================================================================

# Состояния для ConversationHandler
DAY_1_STATE = 1
DAY_2_STATE = 2
DAY_3_STATE = 3

# Константа для сжатия диалога
COMPRESSION_THRESHOLD = 10  # Сжимать каждые N сообщений

# Максимальная длина истории диалога
MAX_HISTORY_LENGTH = 50

# Максимальная длина сообщения для Telegram (в символах)
MAX_MESSAGE_LENGTH = 4000

# ============================================================================
# НАСТРОЙКИ ЛОГИРОВАНИЯ
# ============================================================================

LOGGING_CONFIG = {
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'level': 'INFO'
}

# ============================================================================
# URL И API КОНФИГУРАЦИЯ
# ============================================================================

YANDEX_API_BASE_URL = "https://llm.api.cloud.yandex.net/v1"

# ============================================================================
# ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ КОНФИГУРАЦИИ
# ============================================================================

def get_model_config() -> Dict[str, Any]:
    return {
        'model': f"gpt://{YANDEX_CLOUD_FOLDER}/{YANDEX_CLOUD_MODEL}",
        'max_tokens': MAX_TOKENS,
        'temperature': TEMPERATURE
    }

def get_all_config() -> Dict[str, Any]:
    return {
        'telegram_bot_token': TELEGRAM_BOT_TOKEN,
        'yandex_cloud_folder': YANDEX_CLOUD_FOLDER,
        'yandex_cloud_api_key': YANDEX_CLOUD_API_KEY,
        'yandex_cloud_model': YANDEX_CLOUD_MODEL,
        'max_tokens': MAX_TOKENS,
        'temperature': TEMPERATURE,
        'model_names': MODEL_NAMES,
        'model_prices': MODEL_PRICES,
        'yandex_models': YANDEX_MODELS,
        'compression_threshold': COMPRESSION_THRESHOLD,
        'max_history_length': MAX_HISTORY_LENGTH,
        'max_message_length': MAX_MESSAGE_LENGTH
    }

def print_config_summary():
    """Выводит сводку конфигурации"""
    print("=" * 50)
    print("🤖 Конфигурация телеграм-бота с Yandex GPT")
    print("=" * 50)
    print(f"📊 Модель: {YANDEX_CLOUD_MODEL}")
    print(f"🔥 Температура: {TEMPERATURE}")
    print(f"🔢 Макс. токенов: {MAX_TOKENS}")
    print(f"📁 Yandex Cloud Folder: {YANDEX_CLOUD_FOLDER}")
    print(f"🔑 API Key: {'Установлен' if YANDEX_CLOUD_API_KEY else 'Отсутствует'}")
    print(f"🤖 Telegram Token: {'Установлен' if TELEGRAM_BOT_TOKEN else 'Отсутствует'}")
    print("=" * 50)