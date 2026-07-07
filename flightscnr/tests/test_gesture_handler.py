"""
Regression tests for frozen radar touch gesture logic.

Run before any change to gesture_handler.py, input_handler.py, or pinch_handler.py:
    python3 -m unittest tests.test_gesture_handler -v
"""

import importlib
import importlib.util
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("FLIGHTSCNR_DATA_DIR", "/tmp/flightscnr_gesture_test")

import pygame

def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RT = os.path.join(_ROOT, "display", "round_touch")

input_handler = _load_module(
    "gesture_test_input_handler",
    os.path.join(_RT, "input_handler.py"),
)
pinch_handler = _load_module(
    "gesture_test_pinch_handler",
    os.path.join(_RT, "pinch_handler.py"),
)

# gesture_handler imports display.round_touch.* — stub package for isolated tests.
import types

if "display.round_touch.input_handler" not in sys.modules:
    display_pkg = types.ModuleType("display")
    round_touch_pkg = types.ModuleType("display.round_touch")
    sys.modules["display"] = display_pkg
    sys.modules["display.round_touch"] = round_touch_pkg
sys.modules["display.round_touch.input_handler"] = input_handler
sys.modules["display.round_touch.pinch_handler"] = pinch_handler
rotation_stub = types.ModuleType("display.round_touch.rotation")
rotation_stub.to_logical = lambda x, y: (float(x), float(y))
sys.modules["display.round_touch.rotation"] = rotation_stub

gesture_handler = _load_module(
    "gesture_test_gesture_handler",
    os.path.join(_RT, "gesture_handler.py"),
)

GESTURE_LOGIC_VERSION = gesture_handler.GESTURE_LOGIC_VERSION
RadarGestureHandler = gesture_handler.RadarGestureHandler
TouchInput = input_handler.TouchInput
SWIPE_RIGHT = input_handler.SWIPE_RIGHT
PinchZoom = pinch_handler.PinchZoom


def _finger_event(etype, *, fid=0, x=0.5, y=0.5):
    return SimpleNamespace(type=etype, finger_id=fid, x=x, y=y)


def _mouse_down(x=360, y=360):
    return SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y))


def _mouse_up(x=360, y=360):
    return SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(x, y))


def _mouse_motion(x, y):
    return SimpleNamespace(type=pygame.MOUSEMOTION, pos=(x, y), buttons=(1, 0, 0))


def _surface():
    surf = MagicMock()
    surf.get_width.return_value = 720
    surf.get_height.return_value = 720
    return surf


def _coord_patches(surface):
    return patch("pygame.display.get_surface", return_value=surface)


class TestFrozenContract(unittest.TestCase):
    def test_version_is_set(self):
        self.assertGreaterEqual(GESTURE_LOGIC_VERSION, 1)


class TestTouchInput(unittest.TestCase):
    def test_tap_below_threshold(self):
        touch = TouchInput()
        surface = _surface()
        with _coord_patches(surface):
            touch.handle_event(_mouse_down(100, 100))
            touch.handle_event(_mouse_up(110, 110))
            gesture = touch.consume_gesture()
        self.assertEqual(gesture[0], "tap")
        self.assertEqual(gesture[1], (110, 110))

    def test_swipe_above_threshold(self):
        touch = TouchInput()
        surface = _surface()
        with _coord_patches(surface):
            touch.handle_event(_mouse_down(100, 100))
            touch.handle_event(_mouse_motion(200, 100))
            touch.handle_event(_mouse_up(200, 100))
            gesture = touch.consume_gesture()
        self.assertEqual(gesture[0], "swipe")
        self.assertEqual(gesture[1], SWIPE_RIGHT)

    def test_short_drag_is_tap_not_swipe(self):
        touch = TouchInput()
        surface = _surface()
        with _coord_patches(surface):
            touch.handle_event(_mouse_down(200, 200))
            touch.handle_event(_mouse_motion(210, 205))
            touch.handle_event(_mouse_up(210, 205))
            gesture = touch.consume_gesture()
        self.assertEqual(gesture[0], "tap")


