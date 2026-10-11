"""Vector icon set drawn with QPainter on a 24×24 grid.

Icons are rendered on demand in any color and size, so they stay crisp on
high-DPI screens and follow the active theme without image files.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

STROKE = 1.8

Drawer = Callable[[QPainter], None]


def _pen(painter: QPainter, width: float = STROKE) -> None:
    pen = QPen(painter.brush().color(), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _fill(painter: QPainter, color: QColor) -> None:
    pen = QPen(color, 1.6)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QBrush(color))


def _poly(*points: tuple[float, float], close: bool = False) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    if close:
        path.closeSubpath()
    return path


def _play(p: QPainter, c: QColor) -> None:
    _fill(p, c)
    p.drawPath(_poly((8.5, 5.5), (18.5, 12), (8.5, 18.5), close=True))


def _pause(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(6.5, 5, 4, 14), 1.3, 1.3)
    p.drawRoundedRect(QRectF(13.5, 5, 4, 14), 1.3, 1.3)


def _previous(p: QPainter, c: QColor) -> None:
    _fill(p, c)
    p.drawPath(_poly((18, 6.5), (9.5, 12), (18, 17.5), close=True))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(5.5, 6, 2.4, 12), 1.1, 1.1)


def _next(p: QPainter, c: QColor) -> None:
    _fill(p, c)
    p.drawPath(_poly((6, 6.5), (14.5, 12), (6, 17.5), close=True))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(16.1, 6, 2.4, 12), 1.1, 1.1)


def _speaker(p: QPainter) -> None:
    p.drawPath(_poly((4, 9.5), (7.5, 9.5), (12, 5.5), (12, 18.5), (7.5, 14.5), (4, 14.5), close=True))


def _volume(p: QPainter, c: QColor) -> None:
    _speaker(p)
    p.drawArc(QRectF(10, 8, 8, 8), -50 * 16, 100 * 16)
    p.drawArc(QRectF(8.5, 4.5, 14, 15), -55 * 16, 110 * 16)


def _volume_low(p: QPainter, c: QColor) -> None:
    _speaker(p)
    p.drawArc(QRectF(10, 8, 8, 8), -50 * 16, 100 * 16)


def _volume_mute(p: QPainter, c: QColor) -> None:
    _speaker(p)
    p.drawLine(QPointF(16, 9.5), QPointF(21, 14.5))
    p.drawLine(QPointF(21, 9.5), QPointF(16, 14.5))


def _search(p: QPainter, c: QColor) -> None:
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20, 20))


def _songs(p: QPainter, c: QColor) -> None:
    p.drawPath(_poly((9, 17), (9, 5.5), (19, 3.5), (19, 15)))
    p.drawEllipse(QPointF(6.5, 17), 2.5, 2.5)
    p.drawEllipse(QPointF(16.5, 15), 2.5, 2.5)


def _album(p: QPainter, c: QColor) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawEllipse(QPointF(12, 12), 2.6, 2.6)


def _playlist(p: QPainter, c: QColor) -> None:
    p.drawLine(QPointF(3.5, 6), QPointF(14.5, 6))
    p.drawLine(QPointF(3.5, 11), QPointF(14.5, 11))
    p.drawLine(QPointF(3.5, 16), QPointF(10, 16))
    p.drawPath(_poly((18.5, 17), (18.5, 6), (21.5, 7)))
    p.drawEllipse(QPointF(16.2, 17.2), 2.3, 2.3)


def _shuffle(p: QPainter, c: QColor) -> None:
    path = QPainterPath(QPointF(3, 17.5))
    path.lineTo(4.5, 17.5)
    path.cubicTo(7.5, 17.5, 9.5, 16, 11, 13.5)
    path.lineTo(13, 10.5)
    path.cubicTo(14.5, 8, 16.5, 6.5, 19.5, 6.5)
    path.lineTo(21, 6.5)
    p.drawPath(path)
    upper = QPainterPath(QPointF(3, 6.5))
    upper.lineTo(4.5, 6.5)
    upper.cubicTo(6.8, 6.5, 8.4, 7.4, 9.6, 8.9)
    p.drawPath(upper)
    lower = QPainterPath(QPointF(21, 17.5))
    lower.lineTo(19.5, 17.5)
    lower.cubicTo(17.2, 17.5, 15.6, 16.6, 14.4, 15.1)
    p.drawPath(lower)
    p.drawPath(_poly((18, 3.5), (21, 6.5), (18, 9.5)))
    p.drawPath(_poly((18, 14.5), (21, 17.5), (18, 20.5)))


def _settings(p: QPainter, c: QColor) -> None:
    teeth = 8
    outer, inner = 9.3, 7.0
    path = QPainterPath()
    for i in range(teeth * 4):
        angle = (i / (teeth * 4)) * 2 * math.pi - math.pi / 2
        radius = outer if (i % 4) in (1, 2) else inner
        point = QPointF(12 + radius * math.cos(angle), 12 + radius * math.sin(angle))
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QPointF(12, 12), 3, 3)


def _plus(p: QPainter, c: QColor) -> None:
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _trash(p: QPainter, c: QColor) -> None:
    p.drawLine(QPointF(4, 7), QPointF(20, 7))
    p.drawPath(_poly((9, 7), (9, 4.5), (15, 4.5), (15, 7)))
    p.drawPath(_poly((6, 7), (7, 20), (17, 20), (18, 7)))
    p.drawLine(QPointF(10, 11), QPointF(10, 16))
    p.drawLine(QPointF(14, 11), QPointF(14, 16))


def _pencil(p: QPainter, c: QColor) -> None:
    p.drawPath(_poly((4.5, 19.5), (5.2, 15.8), (15.8, 5.2), (18.8, 8.2), (8.2, 18.8), close=True))
    p.drawLine(QPointF(13.6, 7.4), QPointF(16.6, 10.4))


def _image(p: QPainter, c: QColor) -> None:
    p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2.5, 2.5)
    p.drawEllipse(QPointF(9, 9.8), 1.7, 1.7)
    p.drawPath(_poly((4, 17), (9.5, 12.5), (13, 15.5), (16, 13), (20, 16.5)))


def _arrow_left(p: QPainter, c: QColor) -> None:
    p.drawLine(QPointF(19, 12), QPointF(5, 12))
    p.drawPath(_poly((11, 6), (5, 12), (11, 18)))


def _chevron_up(p: QPainter, c: QColor) -> None:
    p.drawPath(_poly((6.5, 14.5), (12, 9), (17.5, 14.5)))


def _chevron_down(p: QPainter, c: QColor) -> None:
    p.drawPath(_poly((6.5, 9.5), (12, 15), (17.5, 9.5)))


def _reorder(p: QPainter, c: QColor) -> None:
    p.drawLine(QPointF(8, 19), QPointF(8, 5))
    p.drawPath(_poly((4.5, 8.5), (8, 5), (11.5, 8.5)))
    p.drawLine(QPointF(16, 5), QPointF(16, 19))
    p.drawPath(_poly((12.5, 15.5), (16, 19), (19.5, 15.5)))


def _folder(p: QPainter, c: QColor) -> None:
    path = QPainterPath(QPointF(3.5, 7.5))
    path.quadTo(3.5, 5.5, 5.5, 5.5)
    path.lineTo(9.5, 5.5)
    path.lineTo(11.5, 7.8)
    path.lineTo(18.5, 7.8)
    path.quadTo(20.5, 7.8, 20.5, 9.8)
    path.lineTo(20.5, 17)
    path.quadTo(20.5, 19, 18.5, 19)
    path.lineTo(5.5, 19)
    path.quadTo(3.5, 19, 3.5, 17)
    path.closeSubpath()
    p.drawPath(path)


def _refresh(p: QPainter, c: QColor) -> None:
    p.drawArc(QRectF(4.5, 4.5, 15, 15), 40 * 16, 290 * 16)
    p.drawPath(_poly((19.8, 4.5), (19.2, 9.2), (14.6, 8.4)))


def _more(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    for x in (5.5, 12, 18.5):
        p.drawEllipse(QPointF(x, 12), 1.7, 1.7)


def _check(p: QPainter, c: QColor) -> None:
    p.drawPath(_poly((5, 12.5), (10, 17.5), (19, 7)))


def _close(p: QPainter, c: QColor) -> None:
    p.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
    p.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))


def _logo(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(12, 12), 10, 10)
    p.setBrush(QColor("#0f0f0f"))
    p.drawPath(_poly((10, 8), (10, 16), (16.5, 12), close=True))


_FILLED = {"play", "pause", "previous", "next", "more", "logo"}
_DRAWERS: dict[str, Callable[[QPainter, QColor], None]] = {
    "play": _play,
    "pause": _pause,
    "previous": _previous,
    "next": _next,
    "volume": _volume,
    "volume_low": _volume_low,
    "volume_mute": _volume_mute,
    "search": _search,
    "songs": _songs,
    "album": _album,
    "playlist": _playlist,
    "shuffle": _shuffle,
    "settings": _settings,
    "plus": _plus,
    "trash": _trash,
    "pencil": _pencil,
    "image": _image,
    "arrow_left": _arrow_left,
    "chevron_up": _chevron_up,
    "chevron_down": _chevron_down,
    "reorder": _reorder,
    "folder": _folder,
    "refresh": _refresh,
    "more": _more,
    "check": _check,
    "close": _close,
    "logo": _logo,
}

ICON_NAMES = frozenset(_DRAWERS)


def paint_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, stroke: float = STROKE) -> None:
    """Draw icon ``name`` scaled into ``rect``."""
    drawer = _DRAWERS[name]
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    side = min(rect.width(), rect.height())
    painter.translate(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2)
    painter.scale(side / 24.0, side / 24.0)
    painter.setBrush(QBrush(color))
    if name not in _FILLED:
        _pen(painter, stroke)
    drawer(painter, color)
    painter.restore()


@lru_cache(maxsize=512)
def _icon_cached(name: str, rgba: int, size: int) -> QIcon:
    color = QColor.fromRgba(rgba)
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(scale)
        painter = QPainter(pixmap)
        paint_icon(painter, name, QRectF(0, 0, size, size), color)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def make_icon(name: str, color: QColor, size: int = 20) -> QIcon:
    return _icon_cached(name, color.rgba(), int(size))
