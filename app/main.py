"""
main.py — Точка входа FastAPI-приложения для мониторинга RAID.

Предоставляет REST API для:
  - Аутентификации (cookie-сессии)
  - Получения статуса RAID-массива с удалённых серверов (SSH + StorCLI)
  - CRUD-управления конфигурацией хостов (hosts.json)
  - Выполнения команд управления (Locate, Rebuild, Hot Spare и т.д.)
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import (
    create_session_token,
    is_public_path,
    validate_session_token,
    verify_credentials,
)
from app.commands import build_command, get_all_actions, get_command
from app.config import (
    add_host,
    delete_host,
    get_app_config,
    get_host_by_id,
    get_host_full_data,
    load_hosts,
    update_host,
)
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
    description="Веб-приложение для мониторинга и управления RAID-массивами",
    version="2.3.0",
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ───────────────────────────────────────────────────────────
# Middleware: Проверка авторизации
# ───────────────────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Проверяет cookie-сессию на каждый запрос."""
    path = request.url.path

    # Публичные пути — пропускаем
    if is_public_path(path):
        return await call_next(request)

    # Проверяем cookie
    session_token = request.cookies.get("session")
    username = validate_session_token(session_token)

    if username is None:
        # API-запросы → 401 JSON
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"error": "UNAUTHORIZED", "message": "Требуется авторизация"},
            )
        # Страницы → редирект на логин
        return RedirectResponse(url="/login", status_code=302)

    # Сохраняем username в state для использования в обработчиках
    request.state.username = username
    return await call_next(request)


# ───────────────────────────────────────────────────────────
# Авторизация
# ───────────────────────────────────────────────────────────
@app.get("/login", response_class=FileResponse)
async def login_page():
    """Отдаёт страницу входа."""
    return FileResponse(str(STATIC_DIR / "login.html"))


@app.post("/api/login")
async def login(request: Request):
    """Аутентификация: проверяет логин/пароль и устанавливает cookie."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "INVALID_JSON", "message": "Невалидный JSON"})

    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not verify_credentials(username, password):
        logger.warning("Неудачная попытка входа: user='%s', ip=%s", username, request.client.host)
        raise HTTPException(
            status_code=401,
            detail={"error": "INVALID_CREDENTIALS", "message": "Неверный логин или пароль"},
        )

    # Создаём сессию
    token = create_session_token(username)
    logger.info("Успешный вход: user='%s', ip=%s", username, request.client.host)

    response = JSONResponse(content={"success": True, "message": "Авторизация успешна"})
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,       # Недоступна из JS
        samesite="strict",   # Защита от CSRF
        max_age=86400,       # 24 часа
        path="/",
    )
    return response


@app.post("/api/logout")
async def logout():
    """Выход: удаляет cookie сессии."""
    response = JSONResponse(content={"success": True, "message": "Выход выполнен"})
    response.delete_cookie(key="session", path="/")
    return response


# ───────────────────────────────────────────────────────────
# Страница
# ───────────────────────────────────────────────────────────
@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    """Отдаёт главную HTML-страницу дашборда."""
    return FileResponse(str(STATIC_DIR / "index.html"))


# ───────────────────────────────────────────────────────────
# CRUD хостов
# ───────────────────────────────────────────────────────────
@app.get("/api/hosts")
async def list_hosts_endpoint():
    """Список хостов (без конфиденциальных данных)."""
    try:
        hosts = load_hosts()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail={"error": "CONFIG_ERROR", "message": str(exc)})

    safe_hosts = [
        {"id": h.id, "name": h.name, "description": h.description, "host": h.ssh.host, "port": h.ssh.port}
        for h in hosts
    ]
    return JSONResponse(content={"success": True, "hosts": safe_hosts})


@app.get("/api/hosts/{host_id}")
async def get_host_endpoint(host_id: str):
    """Полные данные хоста для формы редактирования."""
    entry = get_host_full_data(host_id)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "HOST_NOT_FOUND", "message": f"Хост '{host_id}' не найден"})

    ssh = entry.get("ssh", {})
    masked = {**entry, "ssh": {**ssh, "password_masked": bool(ssh.get("password"))}}
    return JSONResponse(content={"success": True, "host": masked})


@app.post("/api/hosts")
async def create_host_endpoint(request: Request):
    """Создание нового хоста."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "INVALID_JSON", "message": "Невалидный JSON"})

    ssh_host = payload.get("ssh_host", "").strip()
    if not ssh_host:
        raise HTTPException(status_code=422, detail={"error": "VALIDATION_ERROR", "message": "Поле 'ssh_host' обязательно"})
    if not payload.get("name", "").strip():
        payload["name"] = ssh_host

    try:
        new_entry = add_host(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "CONFLICT", "message": str(exc)})

    return JSONResponse(content={"success": True, "host": new_entry}, status_code=201)


