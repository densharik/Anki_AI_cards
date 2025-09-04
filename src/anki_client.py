"""Клиент для взаимодействия с AnkiConnect API."""

import base64
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from .schemas import AnkiNote
from .settings import ANKI_CONFIG
from .utils import batch_items, retry_with_backoff


class AnkiConnectError(Exception):
    """Ошибка AnkiConnect API."""
    pass


class AnkiClient:
    """Клиент для работы с Anki через AnkiConnect."""
    
    def __init__(self):
        self.url = ANKI_CONFIG.url
        self.timeout = ANKI_CONFIG.timeout
        self.batch_size = ANKI_CONFIG.batch_size
    
    async def _request(self, action: str, **params) -> Any:
        """Базовый запрос к AnkiConnect."""
        payload = {
            "action": action,
            "version": 6,
            "params": params
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
                
                data = response.json()
                if data.get("error"):
                    raise AnkiConnectError(f"Anki error in {action}: {data['error']}")
                
                return data.get("result")
            except httpx.RequestError as e:
                raise AnkiConnectError(f"Ошибка соединения с Anki: {e}")
            except Exception as e:
                raise AnkiConnectError(f"Ошибка запроса {action}: {e}")
    
    async def _multi_request(self, actions: List[Dict[str, Any]]) -> List[Any]:
        """Множественный запрос через action 'multi'."""
        return await self._request("multi", actions=actions)
    
    async def get_deck_names(self) -> List[str]:
        """Получить список всех колод."""
        return await retry_with_backoff(self._request, "deckNames")
    
    async def get_deck_names_and_ids(self) -> Dict[str, int]:
        """Получить словарь колод: имя -> ID."""
        return await retry_with_backoff(self._request, "deckNamesAndIds")
    
    async def find_notes(self, query: str) -> List[int]:
        """Найти заметки по запросу."""
        return await retry_with_backoff(self._request, "findNotes", query=query)
    
    async def get_notes_info(self, note_ids: List[int]) -> List[AnkiNote]:
        """Получить информацию о заметках."""
        if not note_ids:
            return []
        
        # Обрабатываем батчами для больших списков
        all_notes = []
        batches = batch_items(note_ids, self.batch_size)
        
        for batch in batches:
            try:
                raw_notes = await retry_with_backoff(
                    self._request, "notesInfo", notes=batch
                )
                
                for note_data in raw_notes:
                    fields = {}
                    for field_name, field_data in note_data.get("fields", {}).items():
                        fields[field_name] = field_data.get("value", "")
                    
                    note = AnkiNote(
                        note_id=note_data["noteId"],
                        model_name=note_data.get("modelName", ""),
                        deck_name=note_data.get("deckName", ""),
                        fields=fields,
                        tags=note_data.get("tags", [])
                    )
                    all_notes.append(note)
                    
            except Exception as e:
                logger.error(f"Ошибка получения информации о заметках: {e}")
                continue
        
        return all_notes
    
    async def update_note_fields(self, note_id: int, fields: Dict[str, str]) -> bool:
        """Обновить поля заметки."""
        try:
            await retry_with_backoff(
                self._request, "updateNoteFields",
                note={"id": note_id, "fields": fields}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления полей заметки {note_id}: {e}")
            return False
    
    async def update_note_tags(self, note_id: int, tags: List[str]) -> bool:
        """Обновить теги заметки."""
        try:
            await retry_with_backoff(
                self._request, "updateNote",
                note={"id": note_id, "tags": tags}
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления тегов заметки {note_id}: {e}")
            return False
    
    async def store_media_file(self, filename: str, data: bytes) -> bool:
        """Сохранить медиа файл в Anki."""
        try:
            b64_data = base64.b64encode(data).decode('utf-8')
            await retry_with_backoff(
                self._request, "storeMediaFile",
                filename=filename, data=b64_data
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения медиа файла {filename}: {e}")
            return False
    
    async def batch_update_notes(
        self, 
        updates: List[Dict[str, Any]]
    ) -> List[bool]:
        """Батчевое обновление заметок через multi action."""
        if not updates:
            return []
        
        results = []
        batches = batch_items(updates, self.batch_size)
        
        for batch in batches:
            actions = []
            for update in batch:
                if "fields" in update:
                    actions.append({
                        "action": "updateNoteFields",
                        "params": {
                            "note": {
                                "id": update["note_id"],
                                "fields": update["fields"]
                            }
                        }
                    })
                
                if "tags" in update:
                    actions.append({
                        "action": "updateNote", 
                        "params": {
                            "note": {
                                "id": update["note_id"],
                                "tags": update["tags"]
                            }
                        }
                    })
            
            try:
                batch_results = await retry_with_backoff(self._multi_request, actions)
                # Каждый запрос в multi возвращает результат
                results.extend([True] * len(batch))
            except Exception as e:
                logger.error(f"Ошибка батчевого обновления: {e}")
                results.extend([False] * len(batch))
        
        return results
    
    async def batch_store_media(
        self, 
        media_files: List[Dict[str, Any]]
    ) -> List[bool]:
        """Батчевое сохранение медиа файлов."""
        if not media_files:
            return []
        
        results = []
        batches = batch_items(media_files, self.batch_size)
        
        for batch in batches:
            actions = []
            for media in batch:
                b64_data = base64.b64encode(media["data"]).decode('utf-8')
                actions.append({
                    "action": "storeMediaFile",
                    "params": {
                        "filename": media["filename"],
                        "data": b64_data
                    }
                })
            
            try:
                await retry_with_backoff(self._multi_request, actions)
                results.extend([True] * len(batch))
            except Exception as e:
                logger.error(f"Ошибка батчевого сохранения медиа: {e}")
                results.extend([False] * len(batch))
        
        return results
    
    async def get_model_names(self) -> List[str]:
        """Получить список типов заметок."""
        return await retry_with_backoff(self._request, "modelNames")
    
    async def get_model_field_names(self, model_name: str) -> List[str]:
        """Получить поля типа заметки."""
        return await retry_with_backoff(
            self._request, "modelFieldNames", modelName=model_name
        )
    
    async def check_connection(self) -> bool:
        """Проверить соединение с Anki."""
        try:
            version = await self._request("version")
            logger.info(f"Подключен к AnkiConnect версии {version}")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к Anki: {e}")
            return False
