"""Tests for SVG icon loading, dynamic tinting, and standardized dimensions."""

import pytest
from PySide6.QtWidgets import QApplication

from dock_twoo.icons import IconManager, get_icons_dir


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_svg_icons_exist():
    icons_dir = get_icons_dir()
    assert icons_dir.exists()
    required = [
        "logo", "apps", "calendar", "star", "weather", "vault",
        "notes", "checklist", "team", "bookmark", "bell", "chat",
        "sliders", "headset", "feedback", "more", "brain"
    ]
    for name in required:
        file = icons_dir / f"{name}.svg"
        assert file.exists(), f"Missing icon: {name}.svg"


def test_render_standard_sized_pixmaps(qapp):
    mgr = IconManager.get_instance()
    standard_sizes = [18, 20, 24, 32]

    for size in standard_sizes:
        # Test app icons
        for icon_name in ("apps", "calendar", "vault", "notes", "brain", "logo"):
            pixmap = mgr.render_pixmap(
                name=icon_name,
                size=size,
                color="#E0E0E6",
                opacity=0.9,
                scale_factor=1.0,
            )
            assert not pixmap.isNull(), f"Failed rendering {icon_name}"
            # Strict standard size enforcement
            assert pixmap.width() == size
            assert pixmap.height() == size


def test_icon_active_and_dynamic_tinting(qapp):
    mgr = IconManager.get_instance()
    pm_normal = mgr.render_pixmap("vault", size=24, color="#888888", opacity=0.5, is_active=False)
    pm_active = mgr.render_pixmap("vault", size=24, color="#888888", opacity=0.5, is_active=True)

    assert not pm_normal.isNull()
    assert not pm_active.isNull()
    # Distinct cache entries
    assert (
        ("vault", 24, "#888888", 0.5, False) in mgr._pixmap_cache
    )
    assert (
        ("vault", 24, "#888888", 0.5, True) in mgr._pixmap_cache
    )
