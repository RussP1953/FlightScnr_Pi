"""Radar range scale bands (FlightScnr radar_scale.h)."""

STATUTE_MILE_KM = 1.609344
LABEL_TO_COVERAGE = 4.0 / 3.0

def _band(miles: float) -> dict:
    label_km = miles * STATUTE_MILE_KM
    return {"label_km": label_km, "coverage_km": label_km * LABEL_TO_COVERAGE}


SCALE_BANDS = [_band(m) for m in (2, 3, 5, 8, 10, 20, 30)]

_active_index = 1


def active_band():
    return SCALE_BANDS[_active_index]


def active_index():
    return _active_index


def cycle_next():
    """Advance to the next range band, wrapping to the smallest."""
    global _active_index
    _active_index = (_active_index + 1) % len(SCALE_BANDS)


def select(index: int):
    global _active_index
    _active_index = max(0, min(index, len(SCALE_BANDS) - 1))


def search_radius_nm(index: int | None = None) -> float:
    """Nautical-mile fetch radius for rim targets (coverage scaled to visible edge)."""
    if index is None:
        idx = active_index()
    else:
        idx = max(0, min(int(index), len(SCALE_BANDS) - 1))
    band = SCALE_BANDS[idx]
    try:
        from display.round_touch import theme

        screen_r = theme.VISIBLE_RADIUS - theme.BEYOND_RING_MARGIN
        fetch_km = band["coverage_km"] * (screen_r / theme.GRID_OUTER_RADIUS)
    except ImportError:
        fetch_km = band["coverage_km"]
    return fetch_km / 1.852


NM_PER_KM = 1.0 / 1.852


def format_scale_tag(label_km: float, units: str = "km") -> str:
    units = (units or "km").lower()
    if units == "mi":
        miles = label_km / STATUTE_MILE_KM
        if abs(miles - round(miles)) < 0.05:
            return f"{int(round(miles))}mi"
        return f"{miles:.1f}mi"
    if units == "nm":
        nm = label_km * NM_PER_KM
        if abs(nm - round(nm)) < 0.05:
            return f"{int(round(nm))}nm"
        return f"{nm:.1f}nm"
    if label_km >= 10:
        return f"{int(round(label_km))}km"
    return f"{label_km:.1f}km"


def format_active_tag(units: str = "km") -> str:
    return format_scale_tag(active_band()["label_km"], units)


def format_band_tag(index: int, units: str = "km") -> str:
    idx = max(0, min(int(index), len(SCALE_BANDS) - 1))
    return format_scale_tag(SCALE_BANDS[idx]["label_km"], units)


def index_for_radius_nm(radius_nm: float) -> int:
    """Scale band index that fits the configured search radius."""
    radius_km = radius_nm * 1.852
    best = len(SCALE_BANDS) - 1
    for i, band in enumerate(SCALE_BANDS):
        if band["coverage_km"] >= radius_km:
            best = i
            break
    return best
