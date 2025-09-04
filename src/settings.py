"""Настройки приложения и загрузка переменных окружения."""

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pydantic import ValidationError

from .schemas import AnkiConfig, CacheConfig, OpenAIConfig, ProcessingConfig

# Загрузка переменных окружения
load_dotenv()


def get_env_var(name: str, default: str = None, required: bool = True) -> str:
    """Получить переменную окружения с валидацией."""
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f"Переменная окружения {name} обязательна")
    return value


def validate_openai_config() -> OpenAIConfig:
    """Валидация конфигурации OpenAI."""
    try:
        return OpenAIConfig(
            api_key=get_env_var("OPENAI_API_KEY"),
            base_url=get_env_var("OPENAI_BASE_URL", "https://api.openai.com/v1", False),
            text_model=get_env_var("OPENAI_TEXT_MODEL", "gpt-4-turbo-preview", False),
            tts_model=get_env_var("OPENAI_TTS_MODEL", "tts-1", False),
            tts_voice=get_env_var("OPENAI_TTS_VOICE", "alloy", False)
        )
    except ValidationError as e:
        logger.error(f"Ошибка конфигурации OpenAI: {e}")
        raise


def validate_anki_config() -> AnkiConfig:
    """Валидация конфигурации Anki."""
    try:
        return AnkiConfig(
            url=get_env_var("ANKI_CONNECT_URL", "http://127.0.0.1:8765", False)
        )
    except ValidationError as e:
        logger.error(f"Ошибка конфигурации Anki: {e}")
        raise


def validate_cache_config() -> CacheConfig:
    """Валидация конфигурации кеша."""
    cache_dir = get_env_var("CACHE_DIR", "cache", False)
    try:
        config = CacheConfig(
            dir=cache_dir,
            audio_dir=f"{cache_dir}/audio"
        )
        # Создаем директории если не существуют
        Path(config.dir).mkdir(parents=True, exist_ok=True)
        Path(config.audio_dir).mkdir(parents=True, exist_ok=True)
        return config
    except ValidationError as e:
        logger.error(f"Ошибка конфигурации кеша: {e}")
        raise


# Глобальные настройки
OPENAI_CONFIG = validate_openai_config()
ANKI_CONFIG = validate_anki_config()
CACHE_CONFIG = validate_cache_config()

PROCESSING_CONFIG = ProcessingConfig(
    skip_invalid_notes=True  # По умолчанию пропускаем невалидные заметки
)

# Настройка логирования
LOG_LEVEL = get_env_var("LOG_LEVEL", "INFO", False)
logger.remove()
logger.add(
    "anki_processor.log",
    rotation="10 MB",
    retention="30 days",
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
)
logger.add(
    lambda msg: print(msg, end=""),
    level=LOG_LEVEL,
    format="{time:HH:mm:ss} | {level} | {message}"
)

# Путь к словарю частот (опционально)
FREQ_DICT_PATH = get_env_var("FREQ_DICT_PATH", "", False)
