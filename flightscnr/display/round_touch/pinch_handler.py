"""Two-finger pinch zoom for radar range (capacitive multi-touch).

FROZEN — see gesture_handler.py and tests/test_gesture_handler.py.
Pinch uses FINGER events; never arm from a single-finger mouse drag.
"""

import math

import pygame

_SPAN_STEP_RATIO = 0.15
_FINGER_MOVE_PX = 6
_GHOST_SPAN_SLACK_PX = 18


def _min_span_px() -> int:
    """Minimum finger separation before span changes count (not at touch down)."""
    try:
        from display.round_touch import theme

        return max(20, int(theme.SIZE * 0.035))
    except ImportError:
        return 24


def _logical_pos(event: pygame.event.Event) -> tuple[float, float]:
    from display.round_touch import rotation

    width = pygame.display.get_surface().get_width()
    height = pygame.display.get_surface().get_height()
    if event.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
        x = event.x * width
        y = event.y * height
    else:
        x, y = event.pos
    lx, ly = rotation.to_logical(x, y)
    return float(lx), float(ly)


def _finger_span(fingers: dict[int, tuple[float, float]]) -> float | None:
    if len(fingers) < 2:
        return None
    (x0, y0), (x1, y1) = list(fingers.values())[:2]
    return math.hypot(x1 - x0, y1 - y0)


