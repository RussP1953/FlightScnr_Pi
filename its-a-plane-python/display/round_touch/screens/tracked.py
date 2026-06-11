"""Tracked flight screen — route, progress bar, and live stats."""

from __future__ import annotations

import socket

import pygame

try:
    from config import CLOCK_FORMAT, DISTANCE_UNITS
except ImportError:
    CLOCK_FORMAT = "24hr"
    DISTANCE_UNITS = "metric"

from display.round_touch import aircraft, draw, logos, nav, settings, theme
from utilities.airline_branding import display_flight_id_for_flight
from utilities.overhead import load_tracked_callsign

FOOTER_BUTTONS = ("radar",)


def tap_footer_action(x: int, y: int) -> str | None:
    idx = nav.tap_footer_button(x, y, len(FOOTER_BUTTONS))
    if idx is None:
        return None
    return FOOTER_BUTTONS[idx]

# Nearest-city cache (matches scenes/trackedstats.py)
_city_cache = {"lat": None, "lon": None, "result": None}
_CITY_CACHE_THRESHOLD = 0.01

# Horizontal marquee for stats lines that exceed the round viewport width.
_marquee_states: dict[str, dict] = {}
_marquee_animating = False
_marquee_active_keys: set[str] = set()


def reset_marquee():
    """Clear marquee scroll positions (e.g. when leaving the tracked screen)."""
    global _marquee_animating
    _marquee_states.clear()
    _marquee_active_keys.clear()
    _marquee_animating = False


def tick_marquee() -> bool:
    """Advance marquee positions; return True while any line is scrolling."""
    global _marquee_animating
    if not _marquee_states:
        _marquee_animating = False
        return False
    step = max(1, theme.s(1))
    active = False
    for state in _marquee_states.values():
        state["x"] -= step
        if state["x"] + state["width"] < state["clip_left"]:
            state["x"] = float(state["clip_left"] + state["clip_width"])
        active = True
    _marquee_animating = active
    return active


def marquee_animating() -> bool:
    return _marquee_animating


def _marquee_key(y: int, text: str) -> str:
    return f"{y}:{text}"


def _draw_marquee_line(
    surface,
    y: int,
    text: str,
    font,
    color,
    *,
    always_scroll: bool = False,
) -> None:
    """Draw a stats line; scroll horizontally when wide or always_scroll is set."""
    h = font.get_height()
    max_w = draw.circle_half_width_at_row(int(y), h) * 2
    text_w = font.size(text)[0]
    clip_left = theme.CENTER_X - max_w // 2
    clip_rect = pygame.Rect(clip_left, int(y), max_w, h + 2)

    if text_w <= max_w and not always_scroll:
        _marquee_states.pop(_marquee_key(int(y), text), None)
        rendered = font.render(text, True, color)
        surface.blit(rendered, rendered.get_rect(midtop=(theme.CENTER_X, int(y))))
        return

    key = _marquee_key(int(y), text)
    _marquee_active_keys.add(key)
    state = _marquee_states.get(key)
    if state is None or state["text"] != text:
        state = {
            "text": text,
            "width": text_w,
            "clip_left": clip_left,
            "clip_width": max_w,
            "x": float(clip_left + max_w),
        }
        _marquee_states[key] = state

    rendered = font.render(text, True, color)
    old_clip = surface.get_clip()
    surface.set_clip(clip_rect)
    surface.blit(rendered, (int(state["x"]), int(y)))
    surface.set_clip(old_clip)


def tracking_active() -> bool:
    return bool(load_tracked_callsign())


def _delay_color(real, scheduled, *, is_arrival: bool = False):
    if real is None or scheduled in (None, 0):
        return theme.MUTED
    delay = (real - scheduled) / 60
    if is_arrival:
        if delay <= 0:
            return theme.SWEEP
        if delay <= 30:
            return theme.TAG_TYPE
        if delay <= 60:
            return theme.AIRCRAFT
        if delay <= 240:
            return theme.TAG_ALT_DESCEND
        return theme.ROUTE
    if delay <= 20:
        return theme.SWEEP
    if delay <= 40:
        return theme.TAG_TYPE
    if delay <= 60:
        return theme.AIRCRAFT
    if delay <= 240:
        return theme.TAG_ALT_DESCEND
    return theme.ROUTE


