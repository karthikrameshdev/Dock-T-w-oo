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
    assert geom.width() == 60
    assert geom.height() == 600
    # X should be close to right edge
    assert geom.right() <= avail.right()
    assert geom.x() == avail.right() - 60 - 10


def test_dock_geometry_calculation_left_edge(qapp):
    cfg = DockConfig(edge="left", dock_width=64, edge_offset_x=12, dock_height_mode="fixed", dock_height_fixed=500)
    geom = ScreenManager.calculate_dock_geometry(cfg, content_height=500)

    avail = ScreenManager.get_available_geometry(0)
    assert geom.width() == 64
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
