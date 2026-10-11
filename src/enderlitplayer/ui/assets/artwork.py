"""Painted artwork: the application icon, cover placeholders and the mix cover."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap, QPolygonF

from enderlitplayer.ui.assets.icons import paint_icon
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import ACCENT

APP_ICON_BACKGROUND = "#121212"


def build_icon_image(size: int) -> QImage:
    """The Enderlit logo: a green disc with a play glyph on a dark rounded square."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(APP_ICON_BACKGROUND))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    circle = size * 0.62
    painter.setBrush(QColor(ACCENT))
    painter.drawEllipse(QRectF((size - circle) / 2, (size - circle) / 2, circle, circle))
    painter.setBrush(QColor("#0f0f0f"))
    painter.drawPolygon(
        QPolygonF(
            [
                QPointF(size * 0.45, size * 0.36),
                QPointF(size * 0.45, size * 0.64),
                QPointF(size * 0.67, size * 0.5),
            ]
        )
    )
    painter.end()
    return image


def build_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(build_icon_image(size)))
    return icon


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_cover(
    painter: QPainter,
    rect: QRectF,
    pixmap: QPixmap | None,
    theme: ThemeManager,
    glyph: str = "album",
) -> None:
    """Draw artwork (or a quiet placeholder) clipped to the theme's cover radius."""
    radius = theme.cover_radius(rect.width())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setClipPath(rounded_path(rect, radius))
    if pixmap is not None and not pixmap.isNull():
        painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
    elif glyph == "shuffle":
        painter.fillRect(rect, theme.color("placeholder"))
        tint = theme.color("accent")
        tint.setAlphaF(0.16)
        painter.fillRect(rect, tint)
        side = rect.width() * 0.34
        paint_icon(
            painter,
            "shuffle",
            QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side),
            theme.color("accent"),
            stroke=1.6,
        )
    else:
        painter.fillRect(rect, theme.color("placeholder"))
        side = rect.width() * 0.32
        paint_icon(
            painter,
            glyph,
            QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side),
            theme.color("placeholder_glyph"),
            stroke=1.4,
        )
    painter.restore()
