"""Design tokens, theme definitions, and style generators for Dock T(w)oo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtGui import QColor, QFont

from dock_twoo.config import DockConfig


@dataclass
class ThemeTokens:
    font_family: str
    font_size_root: int
    font_size_tooltip: int
    font_size_title: int
    bg_color: str
    border_color: str
    card_bg: str
    text_primary: str
    text_secondary: str
    accent_color: str


def get_theme_tokens(config: DockConfig) -> ThemeTokens:
    """Generate theme tokens matching the current resolved theme."""
    is_dark = config.get_effective_theme() == "dark"

    if is_dark:
        return ThemeTokens(
            font_family=config.font_family,
            font_size_root=config.font_size_root,
            font_size_tooltip=config.font_size_tooltip,
            font_size_title=15,
            bg_color=config.dock_bg_color,
            border_color=config.dock_border_color,
            card_bg="rgba(28, 29, 34, 0.95)",
            text_primary="#F0F0F5",
            text_secondary="#8E8E9F",
            accent_color="#3B82F6",
        )
    else:
        return ThemeTokens(
            font_family=config.font_family,
            font_size_root=config.font_size_root,
            font_size_tooltip=config.font_size_tooltip,
            font_size_title=15,
            bg_color=config.dock_bg_color_light,
            border_color=config.dock_border_color_light,
            card_bg="rgba(255, 255, 255, 0.96)",
            text_primary="#1D1D1F",
            text_secondary="#6E6E73",
            accent_color="#0071E3",
        )


def create_app_font(
    config: DockConfig,
    size: Optional[int] = None,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    """Create a QFont instance following Dock T(w)oo root font rules."""
    font = QFont()
    # SF Pro / Apple system font
    font.setFamily("-apple-system")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSize(size or config.font_size_root)
    font.setWeight(weight)
    return font
