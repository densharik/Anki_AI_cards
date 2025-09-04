"""Утилиты для обработки ошибок, retry логики и батчинга."""

import asyncio
import time
from typing import Any, Callable, List, TypeVar

from loguru import logger

from .config import RETRY_CONFIG

T = TypeVar('T')


async def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = RETRY_CONFIG["max_retries"],
    base_delay: float = RETRY_CONFIG["base_delay"],
    max_delay: float = RETRY_CONFIG["max_delay"],
    exponential_base: float = RETRY_CONFIG["exponential_base"],
    **kwargs
) -> Any:
    """Повторить функцию с экспоненциальной задержкой."""
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(f"Исчерпаны попытки для {func.__name__}: {e}")
                break
                
            # Проверяем специальные коды ошибок
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                delay = min(base_delay * (exponential_base ** attempt), max_delay)
                logger.warning(f"Rate limit для {func.__name__}, повтор через {delay}s")
                await asyncio.sleep(delay)
            elif "5" in str(getattr(e, 'status_code', '')) and str(getattr(e, 'status_code', '')).startswith('5'):
                delay = min(base_delay * (exponential_base ** attempt), max_delay)
                logger.warning(f"Серверная ошибка для {func.__name__}, повтор через {delay}s")
                await asyncio.sleep(delay)
            else:
                # Для других ошибок не повторяем
                logger.error(f"Неповторимая ошибка в {func.__name__}: {e}")
                break
    
    raise last_exception


def batch_items(items: List[T], batch_size: int) -> List[List[T]]:
    """Разделить список на батчи заданного размера."""
    if batch_size <= 0:
        raise ValueError("batch_size должен быть больше 0")
    
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i:i + batch_size])
    return batches


class AsyncSemaphorePool:
    """Пул семафоров для контроля параллелизма различных операций."""
    
    def __init__(self, limits: dict[str, int]):
        self._semaphores = {
            name: asyncio.Semaphore(limit) 
            for name, limit in limits.items()
        }
    
    def get_semaphore(self, name: str) -> asyncio.Semaphore:
        """Получить семафор по имени."""
        if name not in self._semaphores:
            raise ValueError(f"Семафор {name} не найден")
        return self._semaphores[name]
    
    async def run_with_semaphore(self, name: str, coro):
        """Выполнить корутину с ограничением семафора."""
        async with self.get_semaphore(name):
            return await coro


def generate_cache_key(*args) -> str:
    """Генерация стабильного ключа кеша из аргументов."""
    key_parts = []
    for arg in args:
        if isinstance(arg, (str, int, float)):
            key_parts.append(str(arg))
        elif isinstance(arg, (list, tuple)):
            key_parts.append("|".join(str(x) for x in arg))
        elif isinstance(arg, dict):
            sorted_items = sorted(arg.items())
            key_parts.append("|".join(f"{k}:{v}" for k, v in sorted_items))
        else:
            key_parts.append(str(hash(str(arg))))
    
    return "_".join(key_parts).lower().replace(" ", "_")


class ProgressTracker:
    """Отслеживание прогресса обработки."""
    
    def __init__(self, total: int, description: str = "Обработка"):
        self.total = total
        self.processed = 0
        self.errors = 0
        self.start_time = time.time()
        self.description = description
    
    def update(self, success: bool = True):
        """Обновить счетчики."""
        self.processed += 1
        if not success:
            self.errors += 1
        
        if self.processed % 10 == 0 or self.processed == self.total:
            self._log_progress()
    
    def _log_progress(self):
        """Логирование прогресса."""
        elapsed = time.time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        
        logger.info(
            f"{self.description}: {self.processed}/{self.total} "
            f"({self.processed/self.total*100:.1f}%) "
            f"Ошибок: {self.errors} "
            f"Скорость: {rate:.1f}/сек"
        )
    
    def finish(self):
        """Финальная статистика."""
        elapsed = time.time() - self.start_time
        logger.info(
            f"{self.description} завершена: {self.processed}/{self.total} "
            f"за {elapsed:.1f}сек. Ошибок: {self.errors}"
        )


async def run_with_timeout(coro, timeout: float):
    """Выполнить корутину с таймаутом."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Таймаут {timeout}сек для операции")
        raise


def safe_filename(text: str, max_length: int = 100) -> str:
    """Создать безопасное имя файла из текста."""
    import re
    
    # Убираем опасные символы
    safe = re.sub(r'[<>:"/\\|?*]', '_', text)
    # Убираем лишние пробелы и символы
    safe = re.sub(r'\s+', '_', safe.strip())
    # Ограничиваем длину
    if len(safe) > max_length:
        safe = safe[:max_length]
    
    return safe.lower()


class RateLimiter:
    """Ограничитель скорости запросов."""
    
    def __init__(self, max_requests: int, time_window: float):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    async def acquire(self):
        """Получить разрешение на запрос."""
        now = time.time()
        
        # Убираем старые запросы
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < self.time_window]
        
        # Проверяем лимит
        if len(self.requests) >= self.max_requests:
            sleep_time = self.time_window - (now - self.requests[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                return await self.acquire()
        
        self.requests.append(now)
        return True
