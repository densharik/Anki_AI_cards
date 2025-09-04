"""Модуль для работы с частотностью слов."""

import json
from pathlib import Path
from typing import Optional

from loguru import logger
from wordfreq import word_frequency, zipf_frequency

from .schemas import FrequencyData
from .settings import FREQ_DICT_PATH


class FrequencyCalculator:
    """Калькулятор частотности слов."""
    
    def __init__(self):
        self.local_dict: dict = {}
        self.load_local_dictionary()
    
    def load_local_dictionary(self):
        """Загрузить локальный словарь частот."""
        if not FREQ_DICT_PATH:
            logger.info("Путь к словарю частот не указан, используем только wordfreq")
            return
        
        dict_path = Path(FREQ_DICT_PATH)
        if not dict_path.exists():
            logger.info(f"Словарь частот не найден: {FREQ_DICT_PATH}")
            return
        
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Конвертируем в удобный формат: слово -> данные о частоте
            if isinstance(data, list):
                # Проверяем формат данных
                if data and "id" in data[0] and "word" in data[0]:
                    # Формат: [{"id": 1, "word": "THE"}, ...]
                    self.local_dict = {
                        item["word"].lower(): {"rank": item["id"], "frequency": 1.0 / item["id"]}
                        for item in data 
                        if "word" in item and "id" in item
                    }
                else:
                    # Формат: [{"word": "...", "frequency": ..., "rank": ...}, ...]
                    self.local_dict = {
                        item["word"].lower(): item 
                        for item in data 
                        if "word" in item
                    }
            elif isinstance(data, dict):
                # Формат: {"word": {"frequency": ..., "rank": ...}, ...}
                self.local_dict = {
                    word.lower(): freq_data 
                    for word, freq_data in data.items()
                }
            
            logger.info(f"Загружен локальный словарь частот: {len(self.local_dict)} слов")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки словаря частот: {e}")
            self.local_dict = {}
    
    def get_frequency_data(self, word: str, lemma: str = None) -> FrequencyData:
        """
        Получить данные о частотности слова.
        
        Args:
            word: Исходное слово
            lemma: Лемма слова (базовая форма)
            
        Returns:
            FrequencyData с информацией о частотности
        """
        # Приоритет: lemma > word
        search_word = (lemma or word).lower().strip()
        
        if not search_word:
            return FrequencyData(
                word=word,
                frequency=0.0,
                rank=None,
                zipf_score=0.0
            )
        
        # Сначала ищем в локальном словаре
        local_data = self._get_local_frequency(search_word)
        if local_data:
            return local_data
        
        # Если не найден локально, используем wordfreq
        return self._get_wordfreq_data(search_word)
    
    def _get_local_frequency(self, word: str) -> Optional[FrequencyData]:
        """Получить частотность из локального словаря."""
        if word not in self.local_dict:
            return None
        
        data = self.local_dict[word]
        
        try:
            return FrequencyData(
                word=word,
                frequency=float(data.get("frequency", 0)),
                rank=data.get("rank"),
                zipf_score=data.get("zipf_score")
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Некорректные данные в словаре для '{word}': {e}")
            return None
    
    def _get_wordfreq_data(self, word: str) -> FrequencyData:
        """Получить частотность через библиотеку wordfreq."""
        try:
            # Частота слова (от 0 до 1)
            frequency = word_frequency(word, 'en')
            
            # Zipf score (логарифмическая шкала, обычно 0-8)
            zipf_score = zipf_frequency(word, 'en')
            
            logger.debug(f"wordfreq для '{word}': freq={frequency}, zipf={zipf_score}")
            
            return FrequencyData(
                word=word,
                frequency=frequency,
                rank=None,  # wordfreq не предоставляет rank
                zipf_score=zipf_score
            )
            
        except Exception as e:
            logger.warning(f"Ошибка получения частотности для '{word}': {e}")
            return FrequencyData(
                word=word,
                frequency=0.0,
                rank=None,
                zipf_score=0.0
            )
    
    def get_frequency_rank(self, word: str, lemma: str = None) -> str:
        """
        Получить ранг частотности как строку для поля FreqSort.
        
        Returns:
            Строка с рангом или пустая строка
        """
        freq_data = self.get_frequency_data(word, lemma)
        
        # Приоритет: rank из локального словаря
        if freq_data.rank is not None:
            return str(freq_data.rank)
        
        # Если нет rank, используем zipf_score
        if freq_data.zipf_score and freq_data.zipf_score > 0:
            # Записываем zipf score с приставкой
            zipf_value = round(freq_data.zipf_score, 2)
            logger.debug(f"Zipf для '{word}': {zipf_value}")
            return f"zipf {zipf_value}"
        
        # Если есть только frequency
        if freq_data.frequency and freq_data.frequency > 0:
            estimated_rank = int(1 / freq_data.frequency)
            return str(max(1, min(estimated_rank, 999999)))
        
        # Если ничего нет, возвращаем высокий ранг
        return "999999"
    
    def is_common_word(self, word: str, lemma: str = None, threshold: float = 5.0) -> bool:
        """
        Проверить, является ли слово частым.
        
        Args:
            word: Слово для проверки
            lemma: Лемма слова
            threshold: Минимальный zipf score для "частого" слова
            
        Returns:
            True если слово частое
        """
        freq_data = self.get_frequency_data(word, lemma)
        
        if freq_data.rank and freq_data.rank <= 3000:
            return True
        
        if freq_data.zipf_score and freq_data.zipf_score >= threshold:
            return True
        
        return False
    
    def get_frequency_category(self, word: str, lemma: str = None) -> str:
        """
        Получить категорию частотности слова.
        
        Returns:
            Одна из категорий: "very_common", "common", "uncommon", "rare"
        """
        freq_data = self.get_frequency_data(word, lemma)
        
        if freq_data.rank:
            if freq_data.rank <= 1000:
                return "very_common"
            elif freq_data.rank <= 5000:
                return "common"
            elif freq_data.rank <= 20000:
                return "uncommon"
            else:
                return "rare"
        
        if freq_data.zipf_score:
            if freq_data.zipf_score >= 6.5:
                return "very_common"
            elif freq_data.zipf_score >= 5.5:
                return "common"
            elif freq_data.zipf_score >= 4.0:
                return "uncommon"
            else:
                return "rare"
        
        return "rare"
    
    def save_frequency_cache(self, cache_data: dict, cache_path: Path):
        """Сохранить кеш частотности в файл."""
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Кеш частотности сохранен: {len(cache_data)} записей")
        except Exception as e:
            logger.error(f"Ошибка сохранения кеша частотности: {e}")
    
    def load_frequency_cache(self, cache_path: Path) -> dict:
        """Загрузить кеш частотности из файла."""
        if not cache_path.exists():
            return {}
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки кеша частотности: {e}")
            return {}
