"""Aircraft alert detection — military, emergency squawk, watch list."""

import logging
import time

from display.round_touch import alert_prefs, geo
from utilities.adsb_client import normalize_squawk

logger = logging.getLogger(__name__)

_SEEN_CAPACITY = 32
_seen_hashes: list[int] = []
_last_beep_ts = 0.0
_BEEP_COOLDOWN_S = 2.0


def _hash_callsign(callsign: str) -> int:
    h = 2166136261
    for ch in callsign:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _already_seen(h: int) -> bool:
    return h in _seen_hashes


def _mark_seen(h: int) -> None:
    global _seen_hashes
    _seen_hashes.append(h)
    if len(_seen_hashes) > _SEEN_CAPACITY:
        _seen_hashes = _seen_hashes[-_SEEN_CAPACITY:]


def _normalize_callsign(value) -> str:
    if not value:
        return ""
    return "".join(str(value).upper().split())


def callsign_match_keys(callsign: str) -> frozenset[str]:
    """Callsign aliases for matching FR24 entries to ADS-B (e.g. UA123 → UAL123)."""
    cs = _normalize_callsign(callsign)
    if not cs:
        return frozenset()
    keys = {cs}
    if len(cs) >= 3 and cs[:2].isalpha() and cs[2].isdigit():
        try:
            from utilities.airline_branding import IATA_TO_ICAO

            icao = IATA_TO_ICAO.get(cs[:2])
            if icao:
                keys.add(icao + cs[2:])
        except ImportError:
            pass
    return frozenset(keys)


ADSB_ALERT_FIELDS = ("squawk", "db_flags")


def merge_live_fields(target: dict, source: dict, fields: tuple[str, ...]) -> None:
    """Copy live/ADS-B fields from source onto target."""
    for field in fields:
        if field not in source:
            continue
        value = source[field]
        if field in ("squawk",) and not value:
            continue
        target[field] = value


def dedupe_flights(flights: list[dict], *, threshold_km: float = 0.45) -> list[dict]:
    """Collapse FR24 + ADS-B duplicates that share the same position."""

    def richness(flight: dict) -> int:
        score = 0
        if flight.get("origin") or flight.get("destination"):
            score += 10
        if flight.get("airline"):
            score += 3
        if flight.get("data_source") != "adsb_fi":
            score += 5
        if flight.get("squawk"):
            score += 1
        if flight.get("db_flags"):
            score += 1
        return score

    kept: list[dict] = []
    for flight in flights:
        lat = flight.get("plane_latitude")
        lon = flight.get("plane_longitude")
        if lat is None or lon is None:
            kept.append(flight)
            continue

        duplicate = None
        for existing in kept:
            elat = existing.get("plane_latitude")
            elon = existing.get("plane_longitude")
            if elat is None or elon is None:
                continue
            if geo.distance_km(lat, lon, elat, elon) <= threshold_km:
                duplicate = existing
                break

        if duplicate is None:
            kept.append(flight)
            continue

        live_fields = (
            "plane_latitude", "plane_longitude", "altitude",
            "heading", "ground_speed", "vertical_speed",
            "squawk", "db_flags", "icao_hex",
        )
        if richness(flight) > richness(duplicate):
            merge_live_fields(flight, duplicate, live_fields)
            kept.remove(duplicate)
            kept.append(flight)
        else:
            merge_live_fields(duplicate, flight, live_fields)

    return kept


def apply_adsb_alert_fields(flights: list[dict], adsb_entries: list[dict]) -> None:
    """Copy squawk / military flags from ADS-B onto merged flight records."""
    lookup: dict[str, dict] = {}
    for entry in adsb_entries:
        payload = {field: entry.get(field) for field in ADSB_ALERT_FIELDS}
        for key in callsign_match_keys(entry.get("callsign")):
            lookup[key] = payload

    for flight in flights:
        for key in callsign_match_keys(flight.get("callsign")):
            payload = lookup.get(key)
            if not payload:
                continue
            squawk = payload.get("squawk")
            if squawk:
                flight["squawk"] = squawk
            if payload.get("db_flags") is not None:
                flight["db_flags"] = payload.get("db_flags")
            break


def is_military(flight: dict) -> bool:
    try:
        raw = flight.get("db_flags", flight.get("dbFlags"))
        flags = int(raw or 0)
    except (TypeError, ValueError):
        flags = 0
    return bool(flags & 0x01)


def is_emergency_squawk(flight: dict) -> bool:
    squawk = normalize_squawk(flight.get("squawk"))
    return squawk in ("7700", "7600", "7500")


def on_watchlist(flight: dict) -> bool:
    cs = _normalize_callsign(flight.get("callsign"))
    return cs in alert_prefs.watch_callsigns()


def should_alert(flight: dict) -> bool:
    if alert_prefs.military_enabled() and is_military(flight):
        return True
    if alert_prefs.emergency_enabled() and is_emergency_squawk(flight):
        return True
    if on_watchlist(flight):
        return True
    return False


def is_highlighted(flight: dict) -> bool:
    return should_alert(flight)


def is_shown_on_radar(flight: dict) -> bool:
    """True if this aircraft should be drawn when hide-non-alerted is enabled."""
    alert_prefs.reload()
    if not alert_prefs.hide_non_alerted():
        return True
    return is_highlighted(flight)


def pulse_phase() -> bool:
    return int(time.time() * 4) % 2 == 0


def alert_color(flight: dict):
    from display.round_touch import theme

    if alert_prefs.emergency_enabled() and is_emergency_squawk(flight):
        return theme.ALERT_EMERGENCY
    if alert_prefs.military_enabled() and is_military(flight):
        return theme.ALERT_MILITARY
    if on_watchlist(flight):
        return theme.ALERT_WATCH
    return theme.AIRCRAFT


def is_in_range(flight: dict) -> bool:
    lat = flight.get("plane_latitude")
    lon = flight.get("plane_longitude")
    if lat is None or lon is None:
        return False
    return geo.local_offset_km(lat, lon)[2] <= geo.inner_ring_max_km()


def check_new_aircraft(flights: list[dict]) -> None:
    """Log alert when a new in-range alert target appears (no hardware buzzer on Pi)."""
    global _last_beep_ts
    alert_prefs.reload()
    if not alert_prefs.alerts_active():
        return
    fired = False
    for flight in flights:
        if not should_alert(flight):
            continue
        if not is_in_range(flight):
            continue
        cs = _normalize_callsign(flight.get("callsign"))
        if not cs:
            continue
        h = _hash_callsign(cs)
        if _already_seen(h):
            continue
        _mark_seen(h)
        fired = True
        logger.info(
            "ALERT %s mil=%s emrg=%s watch=%s squawk=%s",
            cs,
            is_military(flight),
            is_emergency_squawk(flight),
            on_watchlist(flight),
            flight.get("squawk"),
        )
    if fired and time.time() - _last_beep_ts >= _BEEP_COOLDOWN_S:
        _last_beep_ts = time.time()
