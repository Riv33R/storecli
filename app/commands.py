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
    "vd_delete": {
        "label": "Удалить VD",
        "icon": "🗑️",
        "target": "vd",
        "level": "dangerous",
        "confirm_text": "УДАЛИТЬ виртуальный диск VD {vd}? Все данные на нем будут безвозвратно утеряны!",
        "template": "{path} /c{ctrl}/v{vd} del force",
    },

    # ── Controller: безопасные ──
    "ctrl_show_all": {
        "label": "Полная информация",
        "icon": "ℹ️",
        "target": "controller",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl} show all J",
    },
    "ctrl_event_log": {
        "label": "Event Log",
        "icon": "📋",
        "target": "controller",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl} show events type=latest=20 J",
    },
    "ctrl_foreign_scan": {
        "label": "Сканировать Foreign",
        "icon": "🔍",
        "target": "controller",
        "level": "safe",
        "confirm_text": None,
        "template": "{path} /c{ctrl}/fall show J",
    },

    # ── Controller: операционные ──
    "ctrl_start_cc": {
        "label": "Запуск CC (все VD)",
        "icon": "✅",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Запустить Consistency Check на всех VD контроллера C{ctrl}?",
        "template": "{path} /c{ctrl} start cc",
    },
    "ctrl_stop_cc": {
        "label": "Остановка CC (все VD)",
        "icon": "⏹️",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Остановить Consistency Check на всех VD контроллера C{ctrl}?",
        "template": "{path} /c{ctrl} stop cc",
    },
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
    "ctrl_set_rebuild_rate": {
        "label": "Rebuild Rate",
        "icon": "⚙️",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Установить Rebuild Rate = {rate}% на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set rebuildrate={rate}",
    },
    "ctrl_set_cc_rate": {
        "label": "CC Rate",
        "icon": "⚙️",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Установить CC Rate = {rate}% на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set ccrate={rate}",
    },
    "ctrl_set_patrol_rate": {
        "label": "Patrol Read Rate",
        "icon": "⚙️",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Установить Patrol Read Rate = {rate}% на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set patrolreadrate={rate}",
    },
    "ctrl_set_bgi_rate": {
        "label": "BGI Rate",
        "icon": "⚙️",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Установить BGI Rate = {rate}% на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set bgirate={rate}",
    },
    "ctrl_set_alarm_on": {
        "label": "Включить Alarm",
        "icon": "🔊",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Включить звуковой сигнал на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set alarm=on",
    },
    "ctrl_silence_alarm": {
        "label": "Выключить Alarm",
        "icon": "🔇",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Выключить звуковой сигнал на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set alarm=silence",
    },
    "ctrl_set_alarm_off": {
        "label": "Отключить Alarm полностью",
        "icon": "🔕",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Полностью отключить поддержку Alarm на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set alarm=off",
    },
    "ctrl_set_cache_wb": {
        "label": "Кэш WB",
        "icon": "💾",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Установить Cachecade Write Back на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set cachecade writeback",
    },
    "ctrl_set_cache_wt": {
        "label": "Кэш WT",
        "icon": "💾",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Установить Cachecade Write Through на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} set cachecade writethrough",
    },
    "ctrl_add_vd": {
        "label": "Создать RAID",
        "icon": "➕",
        "target": "controller",
        "level": "operational",
        "confirm_text": "Создать RAID из выбранных дисков на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl} add vd type={raid_level} drives={drives} {options}",
    },

    # ── PD: опасные ──
    "pd_make_good": {
        "label": "Make Good",
        "icon": "🛠️",
        "target": "pd",
        "level": "dangerous",
        "confirm_text": "Принудительно перевести диск {eid}:{slot} в состояние Unconfigured Good?",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} set good force",
    },
    "pd_make_offline": {
        "label": "Force Offline",
        "icon": "🔌",
        "target": "pd",
        "level": "dangerous",
        "confirm_text": "Принудительно перевести диск {eid}:{slot} в Offline? Это может разрушить массив!",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} set offline",
    },
    "pd_make_online": {
        "label": "Force Online",
        "icon": "🔌",
        "target": "pd",
        "level": "dangerous",
        "confirm_text": "Принудительно перевести диск {eid}:{slot} в Online? Это может разрушить массив если данные не синхронизированы!",
        "template": "{path} /c{ctrl}/e{eid}/s{slot} set online",
    },

    # ── Controller: опасные ──
    "ctrl_foreign_import": {
        "label": "Импорт Foreign",
        "icon": "📥",
        "target": "controller",
        "level": "dangerous",
        "confirm_text": "Импортировать чужую (Foreign) конфигурацию на контроллере C{ctrl}?",
        "template": "{path} /c{ctrl}/fall import",
    },
    "ctrl_foreign_clear": {
        "label": "Очистить Foreign",
        "icon": "🗑️",
        "target": "controller",
        "level": "dangerous",
        "confirm_text": "УДАЛИТЬ чужую (Foreign) конфигурацию на контроллере C{ctrl}? Данные на этих дисках могут быть потеряны!",
        "template": "{path} /c{ctrl}/fall delete",
    }
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
    rate: str = "",
    raid_level: str = "",
    drives: str = "",
    options: str = "",
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
        rate: Rate значение.
        raid_level: Уровень RAID (для add vd).
        drives: Диски (для add vd).
        options: Дополнительные опции (для add vd).

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
        # Убираем лишние пробелы в options, если есть
        result = template.format(
            path=storcli_path,
            ctrl=controller_index,
            eid=eid or "",
            slot=slot or "",
            vd=vd_index if vd_index is not None else "",
            dg=dg if dg is not None else "",
            rate=rate or "",
            raid_level=raid_level or "",
            drives=drives or "",
            options=(options or "").strip(),
        ).strip()
    except KeyError as exc:
        raise ValueError(f"Не хватает параметра для команды '{action}': {exc}") from exc

    logger.info("Собрана команда [%s]: %s", action, result)
    return result
