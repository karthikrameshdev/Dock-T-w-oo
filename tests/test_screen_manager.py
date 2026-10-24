"""Unit tests for screen manager and geometry computations."""

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
import pytest

from dock_twoo.config import DockConfig
from dock_twoo.os_integration.screen_manager import ScreenManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dock_geometry_calculation_right_edge(qapp):
    cfg = DockConfig(edge="right", dock_width=60, edge_offset_x=10, dock_height_mode="fixed", dock_height_fixed=600)
    geom = ScreenManager.calculate_dock_geometry(cfg, content_height=600)

    avail = ScreenManager.get_available_geometry(0)
    glow_pad = 8 if cfg.glow_enabled else 2
    thickness = 60 + (glow_pad * 2)
    assert geom.width() == thickness
    assert geom.height() == 600
    # X should be close to right edge
    assert geom.right() <= avail.right()
    assert geom.x() == avail.right() - thickness - 10


def test_dock_geometry_calculation_left_edge(qapp):
    cfg = DockConfig(edge="left", dock_width=64, edge_offset_x=12, dock_height_mode="fixed", dock_height_fixed=500)
    geom = ScreenManager.calculate_dock_geometry(cfg, content_height=500)

    avail = ScreenManager.get_available_geometry(0)
    glow_pad = 8 if cfg.glow_enabled else 2
    thickness = 64 + (glow_pad * 2)
    assert geom.width() == thickness
    assert geom.x() == avail.left() + 12


def test_attached_window_geometry_pinned_to_dock(qapp):
    avail = ScreenManager.get_available_geometry(0)
    dock_x = avail.right() - 70
    dock_geom = QRect(dock_x, 200, 60, 700)
    cfg = DockConfig(edge="right", attached_width=380, attached_height=500, attached_gap=10)

    attached = ScreenManager.calculate_attached_geometry(dock_geom, cfg, target_center_y=350)

    # When dock is on right, attached window must be to its left:
    expected_x = dock_geom.left() - 380 - 10
    # Clamped to screen if needed
    clamped_expected_x = max(avail.left() + 10, min(expected_x, avail.right() - 380 - 10))
    assert attached.width() == 380
    assert attached.x() == clamped_expected_x
    assert attached.right() < dock_geom.left()


def test_attached_window_geometry_pinned_left(qapp):
    dock_geom = QRect(20, 200, 60, 700)
    cfg = DockConfig(edge="left", attached_width=380, attached_height=500, attached_gap=10)

    attached = ScreenManager.calculate_attached_geometry(dock_geom, cfg, target_center_y=350)

    # When dock is on left, attached window must be to its right:
    # x = dock_geom.right() + gap = (20 + 60 - 1) + 10 = 89
    assert attached.width() == 380
    assert attached.x() == dock_geom.right() + 10
    assert attached.left() > dock_geom.right()


def test_dock_geometry_calculation_top_edge(qapp):
    cfg = DockConfig(edge="top", dock_width=60, edge_offset_x=10, dock_height_mode="fixed", dock_height_fixed=700)
    geom = ScreenManager.calculate_dock_geometry(cfg, content_height=700)

    avail = ScreenManager.get_available_geometry(0)
    glow_pad = 8 if cfg.glow_enabled else 2
    thickness = 60 + (glow_pad * 2)
    assert geom.height() == thickness
    assert geom.width() == 700
    assert geom.y() == avail.top() + 10


def test_dock_geometry_calculation_bottom_edge(qapp):
    cfg = DockConfig(edge="bottom", dock_width=60, edge_offset_x=12, dock_height_mode="fixed", dock_height_fixed=650)
    geom = ScreenManager.calculate_dock_geometry(cfg, content_height=650)

    avail = ScreenManager.get_available_geometry(0)
    glow_pad = 8 if cfg.glow_enabled else 2
    thickness = 60 + (glow_pad * 2)
    assert geom.height() == thickness
    assert geom.width() == 650
    assert geom.bottom() <= avail.bottom()


def test_dock_cross_axis_symmetry_across_orientations(qapp):
    """Verify that vertical dock width strictly equals horizontal dock height."""
    for width in (50, 60, 72):
        for glow in (True, False):
            glow_pad = 8 if glow else 2
            expected_thickness = width + (glow_pad * 2)

            cfg_right = DockConfig(edge="right", dock_width=width, dock_height=width, glow_enabled=glow)
            cfg_left = DockConfig(edge="left", dock_width=width, dock_height=width, glow_enabled=glow)
            cfg_top = DockConfig(edge="top", dock_width=width, dock_height=width, glow_enabled=glow)
            cfg_bottom = DockConfig(edge="bottom", dock_width=width, dock_height=width, glow_enabled=glow)

            g_right = ScreenManager.calculate_dock_geometry(cfg_right)
            g_left = ScreenManager.calculate_dock_geometry(cfg_left)
            g_top = ScreenManager.calculate_dock_geometry(cfg_top)
            g_bottom = ScreenManager.calculate_dock_geometry(cfg_bottom)

            assert g_right.width() == expected_thickness
            assert g_left.width() == expected_thickness
            assert g_top.height() == expected_thickness
            assert g_bottom.height() == expected_thickness
            assert g_right.width() == g_top.height()


def test_independent_dock_width_and_height(qapp):
    """Verify that dock_height on horizontal edges does not alter dock_width on vertical edges."""
    cfg = DockConfig(edge="top", dock_width=80, dock_height=52, glow_enabled=True)
    geom_top = ScreenManager.calculate_dock_geometry(cfg)
    assert geom_top.height() == 52 + 16

    cfg.edge = "right"
    geom_right = ScreenManager.calculate_dock_geometry(cfg)
    assert geom_right.width() == 80 + 16


def test_attached_window_geometry_top_and_bottom(qapp):
    avail = ScreenManager.get_available_geometry(0)
    cfg_top = DockConfig(edge="top", attached_width=400, attached_height=500, attached_gap=10)
    dock_top = QRect(200, avail.top() + 10, 800, 60)
    attached_top = ScreenManager.calculate_attached_geometry(dock_top, cfg_top, target_center_y=300)

    assert attached_top.width() == 400
    assert attached_top.top() == dock_top.bottom() + 10

    cfg_bottom = DockConfig(edge="bottom", attached_width=400, attached_height=500, attached_gap=12)
    dock_bottom = QRect(200, avail.bottom() - 60 - 12, 800, 60)
    attached_bottom = ScreenManager.calculate_attached_geometry(dock_bottom, cfg_bottom, target_center_y=300)

    assert attached_bottom.width() == 400
    # In QRect, bottom() is top + height - 1, so the empty gap is dock.top() - attached.bottom() - 1
    assert dock_bottom.top() - attached_bottom.bottom() - 1 == 12

