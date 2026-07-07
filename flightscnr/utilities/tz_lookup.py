"""Auto timezone lookup from radar center (timeapi.io, no API key)."""

import logging
import subprocess
import time

import requests

logger = logging.getLogger(__name__)

_CACHE: dict = {"ts": 0.0, "zone": ""}
_CACHE_TTL_S = 24 * 3600


def lookup_timezone_name(lat: float, lon: float) -> str | None:
    global _CACHE
    now = time.time()
    if _CACHE["zone"] and now - _CACHE["ts"] < _CACHE_TTL_S:
        return _CACHE["zone"]
    try:
        resp = requests.get(
            "https://timeapi.io/api/TimeZone/coordinate",
            params={"latitude": lat, "longitude": lon},
            timeout=(5, 15),
        )
        resp.raise_for_status()
        data = resp.json()
        zone = (data.get("timeZone") or data.get("TimeZone") or "").strip()
        if zone:
            _CACHE["zone"] = zone
            _CACHE["ts"] = now
            return zone
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("Timezone lookup failed: %s", exc)
    return _CACHE["zone"] or None


def apply_system_timezone(zone_name: str) -> bool:
    if not zone_name:
        return False
    try:
        subprocess.run(
            ["timedatectl", "set-timezone", zone_name],
            check=True,
            capture_output=True,
            timeout=10,
        )
        logger.info("System timezone set to %s", zone_name)
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("Could not set timezone to %s: %s", zone_name, exc)
        return False


def maybe_apply_auto_timezone(lat: float, lon: float) -> bool:
    zone = lookup_timezone_name(lat, lon)
    if not zone:
        return False
    return apply_system_timezone(zone)
