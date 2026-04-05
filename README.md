# 🛡️ StorCLI RAID Monitor

Веб-приложение для мониторинга и управления RAID-массивами на удалённых серверах через SSH + StorCLI.

## 📋 Возможности

### Мониторинг
- Подключение к **нескольким серверам** по SSH (ключ или пароль)
- Поддержка **нескольких контроллеров** на одном сервере (`/call`)
- Дашборд с информацией о:
  - Контроллерах (модель, прошивка, статус)
  - Виртуальных дисках (VD) — RAID level, размер, состояние
  - Физических дисках (PD) — модель, размер, интерфейс, SMART
  - Топологии RAID-массива
  - Батарее (BBU)
- Цветовая индикация состояний (🟢 Optimal / 🟡 Degraded / 🔴 Critical)

### Управление хостами (CRUD)
- **Добавление** серверов через веб-интерфейс (кнопка «+ Добавить»)
- **Редактирование** — кнопка ✏️ на баннере текущего хоста
- **Удаление** — кнопка 🗑️ с подтверждением
- Все хосты сохраняются в `hosts.json`

### Управление RAID

Из интерфейса можно выполнять команды storcli двух уровней:

#### 🟢 Безопасные (выполняются без подтверждения)

| Кнопка | Действие | Объект | Команда storcli |
|--------|----------|--------|-----------------|
| 📍 | Включить LED | PD | `/cx/ex/sx start locate` |
| 💡 | Выключить LED | PD | `/cx/ex/sx stop locate` |
| 📊 | SMART Info | PD | `/cx/ex/sx show all J` |
| 📋 Event Log | Лог событий | Controller | `/cx show events type=latest=20 J` |

#### 🟡 Операционные (требуют подтверждения)

| Кнопка | Действие | Объект | Команда storcli |
|--------|----------|--------|-----------------|
| ♨️ | Global Hot Spare | PD | `/cx/ex/sx add hotsparedrive` |
| ❌ | Убрать Hot Spare | PD | `/cx/ex/sx delete hotsparedrive` |
| ✅ | Запустить CC | VD | `/cx/vX start cc` |
| ⏹️ | Остановить CC | VD | `/cx/vX stop cc` |
| 🔍 Patrol Read | Старт Patrol Read | Controller | `/cx start patrolread` |
| ⏹️ Stop Patrol | Стоп Patrol Read | Controller | `/cx stop patrolread` |
| 🔇 Silence Alarm | Выключить Alarm | Controller | `/cx set alarm=silence` |
| 🔄 | Запустить Rebuild | PD | `/cx/ex/sx start rebuild` |

> ⚠️ Операционные команды показывают модальное окно подтверждения перед выполнением. Все действия логируются на сервере.

## 🗂 Структура проекта

```
storecli/
├── app/
│   ├── __init__.py        # Пакет приложения
│   ├── config.py          # Загрузка конфигурации + CRUD хостов
│   ├── main.py            # FastAPI-приложение, маршруты, API
│   ├── parser.py          # Парсер JSON-вывода StorCLI (мультиконтроллер)
│   ├── commands.py        # Реестр команд управления StorCLI
│   └── ssh_client.py      # SSH-клиент (Paramiko)
├── static/
│   ├── index.html         # Главная HTML-страница
│   ├── style.css          # Стили дашборда (тёмная тема)
│   └── app.js             # Клиентская логика (Vanilla JS)
├── .env                   # Настройки приложения (APP_PORT, DEBUG_MODE)
├── .env.example           # Пример файла конфигурации
├── .gitignore
├── hosts.json             # Список серверов с SSH-настройками
├── Example.json           # Пример вывода storcli (для debug)
├── README.md
└── requirements.txt       # Python-зависимости
```

## 🚀 Быстрый запуск

### 1. Клонирование и установка

```bash
cd storecli
python -m venv venv

# Linux / macOS:
source venv/bin/activate

# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Настройка хостов

Отредактируйте `hosts.json` — добавьте ваши серверы:

```json
[
    {
        "id": "server-1",
        "name": "Основной сервер",
        "description": "ServeRAID M5014",
        "ssh": {
            "host": "192.168.1.100",
            "port": 22,
            "user": "root",
            "auth_method": "password",
            "key_path": "",
            "password": "your_password",
            "key_passphrase": ""
        },
        "storcli": {
            "path": "/opt/lsi/storcli/storcli",
            "controller": "/call"
        }
    }
]
```

> Хосты также можно добавлять через веб-интерфейс (кнопка «+ Добавить»).

**Параметры storcli.controller:**
- `/call` — опросить **все** контроллеры на хосте (рекомендуется)
- `/c0`, `/c1`, ... — только конкретный контроллер

### 3. Настройка приложения

Отредактируйте `.env`:

```env
APP_HOST=0.0.0.0
APP_PORT=8000
SSH_TIMEOUT=10
DEBUG_MODE=false
```

### 4. Запуск

```bash
python -m app.main
```

Приложение доступно: **http://localhost:8000**

## 🔧 Debug-режим

Для разработки без реального сервера:

```env
DEBUG_MODE=true
```

В debug-режиме:
- Данные мониторинга берутся из `Example.json`
- Команды управления **не выполняются** — возвращается mock-ответ

## 🔌 API

### Мониторинг

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/hosts` | Список серверов (без паролей) |
| `GET` | `/api/raid-status/{host_id}` | RAID-данные конкретного хоста |
| `GET` | `/api/raid-status` | RAID-данные первого хоста |

### Управление хостами

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/hosts/{host_id}` | Полные данные хоста (для формы) |
| `POST` | `/api/hosts` | Добавить хост |
| `PUT` | `/api/hosts/{host_id}` | Обновить хост |
| `DELETE` | `/api/hosts/{host_id}` | Удалить хост |

### Управление RAID

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/actions` | Список всех доступных действий |
| `POST` | `/api/action/{host_id}` | Выполнить команду storcli |

**Тело запроса `POST /api/action/{host_id}`:**
```json
{
    "action": "pd_locate_start",
    "controller_index": 0,
    "eid": "252",
    "slot": "0"
}
```

### Коды ошибок

| Код | Описание |
|-----|----------|
| 503 | Сервер недоступен по SSH |
| 502 | Ошибка выполнения команды storcli |
| 422 | Ошибка парсинга / валидации |
| 404 | Хост не найден |
| 409 | Хост с таким ID уже существует |
| 500 | Непредвиденная ошибка |

## 🔒 Безопасность

- `hosts.json` с учётными данными SSH включён в `.gitignore`
- Пароли **не отдаются** через `GET /api/hosts` (только `password_masked: true/false`)
- Операционные команды требуют подтверждения
- Все действия логируются на сервере с timestamp, host_id и командой
- В debug-режиме команды управления НЕ выполняются

## 📦 Зависимости

| Пакет | Назначение |
|-------|------------|
| FastAPI | Веб-фреймворк для API |
| Uvicorn | ASGI-сервер |
| Paramiko | SSH-клиент |
| python-dotenv | Загрузка .env |
