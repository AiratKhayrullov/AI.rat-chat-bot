# project/storage_manager.py
import json
import logging
import os
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class StorageManager:
    """Менеджер хранения истории чата в JSON файле"""

    def __init__(self, storage_dir: str = "chat_history"):
        """
        Инициализация менеджера хранилища

        Args:
            storage_dir: Директория для хранения JSON файлов
        """
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        logger.info(f"Инициализирован StorageManager. Директория: {os.path.abspath(storage_dir)}")

    def _get_chat_filename(self, chat_id: int) -> str:
        """
        Генерирует имя файла для чата

        Args:
            chat_id: ID чата/пользователя

        Returns:
            Имя файла JSON
        """
        return os.path.join(self.storage_dir, f"chat_{chat_id}.json")

    def save_chat_history(self, chat_id: int, chat_data: Dict[str, Any]) -> bool:
        """
        Сохраняет историю чата в JSON файл

        Args:
            chat_id: ID чата/пользователя
            chat_data: Данные чата для сохранения

        Returns:
            True если сохранение успешно, False в противном случае
        """
        try:
            filename = self._get_chat_filename(chat_id)

            # Добавляем метаданные
            chat_data_with_meta = {
                "chat_id": chat_id,
                "last_updated": datetime.now().isoformat(),
                "data": chat_data
            }

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(chat_data_with_meta, f, ensure_ascii=False, indent=2)

            logger.info(f"История чата {chat_id} сохранена в {filename}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при сохранении истории чата {chat_id}: {e}")
            return False

    def load_chat_history(self, chat_id: int) -> Dict[str, Any]:
        """
        Загружает историю чата из JSON файла

        Args:
            chat_id: ID чата/пользователя

        Returns:
            Данные чата или пустой словарь если файл не существует
        """
        try:
            filename = self._get_chat_filename(chat_id)

            if not os.path.exists(filename):
                logger.info(f"Файл истории для чата {chat_id} не найден. Создаю новую историю.")
                return {}

            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Проверяем структуру данных
            if isinstance(data, dict) and 'data' in data:
                logger.info(f"История чата {chat_id} загружена из {filename}")
                return data['data']
            else:
                logger.warning(f"Некорректная структура файла истории для чата {chat_id}")
                return data if isinstance(data, dict) else {}

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON для чата {chat_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке истории чата {chat_id}: {e}")
            return {}

    def get_chat_history_for_display(self, chat_id: int) -> str:
        """
        Форматирует историю чата для отображения

        Args:
            chat_id: ID чата/пользователя

        Returns:
            Отформатированная строка с историей
        """
        chat_data = self.load_chat_history(chat_id)

        if not chat_data:
            return "📭 История чата пуста или не найдена."

        result = []

        # Метаданные
        if 'system_prompt' in chat_data:
            result.append(f"📋 Системный промпт: {chat_data['system_prompt'][:100]}...")

        # История сообщений
        if 'chat_history' in chat_data and chat_data['chat_history']:
            message_count = len(chat_data['chat_history'])
            result.append(f"\n📜 История сообщений ({message_count} сообщений):")
            result.append("═" * 10)

            # Показываем только последние 20 сообщений для удобства
            recent_messages = chat_data['chat_history'][-20:] if message_count > 20 else chat_data['chat_history']
            start_index = max(1, message_count - len(recent_messages) + 1)

            for i, msg in enumerate(recent_messages, start_index):
                role = "👤 Пользователь" if msg.get('role') == 'user' else "🤖 Ассистент"
                content = msg.get('content', '')
                preview = content[:150] + "..." if len(content) > 150 else content
                result.append(f"{i}. {role}:\n   {preview}")

            if message_count > 20:
                result.append(f"\n... и еще {message_count - 20} более ранних сообщений")

        # Сжатая история
        if 'compressed_history' in chat_data and chat_data['compressed_history']:
            result.append(f"\n📚 Сжатая история ({len(chat_data['compressed_history'])} блоков):")
            result.append("═" * 10)

            for i, msg in enumerate(chat_data['compressed_history'], 1):
                content = msg.get('content', '')
                first_line = content.split('\n')[0] if '\n' in content else content[:80]
                result.append(f"{i}. 📦 {first_line}")

        # Текущий режим
        if 'current_mode' in chat_data:
            mode_display = {
                'day1': '💬 Обычный режим',
                'day2': '💬 Режим JSON',
                'day3': '💬 Режим редактора писем'
            }.get(chat_data['current_mode'], chat_data['current_mode'])
            result.append(f"\n🔧 Текущий режим: {mode_display}")

        # Информация о файле
        filename = self._get_chat_filename(chat_id)
        if os.path.exists(filename):
            size_kb = os.path.getsize(filename) / 1024
            result.append(f"\n💾 Размер файла: {size_kb:.1f} KB")

        return "\n".join(result)

    def clear_chat_history(self, chat_id: int) -> bool:
        """
        Очищает историю чата

        Args:
            chat_id: ID чата/пользователя

        Returns:
            True если очистка успешна, False в противном случае
        """
        try:
            filename = self._get_chat_filename(chat_id)

            if os.path.exists(filename):
                os.remove(filename)
                logger.info(f"История чата {chat_id} очищена")
            else:
                logger.info(f"Файл истории для чата {chat_id} не найден")

            return True

        except Exception as e:
            logger.error(f"Ошибка при очистке истории чата {chat_id}: {e}")
            return False


# Создаем глобальный экземпляр для использования в приложении
storage_manager = StorageManager()