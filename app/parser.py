"""
parser.py — Парсер JSON-вывода утилиты StorCLI.

Поддерживает обработку нескольких контроллеров в одном JSON-ответе
(команда storcli /call show all J возвращает все контроллеры).

Извлекает из сырого JSON данные о:
  - Каждом контроллере (модель, S/N, статус, прошивка)
  - Виртуальных дисках (VD LIST)
  - Физических дисках (PD LIST)
  - Топологии RAID-массива (TOPOLOGY)
  - Состоянии батареи BBU
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class StorCLIParseError(Exception):
    """Ошибка парсинга JSON-вывода StorCLI."""


def parse_storcli_output(raw_json: str) -> dict[str, Any]:
    """
    Парсит сырой JSON-вывод StorCLI и возвращает структурированные данные.

    Обрабатывает ВСЕ контроллеры из массива Controllers[].
    Если использовалась команда /call, их может быть несколько.

    Args:
        raw_json: Строка с JSON-выводом команды storcli.

    Returns:
        Словарь с обработанными данными RAID-массивов всех контроллеров.

    Raises:
        StorCLIParseError: Если JSON невалидный или имеет неожиданную структуру.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.error("Невалидный JSON от StorCLI: %s", exc)
        raise StorCLIParseError(f"Невалидный JSON: {exc}") from exc

    # Проверяем базовую структуру ответа
    controllers_raw = data.get("Controllers")
    if not controllers_raw or not isinstance(controllers_raw, list):
        raise StorCLIParseError("Отсутствует массив 'Controllers' в ответе StorCLI")

    # Парсим каждый контроллер
    controllers = []
    for i, ctrl in enumerate(controllers_raw):
        try:
            parsed_ctrl = _parse_single_controller(ctrl, i)
            if parsed_ctrl is not None:
                controllers.append(parsed_ctrl)
        except StorCLIParseError as exc:
            logger.warning("Пропуск контроллера #%d: %s", i, exc)
            # Добавляем контроллер с ошибкой, чтобы показать на фронте
            controllers.append({
                "controller_index": i,
                "controller": {
                    "model": f"Controller #{i}",
                    "serial_number": "N/A",
                    "controller_time": "N/A",
                    "firmware_version": "N/A",
                    "firmware_package": "N/A",
                    "driver_name": "N/A",
                    "driver_version": "N/A",
                    "bios_version": "N/A",
                    "status": "Error",
                    "memory_size": "N/A",
                    "bbu_present": "N/A",
                    "cache_size_mb": 0,
                },
                "virtual_drives": [],
                "physical_drives": [],
                "topology": [],
                "bbu": [],
                "overall_status": "critical",
                "error": str(exc),
            })

    if not controllers:
        raise StorCLIParseError("Не удалось обработать ни один контроллер")

    # Определяем общий статус по всем контроллерам
    overall = _determine_global_status(controllers)

    result = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "controllers": controllers,
        "controller_count": len(controllers),
        "overall_status": overall,
    }

    logger.info(
        "Парсинг успешен: контроллеров=%d, общий статус=%s",
        len(controllers),
        overall,
    )

    return result


def _parse_single_controller(ctrl: dict, index: int) -> dict[str, Any] | None:
    """
    Парсит данные одного контроллера из массива Controllers[].

    Args:
        ctrl: Словарь с данными контроллера.
        index: Порядковый номер контроллера.

    Returns:
        Структурированный словарь данных контроллера.
    """
    command_status = ctrl.get("Command Status", {})
    response_data = ctrl.get("Response Data", {})

    if not response_data:
        raise StorCLIParseError(
            f"Controller #{index}: отсутствует 'Response Data'"
        )

    # Проверяем статус команды
    if command_status.get("Status") != "Success":
        raise StorCLIParseError(
            f"Controller #{index}: команда не выполнена — "
            f"{command_status.get('Description', 'Unknown error')}"
        )

    controller_info = _parse_controller_info(response_data)

    return {
        "controller_index": command_status.get("Controller", index),
        "controller": controller_info,
        "virtual_drives": _parse_virtual_drives(response_data),
        "physical_drives": _parse_physical_drives(response_data),
        "topology": _parse_topology(response_data),
        "bbu": _parse_bbu_info(response_data),
        "overall_status": _determine_overall_status(response_data),
    }


