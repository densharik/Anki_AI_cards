"""Модуль для кеширования данных и состояний."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from loguru import logger

from .schemas import AnkiNote, CacheEntry, LLMWordData, ProcessingResult
from .settings import CACHE_CONFIG
from .utils import generate_cache_key


class CacheManager:
    """Менеджер кеширования данных."""
    
    def __init__(self):
        self.cache_dir = Path(CACHE_CONFIG.dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Пути к файлам кеша
        self.notes_cache_path = self.cache_dir / "notes_raw.json"
        self.openai_cache_path = self.cache_dir / "openai_results.json"
        self.freq_cache_path = self.cache_dir / "freq.json"
        self.processing_cache_path = self.cache_dir / "processing_results.json"
        
        # In-memory кеши
        self._notes_cache: Dict[str, AnkiNote] = {}
        self._openai_cache: Dict[str, LLMWordData] = {}
        self._freq_cache: Dict[str, str] = {}  # word -> freq_rank
        self._processing_cache: Dict[str, ProcessingResult] = {}
    
    async def load_all_caches(self):
        """Загрузить все кеши в память."""
        await self._load_notes_cache()
        await self._load_openai_cache()
        await self._load_freq_cache()
        await self._load_processing_cache()
        
        logger.info(
            f"Кеши загружены: notes={len(self._notes_cache)}, "
            f"openai={len(self._openai_cache)}, "
            f"freq={len(self._freq_cache)}, "
            f"processing={len(self._processing_cache)}"
        )
    
    async def _load_notes_cache(self):
        """Загрузить кеш заметок."""
        try:
            if self.notes_cache_path.exists():
                async with aiofiles.open(self.notes_cache_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    
                self._notes_cache = {
                    note_data["note_id"]: AnkiNote(**note_data)
                    for note_data in data
                }
        except Exception as e:
            logger.warning(f"Ошибка загрузки кеша заметок: {e}")
            self._notes_cache = {}
    
    async def _load_openai_cache(self):
        """Загрузить кеш OpenAI результатов."""
        try:
            if self.openai_cache_path.exists():
                async with aiofiles.open(self.openai_cache_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    
                self._openai_cache = {
                    key: LLMWordData(**value)
                    for key, value in data.items()
                }
        except Exception as e:
            logger.warning(f"Ошибка загрузки кеша OpenAI: {e}")
            self._openai_cache = {}
    
    async def _load_freq_cache(self):
        """Загрузить кеш частотности."""
        try:
            if self.freq_cache_path.exists():
                async with aiofiles.open(self.freq_cache_path, 'r', encoding='utf-8') as f:
                    self._freq_cache = json.loads(await f.read())
        except Exception as e:
            logger.warning(f"Ошибка загрузки кеша частотности: {e}")
            self._freq_cache = {}
    
    async def _load_processing_cache(self):
        """Загрузить кеш результатов обработки."""
        try:
            if self.processing_cache_path.exists():
                async with aiofiles.open(self.processing_cache_path, 'r', encoding='utf-8') as f:
                    data = json.loads(await f.read())
                    
                self._processing_cache = {
                    key: ProcessingResult(**value)
                    for key, value in data.items()
                }
        except Exception as e:
            logger.warning(f"Ошибка загрузки кеша обработки: {e}")
            self._processing_cache = {}
    
    async def save_notes_cache(self, notes: List[AnkiNote]):
        """Сохранить кеш заметок."""
        self._notes_cache = {str(note.note_id): note for note in notes}
        
        try:
            data = [note.model_dump() for note in notes]
            async with aiofiles.open(self.notes_cache_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            logger.debug(f"Кеш заметок сохранен: {len(notes)} записей")
        except Exception as e:
            logger.error(f"Ошибка сохранения кеша заметок: {e}")
    
    async def save_openai_cache(self):
        """Сохранить кеш OpenAI результатов."""
        try:
            data = {
                key: value.model_dump()
                for key, value in self._openai_cache.items()
            }
            
            async with aiofiles.open(self.openai_cache_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            logger.debug(f"Кеш OpenAI сохранен: {len(data)} записей")
        except Exception as e:
            logger.error(f"Ошибка сохранения кеша OpenAI: {e}")
    
    async def save_freq_cache(self):
        """Сохранить кеш частотности."""
        try:
            async with aiofiles.open(self.freq_cache_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._freq_cache, ensure_ascii=False, indent=2))
            
            logger.debug(f"Кеш частотности сохранен: {len(self._freq_cache)} записей")
        except Exception as e:
            logger.error(f"Ошибка сохранения кеша частотности: {e}")
    
    async def save_processing_cache(self):
        """Сохранить кеш результатов обработки."""
        try:
            data = {
                key: value.model_dump()
                for key, value in self._processing_cache.items()
            }
            
            async with aiofiles.open(self.processing_cache_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            logger.debug(f"Кеш обработки сохранен: {len(data)} записей")
        except Exception as e:
            logger.error(f"Ошибка сохранения кеша обработки: {e}")
    
    def get_cached_note(self, note_id: int) -> Optional[AnkiNote]:
        """Получить заметку из кеша."""
        return self._notes_cache.get(str(note_id))
    
    def get_cached_openai_data(self, word: str, sentence: str) -> Optional[LLMWordData]:
        """Получить данные OpenAI из кеша."""
        cache_key = generate_cache_key(word.lower(), sentence)
        return self._openai_cache.get(cache_key)
    
    def set_cached_openai_data(self, word: str, sentence: str, data: LLMWordData):
        """Сохранить данные OpenAI в кеш."""
        cache_key = generate_cache_key(word.lower(), sentence)
        self._openai_cache[cache_key] = data
    
    def get_cached_frequency(self, word: str, lemma: str = None) -> Optional[str]:
        """Получить частотность из кеша."""
        search_key = (lemma or word).lower()
        return self._freq_cache.get(search_key)
    
    def set_cached_frequency(self, word: str, freq_rank: str, lemma: str = None):
        """Сохранить частотность в кеш."""
        search_key = (lemma or word).lower()
        self._freq_cache[search_key] = freq_rank
    
    def get_cached_processing_result(self, note_id: int, fields_hash: str) -> Optional[ProcessingResult]:
        """Получить результат обработки из кеша."""
        cache_key = f"{note_id}_{fields_hash}"
        return self._processing_cache.get(cache_key)
    
    def set_cached_processing_result(
        self, 
        note_id: int, 
        fields_hash: str, 
        result: ProcessingResult
    ):
        """Сохранить результат обработки в кеш."""
        cache_key = f"{note_id}_{fields_hash}"
        self._processing_cache[cache_key] = result
    
    def is_note_processed(self, note_id: int, expression: str, sentence: str) -> bool:
        """Проверить, была ли заметка обработана."""
        cache_key = generate_cache_key(str(note_id), expression, sentence)
        result = self._processing_cache.get(cache_key)
        return result is not None and result.success
    
    def should_regenerate_field(self, field_name: str, force_regenerate: List[str]) -> bool:
        """Проверить, нужно ли перегенерировать поле."""
        return field_name in force_regenerate or "all" in force_regenerate
    
    async def cleanup_old_cache(self, max_age_days: int = 30):
        """Очистить старые записи кеша."""
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        cleaned = 0
        
        # Очищаем кеш обработки по времени
        to_remove = []
        for key, result in self._processing_cache.items():
            # Если в результате есть временная метка и она старая
            if hasattr(result, 'created_at') and result.created_at < cutoff_time:
                to_remove.append(key)
        
        for key in to_remove:
            del self._processing_cache[key]
            cleaned += 1
        
        if cleaned > 0:
            logger.info(f"Очищено {cleaned} старых записей кеша")
            await self.save_processing_cache()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Получить статистику кеша."""
        return {
            "notes_count": len(self._notes_cache),
            "openai_count": len(self._openai_cache),
            "frequency_count": len(self._freq_cache),
            "processing_count": len(self._processing_cache),
            "cache_dir_size_mb": self._get_cache_dir_size(),
            "files": {
                "notes_exists": self.notes_cache_path.exists(),
                "openai_exists": self.openai_cache_path.exists(),
                "freq_exists": self.freq_cache_path.exists(),
                "processing_exists": self.processing_cache_path.exists()
            }
        }
    
    def _get_cache_dir_size(self) -> float:
        """Получить размер директории кеша в МБ."""
        total_size = 0
        try:
            for file_path in self.cache_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception:
            pass
        
        return total_size / (1024 * 1024)  # МБ
    
    async def clear_cache(self, cache_type: str = "all"):
        """Очистить определенный тип кеша или все."""
        if cache_type in ("all", "notes"):
            self._notes_cache.clear()
            if self.notes_cache_path.exists():
                self.notes_cache_path.unlink()
        
        if cache_type in ("all", "openai"):
            self._openai_cache.clear()
            if self.openai_cache_path.exists():
                self.openai_cache_path.unlink()
        
        if cache_type in ("all", "freq"):
            self._freq_cache.clear()
            if self.freq_cache_path.exists():
                self.freq_cache_path.unlink()
        
        if cache_type in ("all", "processing"):
            self._processing_cache.clear()
            if self.processing_cache_path.exists():
                self.processing_cache_path.unlink()
        
        logger.info(f"Кеш '{cache_type}' очищен")