def _calc_progress(data) -> float:
    dist_remaining = data.get("dist_remaining")
    total_distance = data.get("total_distance")
    if dist_remaining is None:
        return 0.0
    if not total_distance or total_distance <= 0:
        return 0.0
    dist_flown = total_distance - dist_remaining
    return max(0.0, min(1.0, dist_flown / total_distance))


def _format_dep_time(dep_time_str: str) -> str:
    if not dep_time_str:
        return ""
    try:
        parts = dep_time_str.split(" ")
        if len(parts) < 2:
            return dep_time_str
        hm = parts[1].split(":")
        hour = int(hm[0])
        minute = int(hm[1]) if len(hm) > 1 else 0
        if CLOCK_FORMAT == "12hr":
            ampm = "a" if hour < 12 else "p"
            display_hour = hour % 12 or 12
            if minute:
                return f"{display_hour}:{minute:02d}{ampm}"
            return f"{display_hour}{ampm}"
        return f"{hour}:{minute:02d}"
    except (ValueError, IndexError):
        return dep_time_str


def _format_dist_remaining(dist) -> str | None:
    """Format distance remaining using display units from Settings → Display."""
    if dist is None:
        return None
    use_miles = settings.distance_in_miles()
    stored_km = DISTANCE_UNITS == "metric"
    value = float(dist)
    if stored_km and use_miles:
        value /= 1.609344
    elif not stored_km and not use_miles:
        value *= 1.609344
    unit = "mi" if use_miles else "km"
    return f"{int(value)}{unit}"


def _format_speed(ground_speed):
    """Format ground speed using display units from Settings → Display."""
    if ground_speed is None or ground_speed <= 0:
        return None
    kts = float(ground_speed)
    if settings.distance_in_miles():
        return f"{int(kts * 1.15078)} mph"
    return f"{int(kts * 1.852)} km/h"


def _nearest_city_label(data) -> str:
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return ""
    if (
        _city_cache["lat"] is None
        or abs(lat - _city_cache["lat"]) > _CITY_CACHE_THRESHOLD
        or abs(lon - _city_cache["lon"]) > _CITY_CACHE_THRESHOLD
    ):
        _city_cache["lat"] = lat
        _city_cache["lon"] = lon
        try:
            from utilities.cities import get_nearest_city

            _city_cache["result"] = get_nearest_city(lat, lon)
        except Exception:
            _city_cache["result"] = None
    nearest = _city_cache["result"]
    if nearest:
        return f"nr {nearest['name']}"
    return ""


def _status_label(data) -> str:
    if data.get("is_scheduled"):
        return "SCHEDULED"
    if not data.get("is_live", True):
        return "ESTIMATED"
    return "LIVE"


def _format_vertical_speed(vs) -> str | None:
    if vs is None:
        return None
    try:
        rate = int(vs)
    except (TypeError, ValueError):
        return None
    if abs(rate) <= 64:
        return None
    return f"{rate:+d} fpm"


def _progress_parts(data) -> list[str]:
    parts: list[str] = []
    if data.get("time_remaining"):
        parts.append(str(data["time_remaining"]))
    dist_str = _format_dist_remaining(data.get("dist_remaining"))
    if dist_str:
        parts.append(dist_str)
    landmark = _nearest_city_label(data)
    if landmark:
        parts.append(landmark)
    return parts


