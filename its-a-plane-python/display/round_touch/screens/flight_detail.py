"""Flight detail screen."""

from display.round_touch import aircraft, draw, geo, logos, nav, settings, theme
from utilities.airline_branding import display_flight_id_for_flight
from utilities.icao_types import format_aircraft_type

FOOTER_BUTTONS = ("prev", "next", "radar")
FOOTER_EMPTY = ("radar",)


def footer_labels(flights) -> tuple[str, ...]:
    return FOOTER_BUTTONS if flights else FOOTER_EMPTY


def tap_footer_action(x: int, y: int, flights) -> str | None:
    labels = footer_labels(flights)
    idx = nav.tap_footer_button(x, y, len(labels))
    if idx is None:
        return None
    if not flights:
        return "radar"
    return ("prev", "next", "radar")[idx]


def _format_speed(ground_speed) -> str | None:
    if ground_speed is None or ground_speed <= 0:
        return None
    kts = float(ground_speed)
    if settings.distance_in_miles():
        return f"{int(kts * 1.15078)} mph"
    return f"{int(kts * 1.852)} km/h"


def _format_local_distance(dist_km: float) -> str:
    if settings.distance_in_miles():
        dist_mi = dist_km / 1.609344
        if dist_mi >= 0.1:
            return f"{dist_mi:.1f} mi"
        return f"{dist_km * 3280.84:.0f} ft"
    if dist_km >= 1:
        return f"{dist_km:.1f} km"
    return f"{dist_km * 1000:.0f} m"


def _draw_row(surface, text: str, y: int, font, color) -> int:
    h = font.get_height()
    max_w = draw.circle_half_width_at_row(y, h) * 2
    line = draw.fit_text(text, font, max_w)
    rendered = font.render(line, True, color)
    surface.blit(rendered, rendered.get_rect(midtop=(theme.CENTER_X, y)))
    return h


def _draw_logo(surface, flight, y: int) -> int:
    logo_h = theme.s(36)
    logo = logos.load_logo_surface(logos.icao_for_flight(flight), logo_h)
    if logo is None:
        return y
    rect = logo.get_rect(midtop=(theme.CENTER_X, y))
    surface.blit(logo, rect)
    return y + rect.height + theme.s(4)


def draw_flight_detail(surface, flights, selected_index, scroll_offset: int = 0) -> int:
    draw.fill_background(surface)
    title_font = draw.load_font(theme.s(22), bold=True)
    body_font = draw.load_font(theme.s(18))
    detail_font = draw.load_font(theme.s(16))
    chrome_top = nav.content_top_y(has_dots=True)
    line_gap = theme.s(3)

    if not flights:
        nav.draw_breadcrumb(surface, ["Radar", "Flight"])
        nav.draw_footer_buttons(surface, list(FOOTER_EMPTY))
        _draw_row(surface, "No aircraft", chrome_top, body_font, theme.MUTED)
        return 0

    idx = max(0, min(selected_index, len(flights) - 1))
    f = flights[idx]
    callsign = display_flight_id_for_flight(f)
    nav.draw_breadcrumb(surface, ["Radar", "Flight", callsign])
    nav.draw_page_dots(surface, idx, len(flights))

    airline = f.get("airline") or "Airline unknown"
    origin = f.get("origin") or "—"
    dest = f.get("destination") or "—"
    plane_type = format_aircraft_type(f.get("plane") or "")
    alt = aircraft.format_altitude(f.get("altitude"))

    telemetry: list[str] = []
    if alt != "—":
        telemetry.append(alt)
    speed_str = _format_speed(f.get("ground_speed"))
    if speed_str:
        telemetry.append(speed_str)
    heading = f.get("heading")
    if heading is not None and int(heading) > 0:
        telemetry.append(f"HDG {int(heading)}°")

    lat = f.get("plane_latitude")
    lon = f.get("plane_longitude")
    dist_line = ""
    if lat is not None and lon is not None:
        dist_line = _format_local_distance(geo.local_offset_km(lat, lon)[2])

    rows: list[tuple[str, object, tuple[int, int, int]]] = [
        (callsign, title_font, theme.LABEL),
        (airline, body_font, theme.MUTED),
        (f"{origin} > {dest}", body_font, theme.ROUTE),
    ]
    if plane_type:
        rows.append((plane_type, detail_font, theme.MUTED))
    if telemetry:
        rows.append(("  ·  ".join(telemetry), detail_font, theme.LABEL))
    if dist_line:
        rows.append((dist_line, detail_font, theme.MUTED))

    logo_h = theme.s(36) + theme.s(4)
    rows_h = sum(font.get_height() + line_gap for _, font, _ in rows) - line_gap
    total_h = logo_h + rows_h
    bottom = nav.content_bottom_y()
    max_scroll = max(0, total_h - (bottom - chrome_top))

    y = chrome_top - scroll_offset
    y = _draw_logo(surface, f, y)
    for text, font, color in rows:
        h = font.get_height()
        if y + h >= chrome_top and y <= bottom:
            _draw_row(surface, text, int(y), font, color)
        y += h + line_gap

    nav.draw_footer_buttons(surface, list(FOOTER_BUTTONS))
    return max_scroll
