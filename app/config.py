"""
config.py — Загрузка, валидация и сохранение конфигурации.

Хосты загружаются/сохраняются в hosts.json.
Общие настройки приложения — из .env.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Путь к корню проекта (рядом с app/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOSTS_FILE = PROJECT_ROOT / "hosts.json"

# Загружаем переменные окружения из .env файла
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path, override=True)


@dataclass(frozen=True)
class SSHConfig:
    """Конфигурация SSH-подключения к удалённому серверу."""

    host: str
    port: int
    user: str
    auth_method: str  # "key" или "password"
    key_path: str | None
    password: str | None
    key_passphrase: str | None
    timeout: int


@dataclass(frozen=True)
class HostConfig:
    """Полная конфигурация одного хоста."""

    id: str
    name: str
    description: str
    ssh: SSHConfig
    storcli_path: str
    storcli_controller: str


@dataclass(frozen=True)
class AppConfig:
    """Конфигурация приложения."""

    host: str
    port: int
    debug_mode: bool


def get_app_config() -> AppConfig:
    """Создаёт и возвращает AppConfig из переменных окружения."""
    return AppConfig(
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true",
    )


# ───────────────────────────────────────────────────────────
# Загрузка хостов
# ───────────────────────────────────────────────────────────


def _load_raw_hosts() -> list[dict]:
    """Загружает сырой JSON-массив хостов из hosts.json."""
    if not HOSTS_FILE.exists():
        return []

    raw = HOSTS_FILE.read_text(encoding="utf-8")
    data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError("hosts.json должен содержать массив хостов")

    return data


def _entry_to_host_config(entry: dict, index: int) -> HostConfig:
    """Преобразует dict-запись из JSON в HostConfig."""
    ssh_timeout = int(os.getenv("SSH_TIMEOUT", "10"))
    ssh_data = entry.get("ssh", {})
    storcli_data = entry.get("storcli", {})

    return HostConfig(
        id=entry["id"],
        name=entry.get("name", entry["id"]),
        description=entry.get("description", ""),
        ssh=SSHConfig(
            host=ssh_data.get("host", "127.0.0.1"),
            port=int(ssh_data.get("port", 22)),
            user=ssh_data.get("user", "root"),
            auth_method=ssh_data.get("auth_method", "key"),
            key_path=ssh_data.get("key_path") or None,
            password=ssh_data.get("password") or None,
            key_passphrase=ssh_data.get("key_passphrase") or None,
            timeout=ssh_timeout,
        ),
        storcli_path=storcli_data.get("path", "/opt/lsi/storcli/storcli"),
        storcli_controller=storcli_data.get("controller", "/call"),
    )


def load_hosts() -> list[HostConfig]:
    """
    Загружает список хостов из файла hosts.json.

    Returns:
        Список HostConfig с описанием каждого сервера.
    """
    try:
        data = _load_raw_hosts()
    except json.JSONDecodeError as exc:
        raise ValueError(f"Невалидный JSON в hosts.json: {exc}") from exc

    hosts: list[HostConfig] = []

    for i, entry in enumerate(data):
        try:
            host_config = _entry_to_host_config(entry, i)
            hosts.append(host_config)
        except KeyError as exc:
            logger.error("Хост #%d: отсутствует обязательное поле %s", i, exc)
            raise ValueError(
                f"Хост #{i}: отсутствует обязательное поле {exc}"
            ) from exc

    logger.info("Загружено хостов: %d", len(hosts))
    return hosts


def get_host_by_id(host_id: str) -> HostConfig | None:
    """Находит хост по его ID."""
    hosts = load_hosts()
    for h in hosts:
        if h.id == host_id:
            return h
    return None


# ───────────────────────────────────────────────────────────
# CRUD-операции с hosts.json
# ───────────────────────────────────────────────────────────


def _save_raw_hosts(data: list[dict]) -> None:
    """Сохраняет массив хостов в hosts.json с форматированием."""
    HOSTS_FILE.write_text(
        json.dumps(data, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("hosts.json сохранён (%d хостов)", len(data))


def _generate_host_id(name: str, existing_ids: set[str]) -> str:
    """Генерирует уникальный slug-ID из имени хоста."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "host"
    candidate = slug
    counter = 1
    while candidate in existing_ids:
        counter += 1
        candidate = f"{slug}-{counter}"
    return candidate