def _telemetry_parts(data) -> list[str]:
    parts: list[str] = []
    aircraft_type = data.get("aircraft_type", "")
    if aircraft_type and aircraft_type not in ("", "N/A"):
        parts.append(aircraft_type)

    alt_str = aircraft.format_altitude(data.get("altitude"))
    if alt_str != "—":
        vs = data.get("vertical_speed", 0) or 0
        if vs > 64:
            alt_str += " ↑"
        elif vs < -64:
            alt_str += " ↓"
        parts.append(alt_str)

    vs_str = _format_vertical_speed(data.get("vertical_speed"))
    if vs_str:
        parts.append(vs_str)

    speed_str = _format_speed(data.get("ground_speed"))
    if speed_str:
        parts.append(speed_str)

    heading = data.get("heading")
    if heading is not None and int(heading) > 0:
        parts.append(f"HDG {int(heading)}°")
    return parts


def _scheduled_rows(data) -> list[tuple[str, tuple[int, int, int]]]:
    dep = _format_dep_time(data.get("dep_time", ""))
    origin = data.get("origin", "")
    dest = data.get("destination", "")
    if dep:
        return [(f"Departs {dep}  {origin} → {dest}", theme.ROUTE)]
    return [(f"Scheduled  {origin} → {dest}", theme.ROUTE)]


def _build_stats_rows_compact(data) -> list[tuple[str, tuple[int, int, int]]]:
    """One scrolling ticker row — status, progress, and telemetry (matches LED layout)."""
    if data.get("is_scheduled"):
        return _scheduled_rows(data)

    rows: list[tuple[str, tuple[int, int, int]]] = []
    status = _status_label(data)
    status_color = theme.SWEEP if status == "LIVE" else theme.TAG_TYPE
    parts = [status, *_progress_parts(data), *_telemetry_parts(data)]
    if parts:
        rows.append(("  ·  ".join(parts), status_color))
    return rows


def _build_stats_rows_scroll(data) -> list[tuple[str, tuple[int, int, int]]]:
    """Two rows: status, then one scrolling ticker for progress + telemetry."""
    if data.get("is_scheduled"):
        return _scheduled_rows(data)

    rows: list[tuple[str, tuple[int, int, int]]] = []
    status = _status_label(data)
    status_color = theme.SWEEP if status == "LIVE" else theme.TAG_TYPE
    rows.append((status, status_color))

    parts = [*_progress_parts(data), *_telemetry_parts(data)]
    if parts:
        rows.append(("  ·  ".join(parts), theme.LABEL))
    return rows


def _build_stats_rows(data) -> list[tuple[str, tuple[int, int, int]]]:
    if settings.tracked_stats_mode() == settings.TRACKED_STATS_SCROLL:
        return _build_stats_rows_scroll(data)
    return _build_stats_rows_compact(data)


def _draw_logo(surface, flight: dict, y: int) -> int:
    logo_h = theme.s(36)
    logo = logos.load_logo_surface(logos.icao_for_flight(flight), logo_h)
    if logo is None:
        return y
    rect = logo.get_rect(midtop=(theme.CENTER_X, y))
    surface.blit(logo, rect)
    return y + rect.height + theme.s(4)


def _stats_row_gap(*, compact: bool) -> int:
    return theme.s(1) if compact else theme.s(6)


def _stats_rows_height(rows, font, *, compact: bool) -> int:
    if not rows:
        return 0
    gap = _stats_row_gap(compact=compact)
    h = font.get_height()
    return len(rows) * (h + gap) - gap


def _stats_row_always_scroll(index: int, *, compact: bool) -> bool:
    """Stats ticker lines scroll like the LED matrix; status-only row stays static."""
    if compact:
        return True
    return index > 0


def _draw_stats_rows_at(
    surface,
    rows,
    y: int,
    font,
    *,
    compact: bool,
    clip_top: int | None = None,
    clip_bottom: int | None = None,
) -> int:
    gap = _stats_row_gap(compact=compact)
    h = font.get_height()
    for i, (text, color) in enumerate(rows):
        if clip_bottom is not None and int(y) > clip_bottom:
            break
        if clip_top is None or int(y) + h >= clip_top:
            _draw_marquee_line(
                surface,
                int(y),
                text,
                font,
                color,
                always_scroll=_stats_row_always_scroll(i, compact=compact),
            )
        y += h + gap
    return y