class PinchZoom:
    """Pinch out = zoom in (closer range); pinch in = zoom out (wider range)."""

    def __init__(self):
        self._fingers: dict[int, tuple[float, float]] = {}
        self._finger_starts: dict[int, tuple[float, float]] = {}
        self._moved: set[int] = set()
        self._baseline_span: float | None = None
        self._suppress_tap = False
        self._pinch_session = False
        self._pinch_confirmed = False
        self._swipe_blocked = False
        self._primary_id: int | None = None

    def finger_count(self) -> int:
        return len(self._fingers)

    def is_pinching(self) -> bool:
        """True only for a confirmed two-finger pinch (never a swipe ghost)."""
        return self._pinch_confirmed and self._pinch_session and len(self._fingers) >= 2

    def should_suppress_tap(self) -> bool:
        if self._suppress_tap:
            self._suppress_tap = False
            return True
        return False

    def _finger_drift(self, fid: int) -> float:
        start = self._finger_starts.get(fid)
        pos = self._fingers.get(fid)
        if start is None or pos is None:
            return 0.0
        sx, sy = start
        px, py = pos
        return math.hypot(px - sx, py - sy)

    def _note_motion(self, fid: int) -> None:
        if self._finger_drift(fid) >= _FINGER_MOVE_PX:
            self._moved.add(fid)

    def _secondary_id(self) -> int | None:
        if self._primary_id is None:
            return None
        for fid in self._fingers:
            if fid != self._primary_id:
                return fid
        return None

    def _is_swipe_ghost(self) -> bool:
        """Phantom 2nd contact: primary swipes away, secondary never moves."""
        sid = self._secondary_id()
        if sid is None or self._primary_id is None:
            return False
        primary_drift = self._finger_drift(self._primary_id)
        secondary_drift = self._finger_drift(sid)
        if primary_drift < 10 or secondary_drift >= _FINGER_MOVE_PX:
            return False
        span = _finger_span(self._fingers) or 0.0
        return abs(span - primary_drift) < _GHOST_SPAN_SLACK_PX

    def _pinch_ready(self) -> bool:
        if self._swipe_blocked or len(self._fingers) < 2 or self._is_swipe_ghost():
            return False
        if len(self._moved) >= 2:
            return True
        sid = self._secondary_id()
        if sid is None:
            return False
        span = _finger_span(self._fingers)
        return sid in self._moved and span is not None and span >= _min_span_px()

    def _maybe_begin_pinch_session(self) -> None:
        if self._pinch_session or not self._pinch_ready():
            return
        span = _finger_span(self._fingers)
        if span is not None and span >= _min_span_px():
            self._pinch_session = True
            self._pinch_confirmed = True
            self._baseline_span = span

    def _reset(self) -> None:
        self._fingers.clear()
        self._finger_starts.clear()
        self._moved.clear()
        self._baseline_span = None
        self._pinch_session = False
        self._pinch_confirmed = False
        self._swipe_blocked = False
        self._primary_id = None

    def sync_pointer_down(self) -> None:
        """Mouse press — drop stale capacitive contacts from a prior gesture."""
        if not self._pinch_confirmed:
            self._reset()

    def sync_pointer_up(self) -> None:
        """Mouse release — finger contacts from the driver should be gone."""
        self._reset()

    def _drop_ghost_finger(self) -> None:
        sid = self._secondary_id()
        if sid is None:
            return
        self._fingers.pop(sid, None)
        self._finger_starts.pop(sid, None)
        self._moved.discard(sid)

    def handle_event(self, event: pygame.event.Event, *, allow_zoom: bool = True) -> int:
        """Return scale index delta: -1 zoom in, +1 zoom out, 0 none."""
        if event.type not in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
            return 0

        fid = int(event.finger_id)

        if event.type == pygame.FINGERDOWN:
            pos = _logical_pos(event)
            self._fingers[fid] = pos
            self._finger_starts[fid] = pos
            if len(self._fingers) == 1:
                self._primary_id = fid
                self._swipe_blocked = False
            elif len(self._fingers) > 2:
                # Driver reported extra contacts — keep the newest pair only.
                keep = list(self._fingers.keys())[-2:]
                self._fingers = {k: self._fingers[k] for k in keep}
                self._finger_starts = {k: self._finger_starts[k] for k in keep}
                self._moved = {k for k in self._moved if k in keep}
                self._primary_id = keep[0]
            elif len(self._fingers) >= 2 and allow_zoom and not self._swipe_blocked:
                self._maybe_begin_pinch_session()
            return 0

        if event.type == pygame.FINGERMOTION:
            if fid not in self._fingers:
                return 0
            self._fingers[fid] = _logical_pos(event)
            self._note_motion(fid)
            if not allow_zoom or self._swipe_blocked or len(self._fingers) < 2:
                return 0
            if self._is_swipe_ghost():
                self._drop_ghost_finger()
                self._swipe_blocked = True
                self._pinch_session = False
                self._pinch_confirmed = False
                self._baseline_span = None
                return 0
            if not self._pinch_session:
                self._maybe_begin_pinch_session()
                return 0
            if not self._pinch_confirmed:
                return 0
            return self._scale_delta_from_span()

        if event.type == pygame.FINGERUP:
            self._fingers.pop(fid, None)
            self._finger_starts.pop(fid, None)
            self._moved.discard(fid)
            if fid == self._primary_id:
                self._primary_id = next(iter(self._fingers), None)
            if not self._fingers:
                if self._pinch_confirmed:
                    self._suppress_tap = True
                self._reset()
            elif len(self._fingers) < 2:
                if self._pinch_confirmed:
                    self._suppress_tap = True
                self._pinch_session = False
                self._pinch_confirmed = False
                self._baseline_span = None
            return 0

        return 0

    def _scale_delta_from_span(self) -> int:
        if not self._pinch_confirmed or not self._pinch_session or len(self._fingers) < 2:
            return 0
        if self._is_swipe_ghost():
            return 0
        span = _finger_span(self._fingers)
        if span is None or span < _min_span_px():
            return 0
        if self._baseline_span is None:
            self._baseline_span = span
            return 0

        ratio = span / self._baseline_span
        if ratio >= 1.0 + _SPAN_STEP_RATIO:
            self._baseline_span = span
            self._suppress_tap = True
            return -1
        if ratio <= 1.0 - _SPAN_STEP_RATIO:
            self._baseline_span = span
            self._suppress_tap = True
            return 1
        return 0
