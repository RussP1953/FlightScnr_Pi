"""Unit tests for radar position dead-reckoning between ADS-B polls."""

from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOffsetLatLon(unittest.TestCase):
    def test_moves_east_at_heading_90(self):
        from display.round_touch.position_smooth import offset_lat_lon

        lat, lon = offset_lat_lon(37.0, -122.0, heading_deg=90.0, speed_kt=360.0, dt_s=10.0)
        self.assertAlmostEqual(lat, 37.0, places=5)
        self.assertGreater(lon, -122.0)
        expected_dlon = 1.852 / (111.320 * math.cos(math.radians(37.0)))
        self.assertAlmostEqual(lon + 122.0, expected_dlon, places=3)


class TestPositionSmoother(unittest.TestCase):
    def test_coasts_between_identical_reports(self):
        from display.round_touch.position_smooth import PositionSmoother

        sm = PositionSmoother()
        flight = {
            "icao_hex": "ABC123",
            "callsign": "TEST1",
            "plane_latitude": 37.5,
            "plane_longitude": -122.2,
            "heading": 0.0,
            "ground_speed": 360.0,
        }
        t0 = 1_000_000.0
        first = sm.apply([flight], now=t0)[0]
        self.assertEqual(first["plane_latitude"], 37.5)

        later = sm.apply([flight], now=t0 + 2.0)[0]
        self.assertGreater(later["plane_latitude"], 37.5)
        expected = 37.5 + (360.0 * 1.852 * 2.0 / 3600.0) / 110.574
        self.assertAlmostEqual(later["plane_latitude"], expected, places=5)
        self.assertEqual(later["plane_longitude"], flight["plane_longitude"])

    def test_advances_each_frame_on_same_fix(self):
        from display.round_touch.position_smooth import PositionSmoother

        sm = PositionSmoother()
        flight = {
            "icao_hex": "ABC123",
            "plane_latitude": 40.0,
            "plane_longitude": -74.0,
            "heading": 90.0,
            "ground_speed": 180.0,
        }
        t0 = 5_000.0
        a = sm.apply([flight], now=t0 + 0.1)[0]
        b = sm.apply([flight], now=t0 + 0.2)[0]
        self.assertGreater(b["plane_longitude"], a["plane_longitude"])

    def test_continuity_on_new_position(self):
        from display.round_touch.position_smooth import PositionSmoother

        sm = PositionSmoother()
        f1 = {
            "icao_hex": "ABC123",
            "plane_latitude": 40.0,
            "plane_longitude": -74.0,
            "heading": 90.0,
            "ground_speed": 200.0,
        }
        t0 = 10_000.0
        sm.apply([f1], now=t0)
        coasted = sm.apply([f1], now=t0 + 2.0)[0]

        f2 = dict(f1)
        f2["plane_longitude"] = -73.99
        after = sm.apply([f2], now=t0 + 2.0)[0]
        self.assertGreaterEqual(
            after["plane_longitude"],
            min(coasted["plane_longitude"], f2["plane_longitude"]) - 0.001,
        )

    def test_parked_or_slow_not_extrapolated(self):
        from display.round_touch.position_smooth import PositionSmoother

        sm = PositionSmoother()
        flight = {
            "icao_hex": "ABC123",
            "plane_latitude": 40.0,
            "plane_longitude": -74.0,
            "heading": 90.0,
            "ground_speed": 0.2,
        }
        t0 = 20_000.0
        sm.apply([flight], now=t0)
        later = sm.apply([flight], now=t0 + 2.0)[0]
        self.assertEqual(later["plane_latitude"], 40.0)
        self.assertEqual(later["plane_longitude"], -74.0)

    def test_missing_kinematics_passthrough(self):
        from display.round_touch.position_smooth import PositionSmoother

        sm = PositionSmoother()
        flight = {
            "icao_hex": "ABC123",
            "plane_latitude": 40.0,
            "plane_longitude": -74.0,
        }
        t0 = 30_000.0
        sm.apply([flight], now=t0)
        later = sm.apply([flight], now=t0 + 2.0)[0]
        self.assertEqual(later["plane_latitude"], 40.0)
        self.assertEqual(later["plane_longitude"], -74.0)


if __name__ == "__main__":
    unittest.main()
