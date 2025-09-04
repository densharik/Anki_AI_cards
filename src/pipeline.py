"""Основной пайплайн обработки заметок Anki."""

import asyncio
from typing import Dict, List, Optional, Tuple

from loguru import logger
from tqdm.asyncio import tqdm

from .anki_client import AnkiClient
from .cache import CacheManager
from .config import DEFAULT_CONCURRENCY_LIMITS, NOTE_TYPE_CONFIGS, ALLOWED_TAGS
from .freq import FrequencyCalculator
from .openai_client import OpenAITextClient
from .schemas import AnkiNote, FieldMode, LLMWordData, ProcessingResult
from .settings import PROCESSING_CONFIG
from .utils import AsyncSemaphorePool, ProgressTracker, batch_items
from .validators import NoteValidator
from .voice_client import VoiceClient


class ProcessingPipeline:
    """Основной пайплайн обработки заметок."""
    
    def __init__(self):
        self.anki_client = AnkiClient()
        self.openai_client = OpenAITextClient()
        self.voice_client = VoiceClient()
        self.freq_calculator = FrequencyCalculator()
        self.cache_manager = CacheManager()
        self.validator = NoteValidator()
        
        # Пул семафоров для контроля параллелизма
        self.semaphore_pool = AsyncSemaphorePool(DEFAULT_CONCURRENCY_LIMITS)
        
        self.dry_run = PROCESSING_CONFIG.dry_run
        self.force_regenerate = PROCESSING_CONFIG.force_regenerate
        self.skip_audio = PROCESSING_CONFIG.skip_audio
        self.skip_frequency = PROCESSING_CONFIG.skip_frequency
        self.skip_invalid_notes = PROCESSING_CONFIG.skip_invalid_notes
    
    async def initialize(self):
        """Инициализация пайплайна."""
        logger.info("Инициализация пайплайна...")
        
        # Проверяем подключения
        anki_ok = await self.anki_client.check_connection()
        if not anki_ok:
            raise RuntimeError("Не удалось подключиться к Anki")
        
        openai_ok = await self.openai_client.validate_connection()
        if not openai_ok:
            raise RuntimeError("Не удалось подключиться к OpenAI")
        
        if not self.skip_audio:
            tts_ok = await self.voice_client.validate_connection()
            if not tts_ok:
                logger.warning("TTS недоступен, аудио будет пропущено")
                self.skip_audio = True
        
        # Загружаем кеши
        await self.cache_manager.load_all_caches()
        
        logger.info("Пайплайн инициализирован")
    
    async def process_deck(
        self, 
        deck_name: str, 
        note_type_name: str
    ) -> ProcessingResult:
        """
        Обработать все заметки в колоде.
        
        Args:
            deck_name: Имя колоды Anki
            note_type_name: Тип заметок для обработки
            
        Returns:
            Общий результат обработки
        """
        logger.info(f"Начинаем обработку колоды '{deck_name}' с типом '{note_type_name}'")
        
        try:
            # 1. Получаем заметки из колоды
            notes = await self._fetch_notes_from_deck(deck_name, note_type_name)
            if not notes:
                return ProcessingResult(
                    note_id=0,
                    success=False,
                    error="Не найдено заметок для обработки"
                )
            
            # 2. Валидируем заметки
            validation_ready, validation_message = self.validator.check_processing_readiness(
                notes, note_type_name
            )
            
            # 3. Фильтруем валидные заметки
            valid_notes = self.validator.filter_valid_notes(notes, note_type_name)
            invalid_count = len(notes) - len(valid_notes)
            
            if invalid_count > 0:
                if self.skip_invalid_notes:
                    logger.warning(f"Пропускаем {invalid_count} невалидных заметок, обрабатываем {len(valid_notes)}")
                else:
                    logger.error(f"Ошибка валидации: {validation_message}")
                    if not self.dry_run:
                        return ProcessingResult(
                            note_id=0,
                            success=False,
                            error=validation_message
                        )
            
            if not valid_notes:
                return ProcessingResult(
                    note_id=0,
                    success=False,
                    error="Нет валидных заметок для обработки"
                )
            
            logger.info(f"К обработке готовы {len(valid_notes)} из {len(notes)} заметок")
            
            if self.dry_run:
                logger.info("СУХОЙ ПРОГОН: обработка не выполняется")
                return ProcessingResult(
                    note_id=0,
                    success=True,
                    error=f"Dry run: готовы {len(valid_notes)} заметок"
                )
            
            # 4. Обрабатываем заметки
            results = await self._process_notes_batch(valid_notes, note_type_name)
            
            # 5. Сохраняем кеши
            await self._save_all_caches()
            
            # Подсчитываем статистику
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            
            # Формируем детальный отчет
            total_notes = len(notes)
            skipped_invalid = invalid_count if invalid_count > 0 and self.skip_invalid_notes else 0
            
            logger.info(f"Обработка завершена: успешно={successful}, ошибок={failed}, пропущено={skipped_invalid}")
            
            status_message = None
            if failed == 0:
                if skipped_invalid > 0:
                    status_message = f"Успешно обработано {successful} из {total_notes} заметок. Пропущено {skipped_invalid} невалидных."
            else:
                status_message = f"Обработано {successful}, ошибок {failed}"
                if skipped_invalid > 0:
                    status_message += f", пропущено {skipped_invalid} невалидных"
            
            return ProcessingResult(
                note_id=0,
                success=failed == 0,
                error=status_message
            )
            
        except Exception as e:
            logger.error(f"Критическая ошибка в пайплайне: {e}")
            return ProcessingResult(
                note_id=0,
                success=False,
                error=f"Критическая ошибка: {str(e)}"
            )
    
    async def _fetch_notes_from_deck(
        self, 
        deck_name: str, 
        note_type_name: str
    ) -> List[AnkiNote]:
        """Получить заметки из колоды."""
        # Формируем запрос для поиска заметок
        query = f'deck:"{deck_name}" note:"{note_type_name}"'
        
        note_ids = await self.anki_client.find_notes(query)
        if not note_ids:
            logger.warning(f"Не найдено заметок в колоде '{deck_name}' с типом '{note_type_name}'")
            return []
        
        logger.info(f"Найдено {len(note_ids)} заметок")
        
        # Получаем информацию о заметках
        notes = await self.anki_client.get_notes_info(note_ids)
        
        # Сохраняем в кеш
        await self.cache_manager.save_notes_cache(notes)
        
        return notes
    
    async def _process_notes_batch(
        self, 
        notes: List[AnkiNote], 
        note_type_name: str
    ) -> List[ProcessingResult]:
        """Обработать батч заметок."""
        config = NOTE_TYPE_CONFIGS[note_type_name]
        
        # Трекер прогресса
        progress = ProgressTracker(len(notes), "Обработка заметок")
        
        # Результаты обработки
        results = []
        
        # Группируем заметки для параллельной обработки
        tasks = []
        for note in notes:
            task = self._process_single_note(note, config, progress)
            tasks.append(task)
        
        # Выполняем с прогресс-баром
        with tqdm(total=len(notes), desc="Обработка заметок") as pbar:
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                pbar.update(1)
        
        progress.finish()
        return results
    
    async def _process_single_note(
        self, 
        note: AnkiNote, 
        config, 
        progress: ProgressTracker
    ) -> ProcessingResult:
        """Обработать одну заметку."""
        try:
            # Извлекаем входные данные
            input_data = self._extract_input_data(note, config)
            if not input_data:
                progress.update(False)
                return ProcessingResult(
                    note_id=note.note_id,
                    success=False,
                    error="Отсутствуют входные данные"
                )
            
            # Проверяем кеш
            if self._is_note_already_processed(note, input_data):
                progress.update(True)
                return ProcessingResult(
                    note_id=note.note_id,
                    success=True,
                    error="Уже обработано (из кеша)"
                )
            
            # Генерируем данные через OpenAI
            llm_data = await self._generate_llm_data(
                input_data["word"], 
                input_data["sentence"], 
                config.llm_prompt
            )
            
            if not llm_data:
                progress.update(False)
                return ProcessingResult(
                    note_id=note.note_id,
                    success=False,
                    error="Ошибка генерации LLM данных"
                )
            
            # Генерируем аудио
            audio_filename = None
            if not self.skip_audio and "ExpressionAudio" in config.fields:
                audio_filename = await self._generate_audio(
                    input_data["word"], note.note_id
                )
            
            # Получаем частотность
            freq_rank = ""
            if not self.skip_frequency and "FreqSort" in config.fields:
                freq_rank = await self._get_frequency_rank(
                    input_data["word"], getattr(llm_data, 'lemma', None)
                )
            
            # Формируем обновления полей
            field_updates = self._build_field_updates(
                config, llm_data, audio_filename, freq_rank
            )
            
            # Обновляем заметку в Anki
            update_success = await self.anki_client.update_note_fields(
                note.note_id, field_updates
            )
            
            if update_success:
                # Обновляем теги если есть (с фильтрацией по whitelist)
                if hasattr(llm_data, 'tags') and llm_data.tags:
                    filtered_tags = [tag for tag in llm_data.tags if tag in ALLOWED_TAGS]
                    if filtered_tags:
                        await self.anki_client.update_note_tags(note.note_id, filtered_tags)
                
                # Сохраняем в кеш обработки
                self._cache_processing_result(note, input_data, True)
                
                progress.update(True)
                return ProcessingResult(
                    note_id=note.note_id,
                    success=True,
                    updated_fields=field_updates,
                    audio_file=audio_filename
                )
            else:
                progress.update(False)
                return ProcessingResult(
                    note_id=note.note_id,
                    success=False,
                    error="Ошибка обновления заметки"
                )
                
        except Exception as e:
            logger.error(f"Ошибка обработки заметки {note.note_id}: {e}")
            progress.update(False)
            return ProcessingResult(
                note_id=note.note_id,
                success=False,
                error=str(e)
            )
    
    def _extract_input_data(self, note: AnkiNote, config) -> Optional[Dict[str, str]]:
        """Извлечь входные данные из заметки."""
        input_data = {}
        
        for field_name, field_config in config.fields.items():
            if field_config.mode == FieldMode.INPUT:
                value = note.fields.get(field_name, "").strip()
                if not value:
                    logger.warning(f"Пустое INPUT поле {field_name} в заметке {note.note_id}")
                    return None
                input_data[field_name.lower()] = value
        
        # Специальные имена для совместимости
        if "expression" in input_data:
            input_data["word"] = input_data["expression"]
        if "sentence" in input_data and not input_data["sentence"]:
            input_data["sentence"] = input_data.get("word", "")
        
        return input_data if input_data else None
    
    def _is_note_already_processed(self, note: AnkiNote, input_data: Dict[str, str]) -> bool:
        """Проверить, была ли заметка уже обработана."""
        if "all" in self.force_regenerate:
            return False
        
        return self.cache_manager.is_note_processed(
            note.note_id, 
            input_data.get("word", ""), 
            input_data.get("sentence", "")
        )
    
    async def _generate_llm_data(
        self, 
        word: str, 
        sentence: str, 
        system_prompt: str
    ) -> Optional[LLMWordData]:
        """Генерировать данные через LLM."""
        # Проверяем кеш
        cached_data = self.cache_manager.get_cached_openai_data(word, sentence)
        if cached_data and not self._should_regenerate_llm():
            return cached_data
        
        # Генерируем новые данные
        async with self.semaphore_pool.get_semaphore("openai_text"):
            llm_data = await self.openai_client.generate_word_data(
                word, sentence, system_prompt
            )
        
        if llm_data:
            self.cache_manager.set_cached_openai_data(word, sentence, llm_data)
        
        return llm_data
    
    async def _generate_audio(self, word: str, note_id: int) -> Optional[str]:
        """Генерировать аудио файл."""
        async with self.semaphore_pool.get_semaphore("openai_tts"):
            filename = await self.voice_client.synthesize_speech(word, note_id)
        
        if filename:
            # Сохраняем файл в Anki
            audio_path = self.voice_client.audio_dir / filename
            if audio_path.exists():
                with open(audio_path, 'rb') as f:
                    audio_data = f.read()
                await self.anki_client.store_media_file(filename, audio_data)
        
        return filename
    
    async def _get_frequency_rank(self, word: str, lemma: str = None) -> str:
        """Получить ранг частотности слова."""
        # Проверяем кеш
        cached_freq = self.cache_manager.get_cached_frequency(word, lemma)
        if cached_freq is not None:
            return cached_freq
        
        # Вычисляем частотность
        freq_rank = self.freq_calculator.get_frequency_rank(word, lemma)
        
        # Сохраняем в кеш
        self.cache_manager.set_cached_frequency(word, freq_rank, lemma)
        
        return freq_rank
    
    def _build_field_updates(
        self, 
        config, 
        llm_data: LLMWordData, 
        audio_filename: Optional[str], 
        freq_rank: str
    ) -> Dict[str, str]:
        """Построить словарь обновлений полей."""
        updates = {}
        
        for field_name, field_config in config.fields.items():
            if field_config.mode != FieldMode.GENERATE:
                continue
            
            # Специальная логика для аудио
            if field_name == "ExpressionAudio" and audio_filename:
                updates[field_name] = f"[sound:{audio_filename}]"
                continue
            
            # Специальная логика для частотности
            if field_name == "FreqSort":
                updates[field_name] = freq_rank
                continue
            
            # Маппинг через llm_key
            if field_config.llm_key and hasattr(llm_data, field_config.llm_key):
                value = getattr(llm_data, field_config.llm_key)
                if value:
                    updates[field_name] = str(value)
        
        return updates
    
    def _should_regenerate_llm(self) -> bool:
        """Проверить, нужно ли перегенерировать LLM данные."""
        return (
            "all" in self.force_regenerate or
            "llm" in self.force_regenerate or
            "openai" in self.force_regenerate
        )
    
    def _cache_processing_result(
        self, 
        note: AnkiNote, 
        input_data: Dict[str, str], 
        success: bool
    ):
        """Сохранить результат обработки в кеш."""
        from .utils import generate_cache_key
        import time
        
        cache_key = generate_cache_key(
            str(note.note_id), 
            input_data.get("word", ""), 
            input_data.get("sentence", "")
        )
        
        result = ProcessingResult(
            note_id=note.note_id,
            success=success
        )
        result.created_at = time.time()
        
        self.cache_manager.set_cached_processing_result(
            note.note_id, cache_key, result
        )
    
    async def _save_all_caches(self):
        """Сохранить все кеши."""
        await asyncio.gather(
            self.cache_manager.save_openai_cache(),
            self.cache_manager.save_freq_cache(),
            self.cache_manager.save_processing_cache(),
            return_exceptions=True
        )
    
    async def get_deck_preview(self, deck_name: str, note_type_name: str) -> dict:
        """Получить превью колоды для валидации."""
        notes = await self._fetch_notes_from_deck(deck_name, note_type_name)
        
        if not notes:
            return {
                "total_notes": 0,
                "sample_notes": [],
                "validation": None
            }
        
        # Валидация
        validation_report = self.validator.validate_notes(notes, note_type_name)
        
        # Выборка для превью
        sample_notes = notes[:5]  # Первые 5 заметок
        
        return {
            "total_notes": len(notes),
            "sample_notes": [
                {
                    "note_id": note.note_id,
                    "fields": dict(list(note.fields.items())[:3])  # Первые 3 поля
                }
                for note in sample_notes
            ],
            "validation": {
                "valid_notes": validation_report.valid_notes,
                "invalid_notes": validation_report.invalid_notes,
                "error_count": len(validation_report.errors)
            }
        }
