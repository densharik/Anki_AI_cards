"""Клиент для работы с OpenAI API - генерация словарных данных."""

import json
from typing import Dict, Optional

from loguru import logger
from openai import AsyncOpenAI
from pydantic import ValidationError

from .schemas import LLMWordData
from .settings import OPENAI_CONFIG
from .utils import retry_with_backoff


class OpenAIClientError(Exception):
    """Ошибка OpenAI клиента."""
    pass


class OpenAITextClient:
    """Клиент для генерации текстовых данных через OpenAI."""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=OPENAI_CONFIG.api_key,
            base_url=OPENAI_CONFIG.base_url,
            timeout=OPENAI_CONFIG.timeout,
            max_retries=OPENAI_CONFIG.max_retries
        )
        self.model = OPENAI_CONFIG.text_model
    
    def _build_user_prompt(self, word: str, sentence: str) -> str:
        """Построить пользовательский промпт."""
        return json.dumps({
            "task": "generateWordData",
            "word": word,
            "sentence": sentence,
            "requirements": [
                "Ответь только валидным JSON",
                "Все поля обязательны",
                "Используй указанное значение слова из sentence",
                "Сохраняй HTML разметку только где указано",
                "Не изобретай коллокации - используй проверенные"
            ]
        }, ensure_ascii=False)
    
    async def generate_word_data(
        self, 
        word: str, 
        sentence: str, 
        system_prompt: str
    ) -> Optional[LLMWordData]:
        """Сгенерировать словарные данные для слова."""
        user_prompt = self._build_user_prompt(word, sentence)
        
        try:
            response = await retry_with_backoff(
                self._make_completion_request,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            
            if not response:
                logger.error(f"Пустой ответ для слова '{word}'")
                return None
            
            # Парсим JSON ответ
            try:
                content = response.choices[0].message.content
                if not content:
                    logger.error(f"Пустой контент в ответе для '{word}'")
                    return None
                
                json_data = json.loads(content)
                
                # Валидируем через Pydantic
                word_data = LLMWordData(**json_data)
                logger.debug(f"Успешно сгенерированы данные для '{word}'")
                return word_data
                
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON для '{word}': {e}")
                logger.debug(f"Содержимое ответа: {content}")
                return None
            except ValidationError as e:
                logger.error(f"Ошибка валидации данных для '{word}': {e}")
                logger.debug(f"Данные: {json_data}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка генерации данных для '{word}': {e}")
            return None
    
    async def _make_completion_request(
        self, 
        system_prompt: str, 
        user_prompt: str
    ):
        """Выполнить запрос к OpenAI API."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
            )
            return response
        except Exception as e:
            logger.error(f"Ошибка запроса к OpenAI: {e}")
            raise OpenAIClientError(f"Ошибка API: {e}")
    
    async def validate_connection(self) -> bool:
        """Проверить подключение к OpenAI."""
        try:
            # Простой тестовый запрос
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Say 'test' in JSON format."}
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=50
            )
            
            if response.choices:
                logger.info(f"Подключение к OpenAI успешно. Модель: {self.model}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка подключения к OpenAI: {e}")
            return False
    
    async def get_available_models(self) -> list[str]:
        """Получить список доступных моделей."""
        try:
            models = await self.client.models.list()
            return [model.id for model in models.data if "gpt" in model.id]
        except Exception as e:
            logger.error(f"Ошибка получения моделей: {e}")
            return []
    
    def estimate_tokens(self, text: str) -> int:
        """Оценка количества токенов в тексте (приблизительно)."""
        # Грубая оценка: ~4 символа на токен для английского
        return len(text) // 4
    
    async def batch_generate_word_data(
        self,
        word_sentence_pairs: list[tuple[str, str]],
        system_prompt: str,
        concurrency_limit: int = 10
    ) -> Dict[str, Optional[LLMWordData]]:
        """Батчевая генерация данных для списка слов."""
        import asyncio
        
        semaphore = asyncio.Semaphore(concurrency_limit)
        results = {}
        
        async def process_word(word: str, sentence: str):
            async with semaphore:
                data = await self.generate_word_data(word, sentence, system_prompt)
                results[word.lower()] = data
                return word, data
        
        tasks = [
            process_word(word, sentence) 
            for word, sentence in word_sentence_pairs
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        return results