def _parse_controller_info(data: dict) -> dict[str, Any]:
    """Извлекает информацию о контроллере."""
    basics = data.get("Basics", {})
    version = data.get("Version", {})
    status = data.get("Status", {})
    hw_cfg = data.get("HwCfg", {})

    return {
        "model": basics.get("Model", "N/A"),
        "serial_number": basics.get("Serial Number", "N/A"),
        "controller_time": basics.get("Current Controller Date/Time", "N/A"),
        "firmware_version": version.get("Firmware Version", "N/A"),
        "firmware_package": version.get("Firmware Package Build", "N/A"),
        "driver_name": version.get("Driver Name", "N/A"),
        "driver_version": version.get("Driver Version", "N/A"),
        "bios_version": version.get("Bios Version", "N/A"),
        "status": status.get("Controller Status", "Unknown"),
        "memory_size": hw_cfg.get("On Board Memory Size", "N/A"),
        "bbu_present": hw_cfg.get("BBU", "N/A"),
        "cache_size_mb": hw_cfg.get("Current Size of FW Cache (MB)", 0),
    }


def _parse_virtual_drives(data: dict) -> list[dict[str, Any]]:
    """Извлекает список виртуальных дисков (VD LIST)."""
    vd_list = data.get("VD LIST", [])
    result = []

    for vd in vd_list:
        vd_info = {
            "dg_vd": vd.get("DG/VD", "N/A"),
            "type": vd.get("TYPE", "N/A"),
            "state": vd.get("State", "Unknown"),
            "access": vd.get("Access", "N/A"),
            "consistent": vd.get("Consist", "N/A"),
            "cache": vd.get("Cache", "N/A"),
            "size": vd.get("Size", "N/A"),
            "name": vd.get("Name", ""),
        }

        vd_info["health"] = _classify_state(vd_info["state"])
        result.append(vd_info)

    return result


def _parse_physical_drives(data: dict) -> list[dict[str, Any]]:
    """Извлекает список физических дисков (PD LIST)."""
    pd_list = data.get("PD LIST", [])
    result = []

    for pd in pd_list:
        pd_info = {
            "eid_slot": pd.get("EID:Slt", "N/A"),
            "did": pd.get("DID", "N/A"),
            "state": pd.get("State", "Unknown"),
            "drive_group": pd.get("DG", "N/A"),
            "size": pd.get("Size", "N/A"),
            "interface": pd.get("Intf", "N/A"),
            "media": pd.get("Med", "N/A"),
            "model": str(pd.get("Model", "N/A")).strip(),
            "sector_size": pd.get("SeSz", "N/A"),
        }

        pd_info["health"] = _classify_pd_state(pd_info["state"])
        result.append(pd_info)

    return result


def _parse_topology(data: dict) -> list[dict[str, Any]]:
    """Извлекает топологию RAID-массива (TOPOLOGY)."""
    topology = data.get("TOPOLOGY", [])
    result = []

    for item in topology:
        topo_info = {
            "dg": item.get("DG", "N/A"),
            "arr": item.get("Arr", "-"),
            "row": item.get("Row", "-"),
            "eid_slot": item.get("EID:Slot", "-"),
            "did": item.get("DID", "-"),
            "type": item.get("Type", "N/A"),
            "state": item.get("State", "Unknown"),
            "size": item.get("Size", "N/A"),
        }

        topo_info["health"] = _classify_state(topo_info["state"])
        result.append(topo_info)

    return result