def _host_dict_from_payload(payload: dict[str, Any]) -> dict:
    """Формирует dict для hosts.json из данных запроса."""
    return {
        "id": payload["id"],
        "name": payload.get("name", payload["id"]),
        "description": payload.get("description", ""),
        "ssh": {
            "host": payload.get("ssh_host", "127.0.0.1"),
            "port": int(payload.get("ssh_port", 22)),
            "user": payload.get("ssh_user", "root"),
            "auth_method": payload.get("ssh_auth_method", "password"),
            "key_path": payload.get("ssh_key_path", ""),
            "password": payload.get("ssh_password", ""),
            "key_passphrase": payload.get("ssh_key_passphrase", ""),
        },
        "storcli": {
            "path": payload.get("storcli_path", "/opt/lsi/storcli/storcli"),
            "controller": payload.get("storcli_controller", "/call"),
        },
    }


def add_host(payload: dict[str, Any]) -> dict:
    """
    Добавляет новый хост в hosts.json.

    Args:
        payload: Данные нового хоста из API-запроса.

    Returns:
        dict нового хоста, как он был сохранён.

    Raises:
        ValueError: Если хост с таким ID уже существует.
    """
    data = _load_raw_hosts()
    existing_ids = {entry["id"] for entry in data}

    # Генерируем ID, если не указан
    host_id = payload.get("id", "").strip()
    if not host_id:
        name = payload.get("name", "host")
        host_id = _generate_host_id(name, existing_ids)
        payload["id"] = host_id

    if host_id in existing_ids:
        raise ValueError(f"Хост с ID '{host_id}' уже существует")

    new_entry = _host_dict_from_payload(payload)
    data.append(new_entry)
    _save_raw_hosts(data)

    logger.info("Добавлен хост: %s (%s)", new_entry["name"], host_id)
    return new_entry


def update_host(host_id: str, payload: dict[str, Any]) -> dict:
    """
    Обновляет существующий хост в hosts.json.

    Args:
        host_id: ID хоста для обновления.
        payload: Новые данные хоста.

    Returns:
        dict обновлённого хоста.

    Raises:
        ValueError: Если хост не найден.
    """
    data = _load_raw_hosts()

    found_index = None
    for i, entry in enumerate(data):
        if entry.get("id") == host_id:
            found_index = i
            break

    if found_index is None:
        raise ValueError(f"Хост с ID '{host_id}' не найден")

    # Сохраняем ID неизменным
    payload["id"] = host_id
    updated_entry = _host_dict_from_payload(payload)
    data[found_index] = updated_entry
    _save_raw_hosts(data)

    logger.info("Обновлён хост: %s (%s)", updated_entry["name"], host_id)
    return updated_entry


def delete_host(host_id: str) -> None:
    """
    Удаляет хост из hosts.json.

    Args:
        host_id: ID хоста для удаления.

    Raises:
        ValueError: Если хост не найден.
    """
    data = _load_raw_hosts()
    new_data = [entry for entry in data if entry.get("id") != host_id]

    if len(new_data) == len(data):
        raise ValueError(f"Хост с ID '{host_id}' не найден")

    _save_raw_hosts(new_data)
    logger.info("Удалён хост: %s", host_id)


def get_host_full_data(host_id: str) -> dict | None:
    """
    Возвращает полные данные хоста (включая пароли) для редактирования.
    Используется ТОЛЬКО для формы редактирования.
    """
    data = _load_raw_hosts()
    for entry in data:
        if entry.get("id") == host_id:
            return entry
    return None
