"""
main.py — Точка входа FastAPI-приложения для мониторинга RAID.

Предоставляет REST API для получения статуса RAID-массива
с нескольких удалённых серверов через SSH + StorCLI.
"""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_app_config, get_host_by_id, load_hosts
from app.parser import StorCLIParseError, parse_storcli_output
from app.ssh_client import SSHCommandError, SSHConnectionError, execute_remote_command

# ───────────────────────────────────────────────────────────
# Настройка логирования
# ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────
# Инициализация приложения
# ───────────────────────────────────────────────────────────
app = FastAPI(
    title="StorCLI RAID Monitor",
    description="Веб-приложение для мониторинга состояния RAID-массивов",
    version="2.0.0",
)

# Путь к директории со статическими файлами
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Монтируем статические файлы (CSS, JS, шрифты)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ───────────────────────────────────────────────────────────
# Маршруты
# ───────────────────────────────────────────────────────────
@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    """Отдаёт главную HTML-страницу дашборда."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/hosts")
async def list_hosts():
    """
    Возвращает список доступных хостов из hosts.json.

    Не отдаёт конфиденциальные данные (пароли, ключи).
    """
    try:
        hosts = load_hosts()
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Ошибка загрузки hosts.json: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "CONFIG_ERROR",
                "message": f"Ошибка загрузки конфигурации хостов: {exc}",
            },
        )

    # Отдаём только безопасные поля (без паролей и ключей)
    safe_hosts = [
        {
            "id": h.id,
            "name": h.name,
            "description": h.description,
            "host": h.ssh.host,
            "port": h.ssh.port,
        }
        for h in hosts
    ]

    return JSONResponse(content={"success": True, "hosts": safe_hosts})


@app.get("/api/raid-status/{host_id}")
async def get_raid_status(host_id: str):
    """
    API-эндпоинт: возвращает обработанные данные RAID-массива для конкретного хоста.

    Args:
        host_id: Уникальный идентификатор хоста из hosts.json.

    Returns:
        JSON с данными о контроллере, VD, PD, топологии и BBU.

    Raises:
        HTTPException 404: Хост не найден.
        HTTPException 503: Сервер недоступен по SSH.
        HTTPException 502: Ошибка выполнения команды storcli.
        HTTPException 422: Ошибка парсинга ответа storcli.
        HTTPException 500: Непредвиденная ошибка.
    """
    app_config = get_app_config()

    # ── Находим хост ──
    host = get_host_by_id(host_id)
    if host is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "HOST_NOT_FOUND",
                "message": f"Хост с ID '{host_id}' не найден в hosts.json",
            },
        )

    try:
        # ── Debug-режим: читаем Example.json вместо SSH ──
        if app_config.debug_mode:
            logger.info("DEBUG_MODE: хост '%s' — используется Example.json", host.name)
            example_path = PROJECT_ROOT / "Example.json"

            if not example_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail="DEBUG_MODE включён, но файл Example.json не найден",
                )

            raw_json = example_path.read_text(encoding="utf-8")
        else:
            # ── Рабочий режим: выполняем команду по SSH ──
            command = f"{host.storcli_path} {host.storcli_controller} show all J"
            logger.info("Запрос к хосту '%s' (%s)", host.name, host.ssh.host)
            raw_json = execute_remote_command(host.ssh, command)

        # ── Парсим и возвращаем данные ──
        parsed_data = parse_storcli_output(raw_json)

        # Добавляем информацию о хосте в ответ
        parsed_data["host"] = {
            "id": host.id,
            "name": host.name,
            "description": host.description,
            "address": host.ssh.host,
        }

        return JSONResponse(
            content={
                "success": True,
                "data": parsed_data,
            }
        )

    except SSHConnectionError as exc:
        logger.error("SSH connection failed for '%s': %s", host.name, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "SSH_CONNECTION_ERROR",
                "message": f"Не удалось подключиться к серверу '{host.name}': {exc}",
            },
        )

    except SSHCommandError as exc:
        logger.error("SSH command failed for '%s': %s", host.name, exc)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "COMMAND_ERROR",
                "message": f"Ошибка выполнения storcli на '{host.name}': {exc}",
            },
        )

    except StorCLIParseError as exc:
        logger.error("Parse error for '%s': %s", host.name, exc)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "PARSE_ERROR",
                "message": f"Ошибка обработки ответа storcli от '{host.name}': {exc}",
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Unexpected error for '%s': %s", host.name, exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": f"Непредвиденная ошибка: {exc}",
            },
        )


# ── Обратная совместимость: старый эндпоинт без host_id ──
@app.get("/api/raid-status")
async def get_raid_status_default():
    """
    Эндпоинт без host_id — берёт первый хост из конфига.
    Обеспечивает обратную совместимость.
    """
    try:
        hosts = load_hosts()
    except (FileNotFoundError, ValueError):
        hosts = []

    if not hosts:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NO_HOSTS",
                "message": "Нет настроенных хостов. Добавьте хосты в hosts.json.",
            },
        )

    return await get_raid_status(hosts[0].id)


# ───────────────────────────────────────────────────────────
# Запуск приложения
# ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    config = get_app_config()
    logger.info("Запуск StorCLI RAID Monitor на %s:%d", config.host, config.port)

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=True,
    )
