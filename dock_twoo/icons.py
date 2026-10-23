"""SVG Icon management, dynamic coloring, and standardized rendering for Dock T(w)oo.

All icons are vector SVGs rendered at strict uniform bounding boxes.
Supports live theme tinting, user-defined icon colors, and opacity adjustments.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QByteArray, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer


def get_assets_dir() -> Path:
    """Return the assets directory."""
    return Path(__file__).resolve().parent.parent / "assets"


def get_icons_dir() -> Path:
    """Return the SVG icons directory."""
    return get_assets_dir() / "icons"


class IconManager:
    """Loads, tints, and caches standard-sized SVG icons."""

    _instance: Optional[IconManager] = None
    _pixmap_cache: Dict[Tuple[str, int, str, float, bool], QPixmap] = {}

    def __init__(self, icons_dir: Optional[Path] = None):
        self.icons_dir = icons_dir or get_icons_dir()
        self._svg_cache: Dict[str, str] = {}
        self._load_svgs()

    @classmethod
    def get_instance(cls) -> IconManager:
        if cls._instance is None:
            cls._instance = IconManager()
        return cls._instance

    def _load_svgs(self) -> None:
        """Preload SVG text contents."""
        if not self.icons_dir.exists():
            return
        for file in self.icons_dir.glob("*.svg"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    self._svg_cache[file.stem] = f.read()
            except Exception as e:
                print(f"[Dock T(w)oo] Failed to read {file}: {e}")

    def get_raw_svg(self, name: str) -> Optional[str]:
        """Return raw SVG string for an icon."""
        if name in self._svg_cache:
            return self._svg_cache[name]
        svg_file = self.icons_dir / f"{name}.svg"
        if svg_file.exists():
            with open(svg_file, "r", encoding="utf-8") as f:
                content = f.read()
                self._svg_cache[name] = content
                return content
        return None

    def render_pixmap(
        self,
        name: str,
        size: int = 22,
        color: str = "#E0E0E6",
        opacity: float = 0.9,
        is_active: bool = False,
        scale_factor: float = 2.0,  # High-DPI support
    ) -> QPixmap:
        """Render standard SVG icon into a high-DPI QPixmap with tinting and opacity."""
        cache_key = (name, size, color, opacity, is_active)
        if cache_key in self._pixmap_cache:
            return self._pixmap_cache[cache_key]

        raw_svg = self.get_raw_svg(name)
        if not raw_svg:
            # Fallback circle placeholder
            pixmap = self._render_fallback(size, color, opacity, scale_factor)
            self._pixmap_cache[cache_key] = pixmap
            return pixmap

        # Tint the SVG by replacing stroke/fill colors or injecting style
        tinted_svg = self._tint_svg(raw_svg, color, opacity, is_active)

        # Render using QSvgRenderer
        renderer = QSvgRenderer(QByteArray(tinted_svg.encode("utf-8")))

        pixel_size = int(size * scale_factor)
        image = QImage(pixel_size, pixel_size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Center and render inside pixel_size
        renderer.render(painter, QRectF(0, 0, pixel_size, pixel_size))
        painter.end()

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(scale_factor)
        self._pixmap_cache[cache_key] = pixmap
        return pixmap

    def _tint_svg(self, svg: str, color: str, opacity: float, is_active: bool) -> str:
        """Inject color and opacity into SVG text, preserving multi-color gradient SVGs."""
        if "<linearGradient" in svg or "<radialGradient" in svg:
            # Preserve rich vibrant multi-color illustration (e.g. Brain robot)
            if is_active:
                return svg
            effective_opacity = max(0.2, min(1.0, opacity))
            if "<svg " in svg:
                return svg.replace("<svg ", f'<svg style="opacity: {effective_opacity};" ', 1)
            return svg

        effective_color = "#FFFFFF" if is_active else color
        effective_opacity = 1.0 if is_active else max(0.1, min(1.0, opacity))

        # Inject style header for currentColor and opacity
        replacement = (
            f'<svg style="color: {effective_color}; opacity: {effective_opacity};" '
        )
        if "<svg " in svg:
            tinted = svg.replace("<svg ", replacement, 1)
        elif "<svg>" in svg:
            tinted = svg.replace("<svg>", replacement + ">", 1)
        else:
            tinted = svg

        # Replace any explicit hardcoded gray/black colors if present
        tinted = tinted.replace('stroke="black"', f'stroke="{effective_color}"')
        tinted = tinted.replace('fill="black"', f'fill="{effective_color}"')
        return tinted

    def _render_fallback(
        self, size: int, color: str, opacity: float, scale_factor: float
    ) -> QPixmap:
        """Render standard dot when SVG is missing."""
        pixel_size = int(size * scale_factor)
        image = QImage(pixel_size, pixel_size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        qc = QColor(color)
        qc.setAlphaF(max(0.1, min(1.0, opacity)))
        painter.setBrush(QBrush(qc))
        painter.setPen(Qt.PenStyle.NoPen)
        r = pixel_size * 0.25
        painter.drawEllipse(QRectF(r, r, pixel_size - 2 * r, pixel_size - 2 * r))
        painter.end()

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(scale_factor)
        return pixmap

    def clear_cache(self) -> None:
        """Clear cached pixmaps (useful on theme change)."""
        self._pixmap_cache.clear()
