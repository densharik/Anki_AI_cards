"""Схемы данных и типы для Anki обработчика."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FieldMode(str, Enum):
    """Режимы обработки полей Anki."""
    INPUT = "INPUT"
    GENERATE = "GENERATE"
    SKIP = "SKIP"


class NoteTypeFieldConfig(BaseModel):
    """Конфигурация поля типа заметки."""
    mode: FieldMode
    llm_key: Optional[str] = None  # ключ в JSON ответе LLM
    description: Optional[str] = None


class NoteTypeConfig(BaseModel):
    """Конфигурация типа заметки."""
    name: str
    fields: Dict[str, NoteTypeFieldConfig]
    llm_prompt: str
    input_fields: List[str] = Field(default_factory=list)
    generate_fields: List[str] = Field(default_factory=list)


class OpenAIConfig(BaseModel):
    """Конфигурация OpenAI API."""
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    text_model: str = "gpt-4-turbo-preview"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    max_retries: int = 3
    timeout: float = 60.0
    concurrency_limit: int = 10


class AnkiConfig(BaseModel):
    """Конфигурация AnkiConnect."""
    url: str = "http://127.0.0.1:8765"
    batch_size: int = 50
    timeout: float = 30.0


class CacheConfig(BaseModel):
    """Конфигурация кеширования."""
    dir: str = "cache"
    audio_dir: str = "cache/audio"


class ProcessingConfig(BaseModel):
    """Конфигурация обработки."""
    dry_run: bool = False
    force_regenerate: List[str] = Field(default_factory=list)
    skip_audio: bool = False
    skip_frequency: bool = False
    skip_invalid_notes: bool = True


class LLMWordData(BaseModel):
    """Структура ответа LLM для словарных данных."""
    definition: str = Field(..., description="Короткое английское определение")
    definition_ru: str = Field(..., description="Русский перевод")
    ipa: str = Field(..., description="IPA транскрипция")
    lemma: str = Field(..., description="Словарная форма слова")
    collocations: str = Field(..., description="Коллокации с HTML разметкой")
    synonyms: str = Field(..., description="Синонимы с объяснениями")
    antonyms: str = Field(..., description="Антонимы с объяснениями")
    related_forms: str = Field(..., description="Родственные формы")
    examples: str = Field(..., description="Примеры диалогов")
    hint: str = Field(..., description="Подсказка на русском")
    tags: List[str] = Field(..., description="Теги для категоризации")


class AnkiNote(BaseModel):
    """Представление заметки Anki."""
    model_config = {"protected_namespaces": ()}
    
    note_id: int
    model_name: str
    deck_name: str
    fields: Dict[str, str]
    tags: List[str]


class ProcessingResult(BaseModel):
    """Результат обработки заметки."""
    note_id: int
    success: bool
    error: Optional[str] = None
    updated_fields: Dict[str, str] = Field(default_factory=dict)
    audio_file: Optional[str] = None
    created_at: Optional[float] = None


class ValidationError(BaseModel):
    """Ошибка валидации поля."""
    note_id: int
    field_name: str
    expected_mode: FieldMode
    current_value: str
    error_message: str


class ValidationReport(BaseModel):
    """Отчет о валидации заметок."""
    total_notes: int
    valid_notes: int
    invalid_notes: int
    errors: List[ValidationError]


class CacheEntry(BaseModel):
    """Запись в кеше."""
    key: str
    data: Any
    created_at: float
    expires_at: Optional[float] = None


class FrequencyData(BaseModel):
    """Данные о частотности слова."""
    word: str
    frequency: float
    rank: Optional[int] = None
    zipf_score: Optional[float] = None
