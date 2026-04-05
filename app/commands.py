"""
commands.py — Реестр команд StorCLI для управления RAID.

Каждая команда имеет:
  - action: уникальный ID действия
  - label: отображаемое имя
  - icon: эмодзи-иконка
  - target: тип объекта (pd, vd, controller)
  - level: уровень безопасности (safe, operational)
  - confirm_text: текст подтверждения (для operational)
  - template: шаблон storcli-команды
    Плейсхолдеры: {path}, {ctrl}, {eid}, {slot}, {vd}, {dg}
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────
# Реестр команд
# ───────────────────────────────────────────────────────────

COMMAND_REGISTRY: dict[str, dict[str, Any]] = {
    # ── PD: безопасные ──
    "pd_locate_start": {
        "label": "Включить LED",
        "icon": "📍",
        "target": "pd",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl}/e{eid}/s{slot} start locate",
    },
    "pd_locate_stop": {
        "label": "Выключить LED",
        "icon": "📍",
        "target": "pd",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl}/e{eid}/s{slot} stop locate",
    },
    "pd_smart": {
        "label": "SMART Info",
        "icon": "📊",
        "target": "pd",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl}/e{eid}/s{slot} show all J",
    },

    # ── PD: операционные ──
    "pd_start_rebuild": {
        "label": "Запустить Rebuild",
        "icon": "🔄",
        "target": "pd",
        "level": "operational",
        "confirm_text": "Запустить перестроение (Rebuild) диска {eid}:{slot}?",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} start rebuild",
    },
    "pd_add_hotspare_global": {
        "label": "Global Hot Spare",
        "icon": "♨️",
        "target": "pd",
        "level": "operational",
        "confirm_text": "Назначить диск {eid}:{slot} глобальным Hot Spare?",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} add hotsparedrive",
    },
    "pd_add_hotspare_dedicated": {
        "label": "Dedicated Hot Spare",
        "icon": "♨️",
        "target": "pd",
        "level": "operational",
        "confirm_text": "Назначить диск {eid}:{slot} выделенным Hot Spare для DG {dg}?",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} add hotsparedrive dgs={dg}",
    },
    "pd_remove_hotspare": {
        "label": "Убрать Hot Spare",
        "icon": "❌",
        "target": "pd",
        "level": "operational",
        "confirm_text": "Убрать Hot Spare статус с диска {eid}:{slot}?",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} delete hotsparedrive",
    },

    # ── VD: операционные ──
    "vd_start_cc": {
        "label": "Запустить CC",
        "icon": "✅",
        "target": "vd",
        "level": "operational",
        "confirm_text": "Запустить Consistency Check на VD {vd}?",
        "template": "{path} /c{ctrl}/v{vd} start cc",
    },
    "vd_stop_cc": {
        "label": "Остановить CC",
        "icon": "⏹️",
        "target": "vd",
        "level": "operational",
        "confirm_text": "Остановить Consistency Check на VD {vd}?",
        "template": "{path} /c{ctrl}/v{vd} stop cc",
    },

    # ── Controller: безопасные ──
    "ctrl_event_log": {
        "label": "Event Log",
        "icon": "📋",
        "target": "controller",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl} show events type=latest=20 J",
    },

    # ── Controller: операционные ──
    "ctrl_start_patrol": {
        "label": "Старт Patrol Read",
        "icon": "🔍",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Запустить Patrol Read на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} start patrolread",
    },
    "ctrl_stop_patrol": {
        "label": "Стоп Patrol Read",
        "icon": "⏹️",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Остановить Patrol Read на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} stop patrolread",
    },
    "ctrl_silence_alarm": {
        "label": "Выключить Alarm",
        "icon": "🔇",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Выключить звуковой сигнал на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set alarm=silence",
    },
}


def get_command(action: str) -> dict[str, Any] | None:
    """Возвращает описание команды по action ID."""
    return COMMAND_REGISTRY.get(action)


def get_actions_for_target(target: str) -> list[dict[str, Any]]:
    """Возвращает все действия для указанного типа объекта."""
    result = []
    for action_id, cmd in COMMAND_REGISTRY.items():
        if cmd["target"] == target:
            result.append({"action": action_id, **cmd})
    return result


def get_all_actions() -> dict[str, list[dict[str, Any]]]:
    """Возвращает все действия, сгруппированные по target."""
    grouped: dict[str, list] = {"pd": [], "vd": [], "controller": []}
    for action_id, cmd in COMMAND_REGISTRY.items():
        grouped.setdefault(cmd["target"], []).append({"action": action_id, **cmd})
    return grouped


def build_command(
    action: str,
    storcli_path: str,
    controller_index: int,
    eid: str | None = None,
    slot: str | None = None,
    vd_index: int | None = None,
    dg: int | None = None,
) -> str:
    """
    Собирает финальную storcli-команду из шаблона.

    Args:
        action: ID действия из COMMAND_REGISTRY.
        storcli_path: Путь к storcli на удалённом хосте.
        controller_index: Индекс контроллера.
        eid: Enclosure ID (для PD-действий).
        slot: Slot номер (для PD-действий).
        vd_index: Индекс VD (для VD-действий).
        dg: Drive Group (для dedicated hot spare).

    Returns:
        Готовая к выполнению команда.

    Raises:
        ValueError: Если action не найден или не хватает параметров.
    """
    cmd = get_command(action)
    if cmd is None:
        raise ValueError(f"Неизвестное действие: '{action}'")

    template = cmd["template"]

    try:
        result = template.format(
            path=storcli_path,
            ctrl=controller_index,
            eid=eid or "",
            slot=slot or "",
            vd=vd_index if vd_index is not None else "",
            dg=dg if dg is not None else "",
        )
    except KeyError as exc:
        raise ValueError(f"Не хватает параметра для команды '{action}': {exc}") from exc

    logger.info("Собрана команда [%s]: %s", action, result)
    return result
