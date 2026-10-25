"""Logical-pixel silhouettes shared by native input and local collision checks."""
from __future__ import annotations

import base64
import json

from PySide6.QtCore import QRect
from PySide6.QtGui import QBitmap, QImage, QRegion, qRgb


def decode_shape(payload, size):
    """Accept a bounded, MSB-first one-bit bitmap from the local WebGL bridge.

    Dimensions must match the current viewport: a delayed pre-resize frame must
    never restore a large hit area. Effects and toy props are excluded by the
    renderer before producing this bitmap; gaps remain genuine click-through.
    """
    if not isinstance(payload, str) or len(payload) > 180000:
        raise ValueError('Invalid silhouette payload')
    data = json.loads(payload)
    width, height = data['width'], data['height']
    if type(width) is not int or type(height) is not int or not (0 < width <= 1024 and 0 < height <= 1024):
        raise ValueError('Invalid silhouette dimensions')
    if (width, height) != (size.width(), size.height()):
        raise ValueError('Stale silhouette dimensions')
    stride = ((width + 31) // 32) * 4
    bits = base64.b64decode(data['bits'], validate=True)
    if len(bits) != stride * height:
        raise ValueError('Invalid silhouette bitmap')
    image = QImage(bits, width, height, stride, QImage.Format.Format_Mono)
    image.setColorTable([qRgb(255, 255, 255), qRgb(0, 0, 0)])
    return QRegion(QBitmap.fromImage(image))


def native_mask(region):
    # Qt interprets an empty mask as "remove the mask", which blocks the whole
    # rectangle. An off-window pixel instead leaves no clickable client pixels.
    return region if not region.isEmpty() else QRegion(-2, -2, 1, 1)


def provisional_body(size):
    """Conservative collision footprint until the first GPU silhouette arrives."""
    return QRegion(QRect(round(size.width() * .25), round(size.height() * .08),
                         max(1, round(size.width() * .5)), max(1, round(size.height() * .84))))
