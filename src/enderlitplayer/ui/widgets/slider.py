"""Custom-painted horizontal slider used for seeking and volume."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from enderlitplayer.ui.styles.theme import ThemeManager

GROOVE = 4.0
GROOVE_HOVER = 5.0
HANDLE = 12.0


class SeekSlider(QWidget):
    """Click anywhere to jump, drag to scrub.

    * ``moved`` fires continuously while dragging.
    * ``committed`` fires on release (or continuously when ``live`` is True).
    External ``set_value`` calls are ignored while the user is dragging.
    """

    moved = Signal(int)
    committed = Signal(int)

    def __init__(
        self, theme: ThemeManager, *, live: bool = False, step: int = 5, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._live = live
        self._step = step
        self._maximum = 0
        self._value = 0
        self._dragging = False
        self._hovered = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(18)
        theme.themeChanged.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(160, 18)

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def maximum(self) -> int:
        return self._maximum

    def value(self) -> int:
        return self._value

    def set_maximum(self, maximum: int) -> None:
        self._maximum = max(0, int(maximum))
        self._value = min(self._value, self._maximum)
        self.setEnabled(self._maximum > 0)
        self.update()

    def set_value(self, value: int) -> None:
        if self._dragging:
            return
        value = max(0, min(self._maximum, int(value)))
        if value != self._value:
            self._value = value
            self.update()

    def _track_rect(self) -> QRectF:
        pad = HANDLE / 2
        return QRectF(pad, 0, max(1.0, self.width() - HANDLE), self.height())

    def _value_at(self, x: float) -> int:
        track = self._track_rect()
        ratio = (x - track.left()) / track.width()
        return round(max(0.0, min(1.0, ratio)) * self._maximum)

    def _update_from_mouse(self, event: QMouseEvent) -> None:
        self._value = self._value_at(event.position().x())
        self.update()
        self.moved.emit(self._value)
        if self._live:
            self.committed.emit(self._value)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._maximum > 0:
            self._dragging = True
            self._update_from_mouse(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._update_from_mouse(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._update_from_mouse(event)
            if not self._live:
                self.committed.emit(self._value)
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._maximum <= 0:
            return
        delta = self._step if event.angleDelta().y() > 0 else -self._step
        self._value = max(0, min(self._maximum, self._value + delta))
        self.update()
        self.moved.emit(self._value)
        self.committed.emit(self._value)
        event.accept()

    def enterEvent(self, event: QEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        active = (self._hovered or self._dragging) and self.isEnabled()
        groove_h = GROOVE_HOVER if active else GROOVE
        track = self._track_rect()
        y = (self.height() - groove_h) / 2
        groove = QRectF(track.left(), y, track.width(), groove_h)
        painter.setBrush(self._theme.color("border_strong"))
        painter.drawRoundedRect(groove, groove_h / 2, groove_h / 2)
        if self._maximum > 0:
            ratio = self._value / self._maximum
            filled = QRectF(groove.left(), y, groove.width() * ratio, groove_h)
            painter.setBrush(self._theme.color("accent" if active else "text_secondary"))
            painter.drawRoundedRect(filled, groove_h / 2, groove_h / 2)
            if active:
                cx = groove.left() + groove.width() * ratio
                painter.setBrush(self._theme.color("text"))
                painter.drawEllipse(QRectF(cx - HANDLE / 2, (self.height() - HANDLE) / 2, HANDLE, HANDLE))
