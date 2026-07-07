"""Night / off-hours brightness schedule."""

from __future__ import annotations

from datetime import datetime
import json
import os

try:
    from config import NIGHT_BRIGHTNESS, NIGHT_END, NIGHT_START, BRIGHTNESS_NIGHT
except ImportError:
    NIGHT_BRIGHTNESS = False
    NIGHT_START = "22:00"
    NIGHT_END = "06:00"
    BRIGHTNESS_NIGHT = 50

DATA_DIR = os.environ.get("FLIGHTSCNR_DATA_DIR", "/var/lib/flightscnr")
PREFS_PATH = os.path.join(DATA_DIR, "off_hours_prefs.json")


def _parse_hhmm(text: str) -> int | None:
    try:
        h, m = text.strip().split(":", 1)
        hi, mi = int(h), int(m)
        if 0 <= hi <= 23 and 0 <= mi <= 59:
            return hi * 60 + mi
    except (ValueError, AttributeError):
        pass
    return None


def _env_defaults() -> dict:
    mode = "dim"
    if int(BRIGHTNESS_NIGHT) <= 0:
        mode = "off"
    return {
        "enabled": bool(NIGHT_BRIGHTNESS),
        "start": str(NIGHT_START),
        "end": str(NIGHT_END),
        "mode": mode,
        "dim_percent": max(10, min(100, int(BRIGHTNESS_NIGHT or 50))),
    }


def _save(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PREFS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, PREFS_PATH)


def _load() -> dict:
    defaults = _env_defaults()
    if not os.path.exists(PREFS_PATH):
        _save(defaults)
        return defaults
    try:
        with open(PREFS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, TypeError):
        _save(defaults)
        return defaults
    out = {**defaults, **data}
    out["enabled"] = bool(out.get("enabled", False))
    out["start"] = str(out.get("start", defaults["start"]))
    out["end"] = str(out.get("end", defaults["end"]))
    mode = str(out.get("mode", "dim")).lower()
    if mode not in ("dim", "off", "clock"):
        mode = "dim"
    if bool(out.get("force_clock", False)):
        mode = "clock"
    out["mode"] = mode
    try:
        out["dim_percent"] = max(10, min(100, int(out.get("dim_percent", defaults["dim_percent"]))))
    except (TypeError, ValueError):
        out["dim_percent"] = defaults["dim_percent"]
    return out


_state = _load()


def prefs() -> dict:
    global _state
    _state = _load()
    return dict(_state)


def update_prefs(
    *,
    enabled: bool | None = None,
    start: str | None = None,
    end: str | None = None,
    mode: str | None = None,
    dim_percent: int | None = None,
) -> dict:
    global _state
    if enabled is not None:
        _state["enabled"] = bool(enabled)
    if start is not None and _parse_hhmm(str(start)) is not None:
        _state["start"] = str(start)
    if end is not None and _parse_hhmm(str(end)) is not None:
        _state["end"] = str(end)
    if mode is not None:
        new_mode = str(mode).lower()
        if new_mode not in ("dim", "off", "clock"):
            new_mode = "dim"
        _state["mode"] = new_mode
    if dim_percent is not None:
        try:
            _state["dim_percent"] = max(10, min(100, int(dim_percent)))
        except (TypeError, ValueError):
            pass
    _save(_state)
    return dict(_state)


def force_clock_enabled() -> bool:
    return prefs().get("mode") == "clock"


def in_off_hours(now: datetime | None = None) -> bool:
    cfg = prefs()
    if not cfg.get("enabled"):
        return False
    start = _parse_hhmm(cfg.get("start", "22:00"))
    end = _parse_hhmm(cfg.get("end", "06:00"))
    if start is None or end is None:
        return False
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end


def effective_brightness_percent(day_percent: int) -> int:
    if in_off_hours():
        cfg = prefs()
        if cfg.get("mode") == "off":
            return 0
        if cfg.get("mode") == "clock":
            return max(10, min(100, int(day_percent)))
        return max(10, min(100, int(cfg.get("dim_percent", 20))))
    return day_percent