def _draw_stats_rows_clipped(
    surface,
    rows,
    stats_top: int,
    bottom: int,
    font,
) -> None:
    """Compact mode — clip stats at the content bottom."""
    gap = _stats_row_gap(compact=True)
    h = font.get_height()
    y = stats_top
    for i, (text, color) in enumerate(rows):
        if y + h > bottom:
            break
        _draw_marquee_line(
            surface,
            int(y),
            text,
            font,
            color,
            always_scroll=_stats_row_always_scroll(i, compact=True),
        )
        y += h + gap


def _draw_route_header(surface, data, y: int, title_font, body_font) -> int:
    airline_name = data.get("airline_name", "") or data.get("airline", "")
    display_id = display_flight_id_for_flight(data)
    flight_num = "".join(ch for ch in display_id if ch.isnumeric())
    display_name = f"{airline_name} {flight_num}".strip() if airline_name else display_id
    origin = data.get("origin", "???")
    destination = data.get("destination", "???")

    y = draw.draw_center_line(surface, display_name, y, title_font, theme.LABEL)

    origin_color = _delay_color(
        data.get("time_real_departure"),
        data.get("time_scheduled_departure"),
    )
    dest_color = _delay_color(
        data.get("time_estimated_arrival"),
        data.get("time_scheduled_arrival"),
        is_arrival=True,
    )

    h = body_font.get_height()
    max_w = draw.circle_half_width_at_row(y, h) * 2
    sep = "  →  "
    origin_img = body_font.render(origin, True, origin_color)
    sep_img = body_font.render(sep, True, theme.MUTED)
    dest_img = body_font.render(destination, True, dest_color)
    total_w = origin_img.get_width() + sep_img.get_width() + dest_img.get_width()
    if total_w > max_w:
        y = draw.draw_center_line(surface, f"{origin}{sep}{destination}", y, body_font, theme.ROUTE)
        return y + theme.s(2)

    x = theme.CENTER_X - total_w // 2
    surface.blit(origin_img, (x, y))
    x += origin_img.get_width()
    surface.blit(sep_img, (x, y))
    x += sep_img.get_width()
    surface.blit(dest_img, (x, y))
    return y + h + theme.s(2)


def _draw_progress_bar(surface, data, y: int) -> int:
    bar_h = theme.s(5)
    icon_pad = theme.s(5)
    half_w = draw.circle_half_width_at_row(y, bar_h + icon_pad * 2)
    bar_w = max(theme.s(80), half_w * 2 - theme.s(16))
    x0 = theme.CENTER_X - bar_w // 2
    bar_y = y + icon_pad
    bar_rect = pygame.Rect(x0, bar_y, bar_w, bar_h)
    pygame.draw.rect(surface, theme.GRID, bar_rect, 1)

    progress = _calc_progress(data)
    is_live = data.get("is_live", True)
    flown_color = theme.SWEEP if is_live else theme.TAG_ALT_DESCEND

    flown_w = int(bar_w * progress)
    if flown_w > 0:
        pygame.draw.rect(surface, flown_color, pygame.Rect(x0, bar_y, flown_w, bar_h))

    if flown_w < bar_w:
        pygame.draw.rect(
            surface,
            theme.GRID,
            pygame.Rect(x0 + flown_w, bar_y, bar_w - flown_w, bar_h),
            1,
        )

    # Aircraft icon on the bar — nose points toward destination (right).
    margin = theme.s(6)
    usable = max(1, bar_w - margin * 2)
    plane_x = x0 + margin + int(usable * progress)
    plane_y = bar_y + bar_h // 2
    plane_color = theme.AIRCRAFT if is_live else theme.TAG_ALT_DESCEND
    aircraft.draw_progress_plane(surface, plane_x, plane_y, plane_color)

    return bar_y + bar_h + icon_pad


