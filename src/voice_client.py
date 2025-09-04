"""Клиент для синтеза речи через OpenAI TTS."""

from pathlib import Path
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from .settings import CACHE_CONFIG, OPENAI_CONFIG
from .utils import retry_with_backoff, safe_filename


class VoiceClientError(Exception):
    """Ошибка клиента синтеза речи."""
    pass


class VoiceClient:
    """Клиент для генерации аудио через OpenAI TTS."""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=OPENAI_CONFIG.api_key,
            base_url=OPENAI_CONFIG.base_url,
            timeout=OPENAI_CONFIG.timeout
        )
        self.model = OPENAI_CONFIG.tts_model
        self.voice = OPENAI_CONFIG.tts_voice
        self.audio_dir = Path(CACHE_CONFIG.audio_dir)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
    
    async def synthesize_speech(
        self, 
        text: str, 
        note_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Синтезировать речь для текста.
        
        Args:
            text: Текст для синтеза
            note_id: ID заметки для генерации имени файла
            
        Returns:
            Имя сохраненного аудио файла или None при ошибке
        """
        if not text or not text.strip():
            logger.warning("Пустой текст для синтеза речи")
            return None
        
        # Генерируем имя файла
        filename = self._generate_filename(text, note_id)
        file_path = self.audio_dir / filename
        
        # Проверяем, есть ли уже файл
        if file_path.exists():
            logger.debug(f"Аудио файл уже существует: {filename}")
            return filename
        
        try:
            # Генерируем аудио
            audio_data = await retry_with_backoff(
                self._create_speech_request, text
            )
            
            if not audio_data:
                logger.error(f"Не удалось сгенерировать аудио для '{text}'")
                return None
            
            # Сохраняем файл
            with open(file_path, 'wb') as f:
                f.write(audio_data)
            
            logger.debug(f"Аудио сохранено: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Ошибка синтеза речи для '{text}': {e}")
            return None
    
    async def _create_speech_request(self, text: str) -> bytes:
        """Выполнить запрос к TTS API."""
        try:
            response = await self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text[:4000],  # Ограничение OpenAI TTS
                response_format="mp3"
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"Ошибка TTS API: {e}")
            raise VoiceClientError(f"Ошибка синтеза: {e}")
    
    def _generate_filename(self, text: str, note_id: Optional[int] = None) -> str:
        """Сгенерировать имя файла для аудио."""
        # Используем безопасное имя на основе текста
        safe_text = safe_filename(text, max_length=50)
        
        if note_id:
            return f"{safe_text}_{note_id}.mp3"
        else:
            return f"{safe_text}.mp3"
    
    def get_audio_field_value(self, filename: str) -> str:
        """Получить значение для поля аудио в Anki."""
        if filename:
            return f"[sound:{filename}]"
        return ""
    
    async def validate_connection(self) -> bool:
        """Проверить подключение к TTS API."""
        try:
            # Тестовый синтез короткого текста
            test_audio = await self._create_speech_request("test")
            
            if test_audio and len(test_audio) > 100:  # Минимальный размер MP3
                logger.info(f"Подключение к TTS успешно. Модель: {self.model}, Голос: {self.voice}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка подключения к TTS: {e}")
            return False
    
    def get_available_voices(self) -> list[str]:
        """Получить список доступных голосов."""
        # Голоса OpenAI TTS (по документации)
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def get_cache_size(self) -> tuple[int, float]:
        """Получить размер кеша аудио файлов."""
        count = 0
        total_size = 0.0
        
        if self.audio_dir.exists():
            for file_path in self.audio_dir.glob("*.mp3"):
                count += 1
                total_size += file_path.stat().st_size
        
        return count, total_size / (1024 * 1024)  # МБ
    
    def cleanup_cache(self, max_files: int = 1000) -> int:
        """Очистить старые файлы из кеша."""
        if not self.audio_dir.exists():
            return 0
        
        files = list(self.audio_dir.glob("*.mp3"))
        if len(files) <= max_files:
            return 0
        
        # Сортируем по времени изменения (старые сначала)
        files.sort(key=lambda f: f.stat().st_mtime)
        
        files_to_delete = files[:len(files) - max_files]
        deleted = 0
        
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted += 1
            except Exception as e:
                logger.warning(f"Не удалось удалить {file_path}: {e}")
        
        logger.info(f"Удалено {deleted} старых аудио файлов")
        return deleted
    
    async def batch_synthesize(
        self,
        text_pairs: list[tuple[str, int]],  # (text, note_id)
        concurrency_limit: int = 5
    ) -> dict[int, Optional[str]]:
        """Батчевый синтез аудио для списка текстов."""
        import asyncio
        
        semaphore = asyncio.Semaphore(concurrency_limit)
        results = {}
        
        async def process_text(text: str, note_id: int):
            async with semaphore:
                filename = await self.synthesize_speech(text, note_id)
                results[note_id] = filename
                return note_id, filename
        
        tasks = [
            process_text(text, note_id) 
            for text, note_id in text_pairs
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        return results
