from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QIcon, QPixmap, QPolygonF


def build_icon_image(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    background = QColor("#121212")
    accent = QColor("#1db954")
    painter.setBrush(background)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.2, size * 0.2)

    circle_size = size * 0.62
    circle_rect = QRectF(
        (size - circle_size) / 2,
        (size - circle_size) / 2,
        circle_size,
        circle_size,
    )
    painter.setBrush(accent)
    painter.drawEllipse(circle_rect)

    triangle = QPolygonF(
        [
            QPointF(size * 0.46, size * 0.36),
            QPointF(size * 0.46, size * 0.64),
            QPointF(size * 0.68, size * 0.5),
        ]
    )
    painter.setBrush(QColor("#0f0f0f"))
    painter.drawPolygon(triangle)
    painter.end()
    return image


def main() -> int:
    app = QGuiApplication(sys.argv)
    sizes = [256, 128, 64, 32, 16]
    icon = QIcon()
    for size in sizes:
        icon.addPixmap(QPixmap.fromImage(build_icon_image(size)))
    pixmap = icon.pixmap(256, 256)
    target = Path("icon.ico")
    if not pixmap.save(str(target)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