def _draw_empty(surface, top: int, bottom: int):
    title_font = draw.load_font(theme.FONT_TITLE, bold=True)
    body_font = draw.load_font(theme.FONT_BODY)
    detail_font = draw.load_font(theme.FONT_DETAIL)

    y = top + theme.s(12)
    y = draw.draw_center_line(surface, "No tracked flight.", y, title_font, theme.LABEL)
    y += theme.s(6)
    if y + body_font.get_height() <= bottom:
        y = draw.draw_center_line(
            surface,
            "Select a flight on the web portal.",
            y,
            body_font,
            theme.MUTED,
        )
        y += theme.s(6)
    if y + detail_font.get_height() <= bottom:
        host = socket.gethostname().split(".")[0]
        draw.draw_center_line(surface, f"http://{host}.local:8080", y, detail_font, theme.HINT)


def _draw_pending(surface, callsign: str, top: int, bottom: int):
    title_font = draw.load_font(theme.FONT_TITLE, bold=True)
    body_font = draw.load_font(theme.FONT_BODY)
    detail_font = draw.load_font(theme.FONT_DETAIL)

    y = top + theme.s(8)
    y = _draw_logo(surface, {"callsign": callsign}, y)
    y = draw.draw_center_line(surface, callsign, y, title_font, theme.LABEL)
    y += theme.s(10)
    if y + body_font.get_height() <= bottom:
        y = draw.draw_center_line(surface, "Waiting for flight data", y, body_font, theme.MUTED)
        y += theme.s(8)
    if y + detail_font.get_height() <= bottom:
        y = draw.draw_center_line(surface, "Starts when flight goes live", y, detail_font, theme.HINT)


def _finish_marquee_frame():
    global _marquee_animating
    for key in list(_marquee_states):
        if key not in _marquee_active_keys:
            del _marquee_states[key]
    _marquee_active_keys.clear()
    _marquee_animating = bool(_marquee_states)


def draw_tracked(
    surface,
    tracked_data,
    callsign: str | None = None,
    scroll_offset: int = 0,
) -> int:
    global _marquee_active_keys
    _marquee_active_keys = set()
    del scroll_offset  # tracked page does not scroll vertically

    draw.fill_background(surface)
    raw_callsign = (callsign or load_tracked_callsign() or "").strip().upper()
    display_id = raw_callsign
    if tracked_data:
        display_id = display_flight_id_for_flight(tracked_data)
    trail = ["Radar", "Track"]
    if display_id and display_id != "—":
        trail.append(display_id)
    nav.draw_breadcrumb(surface, trail)

    top = nav.content_top_y()
    compact_stats = settings.tracked_stats_mode() == settings.TRACKED_STATS_COMPACT
    title_font = draw.load_font(theme.s(20), bold=True)
    body_font = draw.load_font(theme.s(16))
    detail_font = draw.load_font(theme.s(15))
    content_bottom = nav.content_bottom_y()

    if not raw_callsign:
        _draw_empty(surface, top, content_bottom)
        nav.draw_footer_buttons(surface, list(FOOTER_BUTTONS))
        _finish_marquee_frame()
        return 0

    if not tracked_data:
        _draw_pending(surface, raw_callsign, top, content_bottom)
        nav.draw_footer_buttons(surface, list(FOOTER_BUTTONS))
        _finish_marquee_frame()
        return 0

    stats_rows = _build_stats_rows(tracked_data)
    y = top + theme.s(2)
    y = _draw_logo(surface, tracked_data, y)
    y = _draw_route_header(surface, tracked_data, y, title_font, body_font)
    if not tracked_data.get("is_scheduled"):
        y = _draw_progress_bar(surface, tracked_data, y)
        y += theme.s(1)
    else:
        y += theme.s(4)
    if stats_rows:
        if compact_stats:
            _draw_stats_rows_clipped(surface, stats_rows, y, content_bottom, detail_font)
        else:
            _draw_stats_rows_at(
                surface,
                stats_rows,
                y,
                detail_font,
                compact=False,
                clip_top=top,
                clip_bottom=content_bottom,
            )
    nav.draw_footer_buttons(surface, list(FOOTER_BUTTONS))
    _finish_marquee_frame()
    return 0