class TestPinchZoom(unittest.TestCase):
    def setUp(self):
        self.handler = RadarGestureHandler(TouchInput(), PinchZoom())
        self.surface = _surface()

    def test_single_finger_drag_no_zoom(self):
        with _coord_patches(self.surface):
            self.handler.handle_input_event(_mouse_down(300, 300))
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=1, x=300 / 720, y=300 / 720)
            )
            for x in range(300, 380, 10):
                self.handler.handle_input_event(_mouse_motion(x, 300))
                delta = self.handler.handle_finger_event(
                    _finger_event(pygame.FINGERMOTION, fid=1, x=x / 720, y=300 / 720)
                )
                self.assertEqual(delta, 0)

    def test_confirmed_pinch_zooms(self):
        with _coord_patches(self.surface):
            self.handler.handle_input_event(_mouse_down(300, 300))
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=1, x=0.35, y=0.5)
            )
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=2, x=0.55, y=0.5)
            )
            deltas = []
            for spread in (0.55, 0.60, 0.66, 0.72):
                self.handler.handle_finger_event(
                    _finger_event(pygame.FINGERMOTION, fid=1, x=0.35, y=0.5)
                )
                deltas.append(
                    self.handler.handle_finger_event(
                        _finger_event(pygame.FINGERMOTION, fid=2, x=spread, y=0.5)
                    )
                )
            self.assertTrue(any(d != 0 for d in deltas))

    def test_swipe_ghost_dropped_no_zoom(self):
        with _coord_patches(self.surface):
            self.handler.handle_input_event(_mouse_down(200, 300))
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=1, x=200 / 720, y=300 / 720)
            )
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=9, x=200 / 720, y=300 / 720)
            )
            deltas = []
            for x in range(200, 320, 15):
                self.handler.handle_input_event(_mouse_motion(x, 300))
                deltas.append(
                    self.handler.handle_finger_event(
                        _finger_event(pygame.FINGERMOTION, fid=1, x=x / 720, y=300 / 720)
                    )
                )
            self.assertTrue(all(d == 0 for d in deltas))
            self.assertLessEqual(self.handler.pinch.finger_count(), 1)

    def test_pointer_sync_clears_stale_contacts(self):
        with _coord_patches(self.surface):
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=9, x=0.5, y=0.5)
            )
            self.assertEqual(self.handler.pinch.finger_count(), 1)
            self.handler.on_pointer_up()
            self.assertEqual(self.handler.pinch.finger_count(), 0)

    def test_zoom_suppresses_tap_once(self):
        with _coord_patches(self.surface):
            self.handler.handle_input_event(_mouse_down(300, 300))
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=1, x=0.35, y=0.5)
            )
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=2, x=0.55, y=0.5)
            )
            for spread in (0.55, 0.62, 0.70, 0.78):
                self.handler.handle_finger_event(
                    _finger_event(pygame.FINGERMOTION, fid=1, x=0.35, y=0.5)
                )
                self.handler.handle_finger_event(
                    _finger_event(pygame.FINGERMOTION, fid=2, x=spread, y=0.5)
                )
            self.assertTrue(self.handler.pinch.should_suppress_tap())
            self.assertFalse(self.handler.pinch.should_suppress_tap())


class TestRadarGestureHandler(unittest.TestCase):
    def setUp(self):
        self.handler = RadarGestureHandler(TouchInput(), PinchZoom())

    def test_cancel_gesture_only_on_scale_delta(self):
        surface = _surface()
        with _coord_patches(surface):
            self.handler.handle_input_event(_mouse_down(100, 100))
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERDOWN, fid=1, x=100 / 720, y=100 / 720)
            )
            self.assertTrue(self.handler.touch.is_dragging())
            self.handler.handle_finger_event(
                _finger_event(pygame.FINGERMOTION, fid=1, x=120 / 720, y=100 / 720)
            )
            self.assertTrue(self.handler.touch.is_dragging())

    def test_event_classifiers(self):
        self.assertTrue(RadarGestureHandler.is_pointer_down(_mouse_down()))
        self.assertTrue(RadarGestureHandler.is_pointer_up(_mouse_up()))
        self.assertTrue(RadarGestureHandler.is_finger_event(_finger_event(pygame.FINGERDOWN)))
        self.assertTrue(RadarGestureHandler.is_touch_event(_mouse_motion(1, 2)))


if __name__ == "__main__":
    unittest.main()