@app.put("/api/hosts/{host_id}")
async def update_host_endpoint(host_id: str, request: Request):
    """Обновление хоста."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "INVALID_JSON", "message": "Невалидный JSON"})

    if not payload.get("ssh_password") and payload.get("ssh_password_keep"):
        existing = get_host_full_data(host_id)
        if existing:
            payload["ssh_password"] = existing.get("ssh", {}).get("password", "")

    try:
        updated = update_host(host_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": "HOST_NOT_FOUND", "message": str(exc)})

    return JSONResponse(content={"success": True, "host": updated})


@app.delete("/api/hosts/{host_id}")
async def delete_host_endpoint(host_id: str):
    """Удаление хоста."""
    try:
        delete_host(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": "HOST_NOT_FOUND", "message": str(exc)})
    return JSONResponse(content={"success": True, "message": f"Хост '{host_id}' удалён"})


# ───────────────────────────────────────────────────────────
# RAID статус
# ───────────────────────────────────────────────────────────
@app.get("/api/raid-status/{host_id}")
async def get_raid_status(host_id: str):
    """Обработанные данные RAID-массива для хоста (мультиконтроллер)."""
    app_config = get_app_config()
    host = get_host_by_id(host_id)
    if host is None:
        raise HTTPException(status_code=404, detail={"error": "HOST_NOT_FOUND", "message": f"Хост '{host_id}' не найден"})

    try:
        if app_config.debug_mode:
            logger.info("DEBUG_MODE: хост '%s' — Example.json", host.name)
            example_path = PROJECT_ROOT / "Example.json"
            if not example_path.exists():
                raise HTTPException(status_code=500, detail="Example.json не найден")
            raw_json = example_path.read_text(encoding="utf-8")
        else:
            command = f"{host.storcli_path} {host.storcli_controller} show all J"
            logger.info("Запрос к '%s' (%s): %s", host.name, host.ssh.host, command)
            raw_json = execute_remote_command(host.ssh, command)

        parsed_data = parse_storcli_output(raw_json)
        parsed_data["host"] = {"id": host.id, "name": host.name, "description": host.description, "address": host.ssh.host}
        return JSONResponse(content={"success": True, "data": parsed_data})

    except SSHConnectionError as exc:
        raise HTTPException(status_code=503, detail={"error": "SSH_CONNECTION_ERROR", "message": str(exc)})
    except SSHCommandError as exc:
        raise HTTPException(status_code=502, detail={"error": "COMMAND_ERROR", "message": str(exc)})
    except StorCLIParseError as exc:
        raise HTTPException(status_code=422, detail={"error": "PARSE_ERROR", "message": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "INTERNAL_ERROR", "message": str(exc)})


@app.get("/api/raid-status")
async def get_raid_status_default():
    """Без host_id — первый хост (обратная совместимость)."""
    try:
        hosts = load_hosts()
    except (FileNotFoundError, ValueError):
        hosts = []
    if not hosts:
        raise HTTPException(status_code=404, detail={"error": "NO_HOSTS", "message": "Нет настроенных хостов."})
    return await get_raid_status(hosts[0].id)


# ───────────────────────────────────────────────────────────
# Действия
# ───────────────────────────────────────────────────────────
@app.get("/api/actions")
async def list_actions():
    """Список всех доступных действий."""
    return JSONResponse(content={"success": True, "actions": get_all_actions()})


@app.post("/api/action/{host_id}")
async def execute_action(host_id: str, request: Request):
    """Выполняет storcli-команду на удалённом сервере."""
    app_config = get_app_config()

    host = get_host_by_id(host_id)
    if host is None:
        raise HTTPException(status_code=404, detail={"error": "HOST_NOT_FOUND", "message": f"Хост '{host_id}' не найден"})

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "INVALID_JSON", "message": "Невалидный JSON"})

    action = payload.get("action", "")
    cmd_info = get_command(action)
    if cmd_info is None:
        raise HTTPException(status_code=400, detail={"error": "UNKNOWN_ACTION", "message": f"Неизвестное действие: '{action}'"})

    if cmd_info["level"] not in ("safe", "operational", "dangerous"):
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Действие запрещено"})

    try:
        command = build_command(
            action=action,
            storcli_path=host.storcli_path,
            controller_index=payload.get("controller_index", 0),
            eid=str(payload.get("eid", "")),
            slot=str(payload.get("slot", "")),
            vd_index=payload.get("vd_index"),
            dg=payload.get("dg"),
            rate=str(payload.get("rate", "")),
            raid_level=str(payload.get("raid_level", "")),
            drives=str(payload.get("drives", "")),
            options=str(payload.get("options", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "BUILD_ERROR", "message": str(exc)})

    timestamp = datetime.now(tz=timezone.utc).isoformat()

    # Аудит (включая username)
    username = getattr(request.state, "username", "unknown")
    logger.info(
        "ACTION [%s] user=%s host=%s ctrl=C%s cmd='%s'",
        action, username, host_id,
        payload.get("controller_index", 0), command,
    )

    if app_config.debug_mode:
        return JSONResponse(content={
            "success": True,
            "result": {
                "action": action, "label": cmd_info["label"], "command": command,
                "output": f"[DEBUG MODE] Команда не выполнена.\nКоманда: {command}",
                "timestamp": timestamp, "debug": True,
            },
        })

    try:
        output = execute_remote_command(host.ssh, command)
        logger.info("ACTION SUCCESS [%s] user=%s host=%s", action, username, host_id)
        return JSONResponse(content={
            "success": True,
            "result": {
                "action": action, "label": cmd_info["label"], "command": command,
                "output": output, "timestamp": timestamp, "debug": False,
            },
        })
    except SSHConnectionError as exc:
        raise HTTPException(status_code=503, detail={"error": "SSH_CONNECTION_ERROR", "message": str(exc)})
    except SSHCommandError as exc:
        logger.warning("ACTION ERROR [%s] user=%s: %s", action, username, exc)
        raise HTTPException(status_code=502, detail={"error": "COMMAND_ERROR", "message": str(exc), "action": action, "label": cmd_info["label"]})
    except Exception as exc:
        logger.exception("ACTION UNEXPECTED [%s]: %s", action, exc)
        raise HTTPException(status_code=500, detail={"error": "INTERNAL_ERROR", "message": str(exc)})


# ───────────────────────────────────────────────────────────
# Запуск
# ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    config = get_app_config()
    logger.info("Запуск StorCLI RAID Monitor на %s:%d", config.host, config.port)
    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=True)
