#!/usr/bin/env python3
"""Точка входа для запуска Anki обработчика."""

import sys
from pathlib import Path

# Добавляем корневую директорию в Python path
root_path = Path(__file__).parent
sys.path.insert(0, str(root_path))

from src.cli import cli_entry_point

if __name__ == "__main__":
    cli_entry_point()
