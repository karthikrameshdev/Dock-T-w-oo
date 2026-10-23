from PySide6.QtGui import QImage, QPainter, QColor, QBrush, QPen, QRadialGradient, QLinearGradient
from PySide6.QtCore import Qt, QRectF, QPointF

size = 128
image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
image.fill(Qt.GlobalColor.transparent)

painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)

# Draw circle background with warm gradient
grad = QLinearGradient(0, 0, size, size)
grad.setColorAt(0.0, QColor("#D7A57E"))
grad.setColorAt(1.0, QColor("#8D5B4C"))
painter.setBrush(QBrush(grad))
painter.setPen(Qt.PenStyle.NoPen)
painter.drawEllipse(QRectF(4, 4, size - 8, size - 8))

# Draw stylized person silhouette
painter.setBrush(QBrush(QColor("#3A2A27")))
# Head
painter.drawEllipse(QRectF(size * 0.32, size * 0.22, size * 0.36, size * 0.38))
# Body / shoulders
painter.drawChord(QRectF(size * 0.16, size * 0.58, size * 0.68, size * 0.70), 0, 180 * 16)

# Outer border ring
pen = QPen(QColor("#777777"), 4)
painter.setBrush(Qt.BrushStyle.NoBrush)
painter.setPen(pen)
painter.drawEllipse(QRectF(3, 3, size - 6, size - 6))

painter.end()
image.save("/Users/karthikramesh/Projects/Self/OSS/Dock T(w)oo/assets/avatar.png")
print("Saved avatar.png")
