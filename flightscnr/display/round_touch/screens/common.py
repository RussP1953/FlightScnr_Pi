"""Shared helpers for round-touch flight screens."""

from display.round_touch import draw, logos, settings, theme


def format_speed(ground_speed) -> str | None:
    """Format ground speed using display units from Settings → Display."""
    if ground_speed is None or ground_speed <= 0:
        return None
    kts = float(ground_speed)
    units = settings.distance_units()
    if units == "mi":
        return f"{int(kts * 1.15078)} mph"
    if units == "nm":
        return f"{int(kts)} kts"
    return f"{int(kts * 1.852)} km/h"


def format_local_distance(dist_km: float) -> str:
    units = settings.distance_units()
    if units == "mi":
        dist_mi = dist_km / 1.609344
        if dist_mi >= 0.1:
            return f"{dist_mi:.1f} mi"
        return f"{dist_km * 3280.84:.0f} ft"
    if units == "nm":
        dist_nm = dist_km / 1.852
        if dist_nm >= 0.1:
            return f"{dist_nm:.1f} nm"
        return f"{dist_km * 3280.84:.0f} ft"
    if dist_km >= 1:
        return f"{dist_km:.1f} km"
    return f"{dist_km * 1000:.0f} m"


def draw_center_row(surface, text: str, y: int, font, color) -> int:
    h = font.get_height()
    max_w = draw.circle_half_width_at_row(y, h) * 2
    line = draw.fit_text(text, font, max_w)
    rendered = font.render(line, True, color)
    surface.blit(rendered, rendered.get_rect(midtop=(theme.CENTER_X, y)))
    return h


def draw_logo(surface, flight: dict, y: int, *, logo_h: int | None = None) -> int:
    logo_h = theme.s(36) if logo_h is None else logo_h
    logo = logos.load_logo_surface(logos.icao_for_flight(flight), logo_h)
    if logo is None:
        return y
    rect = logo.get_rect(midtop=(theme.CENTER_X, y))
    surface.blit(logo, rect)
    return y + rect.height + theme.s(4)
