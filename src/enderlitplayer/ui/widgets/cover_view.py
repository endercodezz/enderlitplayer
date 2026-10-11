"""A square artwork widget with theme-aware placeholder and corner style."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QWidget

from enderlitplayer.ui.assets.artwork import paint_cover
from enderlitplayer.ui.styles.theme import ThemeManager


class CoverView(QWidget):
    clicked = Signal()

    def __init__(
        self, theme: ThemeManager, size: int, *, clickable: bool = False, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._pixmap: QPixmap | None = None
        self._glyph = "album"
        self._clickable = clickable
        self.set_side(size)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.themeChanged.connect(self.update)
        theme.coverStyleChanged.connect(self.update)

    def set_side(self, size: int) -> None:
        self.setFixedSize(QSize(size, size))
        self.update()

    def set_cover(self, pixmap: QPixmap | None, glyph: str = "album") -> None:
        self._pixmap = pixmap
        self._glyph = glyph
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._clickable
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        paint_cover(painter, QRectF(self.rect()), self._pixmap, self._theme, self._glyph)
