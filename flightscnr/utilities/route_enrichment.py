"""On-demand route enrichment for the flight detail screen.

Also used indirectly via overhead.py for pinned pre-departure tracked flights.
One AirLabs lookup per uncached callsign when flight detail is opened and
origin/destination are missing.
"""

from __future__ import annotations

from utilities.airlabs import get_flight_schedule


def lookup_callsign(flight: dict | None) -> str:
    flight = flight or {}
    return (flight.get("callsign") or flight.get("flight_number") or "").strip().upper()


def _missing_route(value) -> bool:
    text = (value or "").strip()
    return not text or text == "—"


def needs_route_enrichment(flight: dict | None) -> bool:
    """True when the open flight detail row lacks a usable route."""
    if not flight:
        return False
    return _missing_route(flight.get("origin")) or _missing_route(flight.get("destination"))


def fetch_route_enrichment(flight: dict) -> dict | None:
    """Call AirLabs for schedule data. Returns fields to merge, or None."""
    callsign = lookup_callsign(flight)
    if not callsign:
        return None
    sched = get_flight_schedule(callsign)
    if not sched:
        return None
    return {
        "origin": sched.get("origin") or "",
        "destination": sched.get("destination") or "",
        "dep_time": sched.get("dep_time") or "",
        "arr_time": sched.get("arr_time") or "",
        "schedule_status": sched.get("status") or "",
    }


def merge_route_enrichment(flight: dict, cache: dict[str, dict]) -> dict:
    """Overlay cached enrichment onto a flight dict for display."""
    callsign = lookup_callsign(flight)
    enr = cache.get(callsign) if callsign else None
    if not enr:
        return flight
    merged = dict(flight)
    for key in ("origin", "destination", "dep_time", "arr_time", "schedule_status"):
        value = enr.get(key)
        if not value:
            continue
        if key in ("origin", "destination"):
            if _missing_route(merged.get(key)):
                merged[key] = value
        elif not merged.get(key):
            merged[key] = value
    return merged
