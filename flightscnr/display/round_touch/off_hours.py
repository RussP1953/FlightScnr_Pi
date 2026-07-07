"""Night / off-hours brightness schedule."""

from datetime import datetime

try:
    from config import NIGHT_BRIGHTNESS, NIGHT_END, NIGHT_START, BRIGHTNESS_NIGHT
except ImportError:
    NIGHT_BRIGHTNESS = False
    NIGHT_START = "22:00"
    NIGHT_END = "06:00"
    BRIGHTNESS_NIGHT = 50


def _parse_hhmm(text: str) -> int | None:
    try:
        h, m = text.strip().split(":", 1)
        hi, mi = int(h), int(m)
        if 0 <= hi <= 23 and 0 <= mi <= 59:
            return hi * 60 + mi
    except (ValueError, AttributeError):
        pass
    return None


def in_off_hours(now: datetime | None = None) -> bool:
    if not NIGHT_BRIGHTNESS:
        return False
    start = _parse_hhmm(NIGHT_START)
    end = _parse_hhmm(NIGHT_END)
    if start is None or end is None:
        return False
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end


def effective_brightness_percent(day_percent: int) -> int:
    if in_off_hours():
        return max(10, min(100, int(BRIGHTNESS_NIGHT)))
    return day_percent
