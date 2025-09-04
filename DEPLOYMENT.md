# Руководство по развертыванию

## Локальная установка

### Требования
- Python 3.11+
- Anki с установленным AnkiConnect
- OpenAI API ключ

### Установка
```bash
# 1. Клонирование
git clone <repository-url>
cd anki-processor

# 2. Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# 3. Установка зависимостей
pip install -r requirements.txt

# 4. Настройка переменных окружения
cp env_example.txt .env
# Отредактируйте .env

# 5. Запуск
python run.py
```

### Мониторинг
- Логи: `anki_processor.log`
