"""Opaque silhouette interpolation for the original character turn artwork."""

import numpy as np


def _distance_to(mask):
    height, width = mask.shape
    limit = height + width + 1
    columns = np.arange(width, dtype=np.float32)[None, :]
    left = columns - np.maximum.accumulate(np.where(mask, columns, -limit), axis=1)
    reverse = mask[:, ::-1]
    right = columns - np.maximum.accumulate(np.where(reverse, columns, -limit), axis=1)
    distance = np.minimum(left, right[:, ::-1])
    for row in range(1, height):
        distance[row] = np.minimum(distance[row], distance[row - 1] + 1)
    for row in range(height - 2, -1, -1):
        distance[row] = np.minimum(distance[row], distance[row + 1] + 1)
    return distance


def alpha_field(alpha):
    """Signed contour distance, preserving the source's antialiased edge exactly."""
    inside = alpha >= 128
    field = _distance_to(~inside) - _distance_to(inside)
    field -= np.sign(field) * .5
    partial = (alpha > 0) & (alpha < 255)
    field[partial] = alpha[partial] / 255 - .5
    return field


def opaque_morph(premultiplied, field):
    """One moving contour, with opaque interior; no faded second silhouette."""
    alpha = np.clip(field + .5, 0, 1) * 255
    scale = np.divide(alpha, premultiplied[:, :, 3], out=np.zeros_like(alpha), where=premultiplied[:, :, 3] > 0)
    result = np.empty_like(premultiplied, dtype=np.uint8)
    result[:, :, :3] = np.clip(np.rint(premultiplied[:, :, :3] * scale[:, :, None]), 0, 255).astype(np.uint8)
    result[:, :, 3] = np.rint(alpha).astype(np.uint8)
    return result
