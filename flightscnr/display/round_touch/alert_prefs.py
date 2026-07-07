"""Persisted aircraft alert preferences (FlightScnr alert portal)."""

import json
import logging
import os
import re

logger = logging.getLogger("flightscnr.display")

DATA_DIR = os.environ.get("FLIGHTSCNR_DATA_DIR", "/var/lib/flightscnr")
ALERT_PATH = os.path.join(DATA_DIR, "alert_prefs.json")

_WATCH_MAX = 16
_CALLSIGN_RE = re.compile(r"^[A-Z]{3}[A-Z0-9]+$")

_defaults = {
    "alert_military": False,
    "alert_emergency": False,
    "alert_hide_non_alerted": False,
    "alert_watch": "",
}


def _save(data: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = ALERT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, ALERT_PATH)
    except OSError as exc:
        logger.warning("Could not save alert prefs: %s", exc)


def _parse_watch(blob: str) -> list[str]:
    out: list[str] = []
    if not blob:
        return out
    for raw in blob.replace(";", ",").split(","):
        token = "".join(raw.upper().split())
        if not token or not _CALLSIGN_RE.match(token):
            continue
        if token not in out and len(out) < _WATCH_MAX:
            out.append(token)
    return out


def _load() -> dict:
    if not os.path.exists(ALERT_PATH):
        state = dict(_defaults)
        _save(state)
        return state
    try:
        with open(ALERT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        state = dict(_defaults)
        _save(state)
        return state
    state = {**_defaults, **data}
    return state


_state = _load()
_watch = _parse_watch(_state.get("alert_watch", ""))
try:
    _last_mtime: float | None = (
        os.path.getmtime(ALERT_PATH) if os.path.exists(ALERT_PATH) else None
    )
except OSError:
    _last_mtime = None


def reload():
    global _state, _watch, _last_mtime
    try:
        mtime = os.path.getmtime(ALERT_PATH) if os.path.exists(ALERT_PATH) else None
    except OSError:
        mtime = None
    if mtime == _last_mtime:
        return
    _last_mtime = mtime
    _state = _load()
    _watch = _parse_watch(_state.get("alert_watch", ""))


def military_enabled() -> bool:
    return bool(_state.get("alert_military", False))


def emergency_enabled() -> bool:
    return bool(_state.get("alert_emergency", False))


def hide_non_alerted() -> bool:
    return bool(_state.get("alert_hide_non_alerted", False))


def watch_callsigns() -> list[str]:
    return list(_watch)


def watch_blob() -> str:
    return _state.get("alert_watch", "") or ""


def alerts_active() -> bool:
    return military_enabled() or emergency_enabled() or bool(_watch)


def update(
    *,
    alert_military: bool | None = None,
    alert_emergency: bool | None = None,
    alert_hide_non_alerted: bool | None = None,
    alert_watch: str | None = None,
) -> None:
    global _watch, _last_mtime
    if alert_military is not None:
        _state["alert_military"] = bool(alert_military)
    if alert_emergency is not None:
        _state["alert_emergency"] = bool(alert_emergency)
    if alert_hide_non_alerted is not None:
        _state["alert_hide_non_alerted"] = bool(alert_hide_non_alerted)
    if alert_watch is not None:
        _watch = _parse_watch(alert_watch)
        _state["alert_watch"] = ",".join(_watch)
    _save(_state)
    try:
        _last_mtime = os.path.getmtime(ALERT_PATH)
    except OSError:
        _last_mtime = None
