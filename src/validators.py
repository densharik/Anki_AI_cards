"""Модуль для валидации заметок и полей."""

from typing import List, Optional

from loguru import logger

from .config import NOTE_TYPE_CONFIGS
from .schemas import (
    AnkiNote,
    FieldMode,
    NoteTypeConfig,
    ValidationError,
    ValidationReport
)


class NoteValidator:
    """Валидатор заметок Anki."""
    
    def __init__(self):
        self.note_type_configs = NOTE_TYPE_CONFIGS
    
    def validate_notes(
        self, 
        notes: List[AnkiNote], 
        note_type_name: str
    ) -> ValidationReport:
        """
        Валидировать список заметок по конфигурации типа.
        
        Args:
            notes: Список заметок для валидации
            note_type_name: Имя типа заметки
            
        Returns:
            ValidationReport с результатами валидации
        """
        if note_type_name not in self.note_type_configs:
            raise ValueError(f"Неизвестный тип заметки: {note_type_name}")
        
        config = self.note_type_configs[note_type_name]
        errors = []
        valid_count = 0
        
        for note in notes:
            note_errors = self._validate_single_note(note, config)
            if note_errors:
                errors.extend(note_errors)
            else:
                valid_count += 1
        
        return ValidationReport(
            total_notes=len(notes),
            valid_notes=valid_count,
            invalid_notes=len(notes) - valid_count,
            errors=errors
        )
    
    def _validate_single_note(
        self, 
        note: AnkiNote, 
        config: NoteTypeConfig
    ) -> List[ValidationError]:
        """Валидировать одну заметку."""
        errors = []
        
        # Проверяем модель заметки
        if note.model_name != config.name:
            errors.append(ValidationError(
                note_id=note.note_id,
                field_name="model_name",
                expected_mode=FieldMode.INPUT,  # Формальное значение
                current_value=note.model_name,
                error_message=f"Ожидается модель '{config.name}', получена '{note.model_name}'"
            ))
            return errors  # Если модель не совпадает, дальше не проверяем
        
        # Проверяем каждое поле по конфигурации
        for field_name, field_config in config.fields.items():
            current_value = note.fields.get(field_name, "").strip()
            
            # Валидация по режиму поля
            field_error = self._validate_field(
                note.note_id,
                field_name,
                current_value,
                field_config.mode
            )
            
            if field_error:
                errors.append(field_error)
        
        return errors
    
    def _validate_field(
        self,
        note_id: int,
        field_name: str,
        current_value: str,
        expected_mode: FieldMode
    ) -> Optional[ValidationError]:
        """Валидировать отдельное поле."""
        if expected_mode == FieldMode.INPUT:
            # INPUT поля должны быть заполнены
            if not current_value:
                return ValidationError(
                    note_id=note_id,
                    field_name=field_name,
                    expected_mode=expected_mode,
                    current_value=current_value,
                    error_message=f"Поле '{field_name}' (INPUT) должно быть заполнено"
                )
        
        elif expected_mode == FieldMode.GENERATE:
            # GENERATE поля должны быть пустыми перед обработкой
            if current_value:
                return ValidationError(
                    note_id=note_id,
                    field_name=field_name,
                    expected_mode=expected_mode,
                    current_value=current_value,
                    error_message=f"Поле '{field_name}' (GENERATE) должно быть пустым перед обработкой"
                )
        
        # SKIP поля не валидируем
        return None
    
    def filter_valid_notes(
        self, 
        notes: List[AnkiNote], 
        note_type_name: str
    ) -> List[AnkiNote]:
        """
        Отфильтровать только валидные заметки.
        
        Returns:
            Список заметок, прошедших валидацию
        """
        if note_type_name not in self.note_type_configs:
            logger.error(f"Неизвестный тип заметки: {note_type_name}")
            return []
        
        config = self.note_type_configs[note_type_name]
        valid_notes = []
        
        for note in notes:
            errors = self._validate_single_note(note, config)
            if not errors:
                valid_notes.append(note)
            else:
                logger.debug(f"Заметка {note.note_id} не прошла валидацию: {len(errors)} ошибок")
        
        return valid_notes
    
    def print_validation_report(self, report: ValidationReport) -> str:
        """Создать текстовый отчет о валидации."""
        lines = [
            f"=== ОТЧЕТ О ВАЛИДАЦИИ ===",
            f"Всего заметок: {report.total_notes}",
            f"Валидных: {report.valid_notes}",
            f"Невалидных: {report.invalid_notes}",
            f"Процент валидных: {report.valid_notes/report.total_notes*100:.1f}%"
        ]
        
        if report.errors:
            lines.append(f"\n=== ОШИБКИ ВАЛИДАЦИИ ({len(report.errors)}) ===")
            
            # Группируем ошибки по заметкам
            errors_by_note = {}
            for error in report.errors:
                if error.note_id not in errors_by_note:
                    errors_by_note[error.note_id] = []
                errors_by_note[error.note_id].append(error)
            
            for note_id, note_errors in errors_by_note.items():
                lines.append(f"\nЗаметка {note_id}:")
                for error in note_errors:
                    lines.append(f"  - {error.field_name} ({error.expected_mode.value}): {error.error_message}")
                    if error.current_value:
                        lines.append(f"    Текущее значение: '{error.current_value[:100]}...'")
        
        return "\n".join(lines)
    
    def get_field_requirements(self, note_type_name: str) -> dict:
        """Получить требования к полям для типа заметки."""
        if note_type_name not in self.note_type_configs:
            return {}
        
        config = self.note_type_configs[note_type_name]
        requirements = {
            "input_fields": [],
            "generate_fields": [],
            "skip_fields": []
        }
        
        for field_name, field_config in config.fields.items():
            if field_config.mode == FieldMode.INPUT:
                requirements["input_fields"].append(field_name)
            elif field_config.mode == FieldMode.GENERATE:
                requirements["generate_fields"].append(field_name)
            else:
                requirements["skip_fields"].append(field_name)
        
        return requirements
    
    def validate_note_type_compatibility(
        self, 
        anki_fields: List[str], 
        note_type_name: str
    ) -> tuple[bool, List[str]]:
        """
        Проверить совместимость полей Anki с конфигурацией.
        
        Args:
            anki_fields: Список полей из Anki
            note_type_name: Имя типа заметки
            
        Returns:
            (совместимость, список отсутствующих полей)
        """
        if note_type_name not in self.note_type_configs:
            return False, [f"Неизвестный тип заметки: {note_type_name}"]
        
        config = self.note_type_configs[note_type_name]
        required_fields = set(config.fields.keys())
        available_fields = set(anki_fields)
        
        missing_fields = list(required_fields - available_fields)
        
        return len(missing_fields) == 0, missing_fields
    
    def check_processing_readiness(
        self, 
        notes: List[AnkiNote], 
        note_type_name: str
    ) -> tuple[bool, str]:
        """
        Проверить готовность заметок к обработке.
        
        Returns:
            (готовность, сообщение)
        """
        if not notes:
            return False, "Нет заметок для обработки"
        
        report = self.validate_notes(notes, note_type_name)
        
        if report.invalid_notes == 0:
            return True, f"Все {report.total_notes} заметок готовы к обработке"
        else:
            return False, (
                f"Найдены ошибки валидации: {report.invalid_notes} из {report.total_notes} заметок невалидны. "
                f"Исправьте ошибки или измените конфигурацию."
            )