def _parse_bbu_info(data: dict) -> list[dict[str, Any]]:
    """Извлекает информацию о батарее (BBU)."""
    bbu_list = data.get("BBU_Info", [])
    result = []

    for bbu in bbu_list:
        bbu_info = {
            "model": bbu.get("Model", "N/A"),
            "state": bbu.get("State", "Unknown"),
            "retention_time": bbu.get("RetentionTime", "N/A"),
            "temperature": bbu.get("Temp", "N/A"),
            "mfg_date": bbu.get("MfgDate", "N/A"),
            "next_learn": bbu.get("Next Learn", "N/A"),
        }

        bbu_info["health"] = _classify_state(bbu_info["state"])
        result.append(bbu_info)

    return result


def _classify_state(state: str) -> str:
    """
    Классифицирует состояние компонента RAID для визуальной индикации.

    Returns:
        "optimal" | "degraded" | "critical" | "unknown"
    """
    state_lower = state.lower().strip()

    optimal_states = {"optl", "optimal", "onln", "online"}
    degraded_states = {"dgrd", "degraded", "pdgd", "partially degraded", "needs attention"}
    critical_states = {"offln", "offline", "failed", "msng", "missing"}

    if state_lower in optimal_states:
        return "optimal"
    if state_lower in degraded_states:
        return "degraded"
    if state_lower in critical_states:
        return "critical"

    # Проверяем подстроки (например, "Dgd (Needs Attention)")
    for keyword in ("dgd", "degraded", "needs attention", "attention"):
        if keyword in state_lower:
            return "degraded"
    for keyword in ("fail", "offln", "offline", "missing", "error"):
        if keyword in state_lower:
            return "critical"

    return "unknown"


def _classify_pd_state(state: str) -> str:
    """
    Классифицирует состояние физического диска.

    Returns:
        "optimal" | "degraded" | "critical" | "unknown"
    """
    state_lower = state.lower().strip()

    optimal_states = {"onln", "online", "ghs", "dhs", "jbod", "ugood"}
    degraded_states = {"rbld", "rebuild", "copyback"}
    critical_states = {"offln", "offline", "failed", "ubad", "msng", "missing"}

    if state_lower in optimal_states:
        return "optimal"
    if state_lower in degraded_states:
        return "degraded"
    if state_lower in critical_states:
        return "critical"
    return "unknown"


def _determine_overall_status(data: dict) -> str:
    """
    Определяет общий статус контроллера на основе его данных и VD.

    Returns:
        "optimal" | "degraded" | "critical"
    """
    controller_status = data.get("Status", {}).get("Controller Status", "Unknown")
    vd_list = data.get("VD LIST", [])

    ctrl_health = _classify_state(controller_status)

    # Если контроллер не в порядке — сразу critical
    if ctrl_health == "critical":
        return "critical"

    # Проверяем состояние каждого VD
    has_degraded = ctrl_health == "degraded"
    for vd in vd_list:
        health = _classify_state(vd.get("State", "Unknown"))
        if health == "critical":
            return "critical"
        if health == "degraded":
            has_degraded = True

    # Проверяем BBU
    for bbu in data.get("BBU_Info", []):
        bbu_health = _classify_state(bbu.get("State", "Unknown"))
        if bbu_health == "critical":
            return "critical"
        if bbu_health == "degraded":
            has_degraded = True

    if has_degraded:
        return "degraded"

    if ctrl_health == "optimal":
        return "optimal"

    return "degraded"


def _determine_global_status(controllers: list[dict]) -> str:
    """
    Определяет глобальный статус по ВСЕМ контроллерам.

    Returns:
        "optimal" | "degraded" | "critical"
    """
    has_degraded = False

    for ctrl in controllers:
        status = ctrl.get("overall_status", "unknown")
        if status == "critical":
            return "critical"
        if status == "degraded":
            has_degraded = True

    return "degraded" if has_degraded else "optimal"
