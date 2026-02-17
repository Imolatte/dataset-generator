# Dataset Generator

Генератор синтетических датасетов для тестирования LLM-агентов.

Программа принимает на вход сырой markdown-документ с бизнес-требованиями и автоматически:
1. Извлекает **use cases** (бизнес-сценарии) и **policies** (правила/ограничения) с трассировкой до исходного текста (evidence).
2. Генерирует **test cases** — комбинации параметров для каждого use case.
3. Генерирует **dataset** — набор примеров (input/expected_output/evaluation_criteria) для тестирования LLM-агента.

Все артефакты соответствуют строгому Data Contract (Pydantic v2) и связаны перекрёстными ссылками.

## Требования

- Python 3.10+
- Google Gemini API key (бесплатный tier)

## Установка

```bash
pip install -r requirements.txt
```

Зависимости: `google-genai>=1.0.0`, `pydantic>=2.0`

## Настройка API-ключа

Вариант 1 — файл `.env`:
```bash
cp .env.example .env
# Впишите ваш ключ в .env
```

Вариант 2 — переменная окружения:
```bash
export GOOGLE_API_KEY=your_key_here
```

Бесплатный ключ можно получить на [Google AI Studio](https://aistudio.google.com/apikey).

## Использование

### Генерация датасета

```bash
python -m dataset_generator generate \
  --input example_input_raw_support_faq_and_tickets.md \
  --out out/support \
  --seed 42
```

Программа поддерживает **resume**: если промежуточные файлы (`use_cases.json`, `policies.json`, `test_cases.json`) уже существуют в `--out`, они будут загружены вместо повторной генерации.

### Валидация артефактов

```bash
python -m dataset_generator validate --out out/support
```

Валидатор проверяет:
- Соответствие JSON-структуры Data Contract (Pydantic-модели)
- Целостность перекрёстных ссылок (`use_case_id`, `test_case_id`, `policy_ids`)
- Минимальные количества (use cases >= 5, policies >= 5, test cases >= 3 на UC, examples >= 1 на TC)
- Покрытие форматов и типов source в metadata
- Корректность evidence (quote совпадает со строками исходного файла, если передан `--input`)

### Валидация с проверкой evidence

```bash
python -m dataset_generator validate \
  --out out/support \
  --input example_input_raw_support_faq_and_tickets.md
```

## Параметры CLI

### `generate`

| Параметр | По умолчанию | Описание |
|---|---|---|
| `--input` | (обязательный) | Путь к markdown-файлу с бизнес-требованиями |
| `--out` | (обязательный) | Директория для выходных файлов |
| `--seed` | `42` | Seed для воспроизводимости |
| `--n-use-cases` | `8` | Целевое количество use cases |
| `--n-test-cases-per-uc` | `5` | Количество test cases на use case |
| `--n-examples-per-tc` | `2` | Количество примеров на test case |
| `--model` | `gemini-2.0-flash` | Модель Gemini |
| `--temperature` | `0.7` | Temperature для генерации |

### `validate`

| Параметр | По умолчанию | Описание |
|---|---|---|
| `--out` | (обязательный) | Директория с артефактами для валидации |
| `--input` | (необязательный) | Путь к исходному markdown (для проверки evidence) |

## Структура проекта

```
dataset-generator/
├── dataset_generator/
│   ├── __init__.py              # Версия пакета
│   ├── __main__.py              # CLI: generate / validate
│   ├── config.py                # Конфигурация (API key, seed, модель)
│   ├── llm.py                   # Обёртка Google Gemini API (retry, rate limit)
│   ├── models.py                # Pydantic v2 модели (Data Contract)
│   ├── extractor.py             # Шаг 1: извлечение use cases + policies
│   ├── test_case_generator.py   # Шаг 2: генерация test cases
│   ├── dataset_generator.py     # Шаг 3: генерация dataset examples
│   └── validator.py             # Валидация артефактов
├── example_input_raw_support_faq_and_tickets.md   # Пример: FAQ интернет-магазина
├── example_input_raw_operator_quality_checks.md   # Пример: проверки оператора медклиники
├── example_input_raw_doctor_booking.md             # Пример: запись к врачу (стоматология)
├── out/
│   ├── support/                 # Предгенерированные артефакты (support_bot)
│   └── operator_quality/        # Предгенерированные артефакты (operator_quality)
├── requirements.txt
├── .env.example
└── README.md
```

## Data Contract

Все выходные файлы соответствуют строгой JSON-схеме:

### `use_cases.json`
```json
{
  "use_cases": [
    {
      "id": "uc_delivery_status",
      "case": "support_bot",
      "name": "Статус доставки",
      "description": "Клиент спрашивает, где его заказ...",
      "evidence": [
        {
          "input_file": "example_input_raw_support_faq_and_tickets.md",
          "line_start": 15,
          "line_end": 20,
          "quote": "Точная цитата из исходного файла"
        }
      ]
    }
  ]
}
```

### `policies.json`
```json
{
  "policies": [
    {
      "id": "pol_russian_language",
      "type": "must",
      "case": "support_bot",
      "statement": "Бот отвечает только на русском языке.",
      "evidence": [{ "input_file": "...", "line_start": 0, "line_end": 0, "quote": "..." }]
    }
  ]
}
```

Типы политик: `must`, `must_not`, `escalate`, `style`, `format`.

### `test_cases.json`
```json
{
  "test_cases": [
    {
      "id": "tc_delivery_status_angry_no_order",
      "case": "support_bot",
      "use_case_id": "uc_delivery_status",
      "parameters": { "tone": "angry", "has_order_id": false },
      "policy_ids": ["pol_russian_language", "pol_polite_professional"]
    }
  ]
}
```

### `dataset.json`
```json
{
  "examples": [
    {
      "id": "ex_support_0001",
      "case": "support_bot",
      "format": "single_turn_qa",
      "use_case_id": "uc_delivery_status",
      "test_case_id": "tc_delivery_status_angry_no_order",
      "input": {
        "messages": [
          { "role": "user", "content": "ГДЕ МОЙ ЗАКАЗ???" }
        ]
      },
      "expected_output": "Здравствуйте! Для проверки статуса...",
      "evaluation_criteria": [
        "Ответ на русском языке",
        "Вежливый тон без ответной агрессии",
        "Запрос номера заказа для уточнения"
      ],
      "policy_ids": ["pol_russian_language", "pol_polite_professional"],
      "metadata": { "source": "faq_paraphrase" }
    }
  ]
}
```

Форматы: `single_turn_qa` (support_bot), `single_utterance_correction` / `dialog_last_turn_correction` (operator_quality).

### `run_manifest.json`
```json
{
  "input_path": "/path/to/input.md",
  "out_path": "/path/to/out/support",
  "seed": 42,
  "timestamp": "2025-02-16T12:00:00+00:00",
  "generator_version": "1.0.0",
  "llm": {
    "provider": "google",
    "model": "gemini-2.0-flash",
    "temperature": 0.7
  }
}
```

## Предгенерированные артефакты

В репозитории содержатся предгенерированные артефакты для двух кейсов:

| Кейс | Use Cases | Policies | Test Cases | Examples |
|---|---|---|---|---|
| `support_bot` | 7 | 11 | 21 | 42 |
| `operator_quality` | 5 | 12 | 15 | 30 |

Проверка валидатором:
```bash
python -m dataset_generator validate --out out/support
python -m dataset_generator validate --out out/operator_quality
# Оба завершаются с exit code 0
```

## Входные документы

| Файл | Описание | Язык |
|---|---|---|
| `example_input_raw_support_faq_and_tickets.md` | FAQ + тикеты интернет-магазина "ТехноМаркет" | RU |
| `example_input_raw_operator_quality_checks.md` | Стандарт качества оператора медклиники "Здоровье Плюс" | RU |
| `example_input_raw_doctor_booking.md` | Запись к врачу — стоматология "ДентаЛюкс" (усложнённый, разрозненные источники) | RU |

Документы написаны в свободном формате (как реальные бизнес-документы). Программа сама определяет тип кейса (`support_bot` / `operator_quality`) по содержимому.

## Архитектурные решения

- **LLM**: Google Gemini 2.0 Flash — бесплатный tier, 15 RPM, поддержка structured output
- **Structured output**: промпты с JSON-инструкциями + парсинг + валидация Pydantic
- **Evidence traceability**: LLM получает пронумерованные строки документа, возвращает `line_start`/`line_end`/`quote`, далее проверяется программно
- **Resume**: каждый шаг сохраняет результат на диск; при повторном запуске готовые шаги пропускаются
- **Anti-hardcode**: имена файлов, пути, количества — всё из CLI-аргументов
