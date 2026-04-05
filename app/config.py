"""
config.py — Загрузка и валидация конфигурации.

Хосты загружаются из hosts.json, общие настройки приложения — из .env.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

logger = logging.getLogger(__name__)

# Путь к корню проекта (рядом с app/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def load_hosts() -> list[HostConfig]:
    """
    Загружает список хостов из файла hosts.json.

    Returns:
        Список HostConfig с описанием каждого сервера.

    Raises:
        FileNotFoundError: Если hosts.json не найден.
        ValueError: Если JSON невалидный или структура неверная.
    """
    hosts_file = PROJECT_ROOT / "hosts.json"
    ssh_timeout = int(os.getenv("SSH_TIMEOUT", "10"))

    if not hosts_file.exists():
        logger.warning("hosts.json не найден, используется пустой список хостов")
        return []

    try:
        raw = hosts_file.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Невалидный JSON в hosts.json: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("hosts.json должен содержать массив хостов")

    hosts: list[HostConfig] = []

    for i, entry in enumerate(data):
        try:
            ssh_data = entry.get("ssh", {})
            storcli_data = entry.get("storcli", {})

            host_config = HostConfig(
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
                storcli_controller=storcli_data.get("controller", "/c0"),
            )
            hosts.append(host_config)
            logger.info("Загружен хост: %s (%s)", host_config.name, host_config.ssh.host)

        except KeyError as exc:
            logger.error("Хост #%d: отсутствует обязательное поле %s", i, exc)
            raise ValueError(f"Хост #{i}: отсутствует обязательное поле {exc}") from exc

    logger.info("Загружено хостов: %d", len(hosts))
    return hosts


def get_host_by_id(host_id: str) -> HostConfig | None:
    """Находит хост по его ID."""
    hosts = load_hosts()
    for h in hosts:
        if h.id == host_id:
            return h
    return None
