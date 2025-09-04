"""Командный интерфейс для обработки заметок Anki."""

import asyncio
import sys
from typing import List, Optional, Tuple

from loguru import logger

from .anki_client import AnkiClient
from .config import NOTE_TYPE_CONFIGS
from .pipeline import ProcessingPipeline
from .settings import PROCESSING_CONFIG
from .validators import NoteValidator


class CLIInterface:
    """Интерфейс командной строки."""
    
    def __init__(self):
        self.anki_client = AnkiClient()
        self.pipeline = ProcessingPipeline()
        self.validator = NoteValidator()
    
    async def run(self):
        """Запуск главного интерфейса."""
        print("=== Anki English Learning Assistant ===\n")
        
        try:
            # Инициализация
            await self._initialize()
            
            # Выбор колоды
            deck_name = await self._select_deck()
            if not deck_name:
                return
            
            # Выбор типа заметки
            note_type_name = await self._select_note_type(deck_name)
            if not note_type_name:
                return
            
            # Подтверждение конфигурации
            confirmed = await self._confirm_configuration(deck_name, note_type_name)
            if not confirmed:
                return
            
            # Превью и валидация
            preview_ok = await self._show_preview(deck_name, note_type_name)
            if not preview_ok:
                return
            
            # Запуск обработки
            await self._run_processing(deck_name, note_type_name)
            
        except KeyboardInterrupt:
            print("\nОбработка прервана пользователем")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            print(f"Критическая ошибка: {e}")
        finally:
            print("Завершение работы...")
    
    async def _initialize(self):
        """Инициализация системы."""
        print("Инициализация...")
        
        # Проверяем подключение к Anki
        if not await self.anki_client.check_connection():
            raise RuntimeError(
                "Не удалось подключиться к Anki.\n"
                "Убедитесь, что Anki запущен и AnkiConnect установлен."
            )
        
        # Инициализируем пайплайн
        await self.pipeline.initialize()
        
        print("✓ Система инициализирована\n")
    
    async def _select_deck(self) -> Optional[str]:
        """Выбор колоды."""
        print("Получение списка колод...")
        decks = await self.anki_client.get_deck_names()
        
        if not decks:
            print("Ошибка: Не найдено ни одной колоды")
            return None
        
        print(f"\nДоступные колоды ({len(decks)}):")
        for i, deck in enumerate(decks, 1):
            print(f"  {i}. {deck}")
        
        while True:
            try:
                choice = input(f"\nВыберите колоду (1-{len(decks)}) или 'q' для выхода: ").strip()
                
                if choice.lower() == 'q':
                    return None
                
                index = int(choice) - 1
                if 0 <= index < len(decks):
                    selected_deck = decks[index]
                    print(f"✓ Выбрана колода: {selected_deck}\n")
                    return selected_deck
                else:
                    print("Ошибка: Неверный номер колоды")
                    
            except ValueError:
                print("Ошибка: Введите число")
    
    async def _select_note_type(self, deck_name: str) -> Optional[str]:
        """Выбор типа заметки."""
        # Получаем доступные типы заметок
        available_types = await self.anki_client.get_model_names()
        
        # Фильтруем только те, которые есть в конфигурации
        supported_types = [
            note_type for note_type in available_types 
            if note_type in NOTE_TYPE_CONFIGS
        ]
        
        if not supported_types:
            print("Ошибка: Не найдено поддерживаемых типов заметок")
            print(f"Поддерживаемые типы: {list(NOTE_TYPE_CONFIGS.keys())}")
            return None
        
        print(f"Поддерживаемые типы заметок ({len(supported_types)}):")
        for i, note_type in enumerate(supported_types, 1):
            print(f"  {i}. {note_type}")
        
        while True:
            try:
                choice = input(f"\nВыберите тип заметки (1-{len(supported_types)}) или 'q' для выхода: ").strip()
                
                if choice.lower() == 'q':
                    return None
                
                index = int(choice) - 1
                if 0 <= index < len(supported_types):
                    selected_type = supported_types[index]
                    print(f"✓ Выбран тип заметки: {selected_type}\n")
                    return selected_type
                else:
                    print("Ошибка: Неверный номер типа")
                    
            except ValueError:
                print("Ошибка: Введите число")
    
    async def _confirm_configuration(self, deck_name: str, note_type_name: str) -> bool:
        """Подтверждение конфигурации."""
        config = NOTE_TYPE_CONFIGS[note_type_name]
        
        print("=== КОНФИГУРАЦИЯ ОБРАБОТКИ ===")
        print(f"Колода: {deck_name}")
        print(f"Тип заметки: {note_type_name}")
        print(f"Сухой прогон: {'Да' if PROCESSING_CONFIG.dry_run else 'Нет'}")
        print(f"Пропуск аудио: {'Да' if PROCESSING_CONFIG.skip_audio else 'Нет'}")
        print(f"Пропуск частотности: {'Да' if PROCESSING_CONFIG.skip_frequency else 'Нет'}")
        print(f"Пропуск невалидных заметок: {'Да' if PROCESSING_CONFIG.skip_invalid_notes else 'Нет'}")
        
        if PROCESSING_CONFIG.force_regenerate:
            print(f"Принудительная регенерация: {', '.join(PROCESSING_CONFIG.force_regenerate)}")
        
        print(f"\nПоля для обработки:")
        print(f"  INPUT (должны быть заполнены): {config.input_fields}")
        print(f"  GENERATE (будут заполнены): {config.generate_fields}")
        
        # Проверяем совместимость полей
        anki_fields = await self.anki_client.get_model_field_names(note_type_name)
        compatible, missing = self.validator.validate_note_type_compatibility(
            anki_fields, note_type_name
        )
        
        if not compatible:
            print(f"\n⚠️  ПРЕДУПРЕЖДЕНИЕ: Отсутствующие поля в Anki: {missing}")
        
        while True:
            choice = input("\nПродолжить обработку? (y/n): ").strip().lower()
            if choice in ['y', 'yes', 'да']:
                return True
            elif choice in ['n', 'no', 'нет']:
                return False
            else:
                print("Введите 'y' или 'n'")
    
    async def _show_preview(self, deck_name: str, note_type_name: str) -> bool:
        """Показать превью и валидацию."""
        print("Получение превью заметок...")
        
        preview = await self.pipeline.get_deck_preview(deck_name, note_type_name)
        
        print(f"\n=== ПРЕВЬЮ КОЛОДЫ ===")
        print(f"Всего заметок: {preview['total_notes']}")
        
        if preview['total_notes'] == 0:
            print("Заметки не найдены")
            return False
        
        # Показываем валидацию
        validation = preview['validation']
        print(f"Валидных заметок: {validation['valid_notes']}")
        print(f"Невалидных заметок: {validation['invalid_notes']}")
        
        if validation['invalid_notes'] > 0:
            print(f"⚠️  Найдено {validation['error_count']} ошибок валидации")
            
            show_errors = input("Показать детали ошибок? (y/n): ").strip().lower()
            if show_errors in ['y', 'yes', 'да']:
                await self._show_validation_errors(deck_name, note_type_name)
        
        # Показываем примеры заметок
        if preview['sample_notes']:
            print(f"\nПример заметок (первые {len(preview['sample_notes'])}):")
            for note in preview['sample_notes']:
                print(f"  ID {note['note_id']}: {note['fields']}")
        
        # Подтверждение продолжения
        if validation['invalid_notes'] > 0:
            if PROCESSING_CONFIG.skip_invalid_notes:
                print(f"\n📋 ИНФОРМАЦИЯ: {validation['invalid_notes']} невалидных заметок будут пропущены автоматически")
                print(f"Будут обработаны только {validation['valid_notes']} валидных заметок")
            elif not PROCESSING_CONFIG.dry_run:
                print(f"\n⚠️  ВНИМАНИЕ: {validation['invalid_notes']} заметок не будут обработаны из-за ошибок валидации")
                
                while True:
                    choice = input("Продолжить с валидными заметками? (y/n): ").strip().lower()
                    if choice in ['y', 'yes', 'да']:
                        return True
                    elif choice in ['n', 'no', 'нет']:
                        return False
                    else:
                        print("Введите 'y' или 'n'")
        
        return True
    
    async def _show_validation_errors(self, deck_name: str, note_type_name: str):
        """Показать детальные ошибки валидации."""
        # Получаем заметки и валидируем
        query = f'deck:"{deck_name}" note:"{note_type_name}"'
        note_ids = await self.anki_client.find_notes(query)
        notes = await self.anki_client.get_notes_info(note_ids)
        
        validation_report = self.validator.validate_notes(notes, note_type_name)
        
        if validation_report.errors:
            print("\n=== ДЕТАЛИ ОШИБОК ВАЛИДАЦИИ ===")
            print(self.validator.print_validation_report(validation_report))
    
    async def _run_processing(self, deck_name: str, note_type_name: str):
        """Запуск основной обработки."""
        if PROCESSING_CONFIG.dry_run:
            print("🔄 Запуск СУХОГО ПРОГОНА (заметки не будут изменены)")
        else:
            print("🔄 Запуск обработки заметок...")
        
        result = await self.pipeline.process_deck(deck_name, note_type_name)
        
        if result.success:
            print("✅ Обработка завершена успешно!")
            if result.error:  # Содержит статистику
                print(f"📊 {result.error}")
        else:
            print("❌ Обработка завершена с ошибками")
            if result.error:
                print(f"📊 {result.error}")
    
    def _handle_interrupt(self):
        """Обработка прерывания."""
        print("\n\nПолучен сигнал прерывания...")
        print("Завершение текущих операций...")
        # Здесь можно добавить логику graceful shutdown


async def main():
    """Точка входа в CLI."""
    cli = CLIInterface()
    await cli.run()


def cli_entry_point():
    """Синхронная точка входа для setuptools."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}")
        print(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_entry_point()
