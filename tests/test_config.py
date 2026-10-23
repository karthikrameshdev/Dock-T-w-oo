"""Unit tests for configuration management."""

import json
from pathlib import Path

from dock_twoo.config import ConfigManager, DockAppItem, DockConfig


def test_default_config_properties():
    cfg = DockConfig()
    assert cfg.edge == "right"
    assert cfg.dock_width == 60
    assert cfg.icon_size == 20
    assert cfg.dock_corner_radius == 28
    assert cfg.dock_height_mode == "fill"
    assert cfg.theme_mode == "system"
    assert cfg.server_port == 28842
    assert len(cfg.apps) > 10


def test_config_serialization():
    cfg = DockConfig(edge="left", icon_size=24, dock_width=64)
    data = cfg.to_dict()

    assert data["edge"] == "left"
    assert data["icon_size"] == 24
    assert data["dock_width"] == 64
    assert isinstance(data["apps"], list)

    restored = DockConfig.from_dict(data)
    assert restored.edge == "left"
    assert restored.icon_size == 24
    assert restored.dock_width == 64
    assert len(restored.apps) == len(cfg.apps)
    assert isinstance(restored.apps[0], DockAppItem)


def test_config_manager_updates_and_listeners(tmp_path: Path):
    config_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=config_file)

    notified = []

    def on_change(c: DockConfig):
        notified.append(c.edge)

    mgr.add_listener(on_change)

    mgr.update({"edge": "left", "icon_size": 26})

    assert mgr.config.edge == "left"
    assert mgr.config.icon_size == 26
    assert notified == ["left"]

    # Verify persisted to disk
    assert config_file.exists()
    with open(config_file, "r") as f:
        saved = json.load(f)
    assert saved["edge"] == "left"
    assert saved["icon_size"] == 26
