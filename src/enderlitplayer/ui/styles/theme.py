"""Theme state shared by widgets that paint themselves."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from enderlitplayer.ui.styles.stylesheet import build_stylesheet
from enderlitplayer.ui.styles.tokens import PALETTES, Palette, cover_radius


def qcolor(value: str) -> QColor:
    """Parse ``#rrggbb`` or ``rgba(r, g, b, a)`` (a in 0..1) token values."""
    value = value.strip()
    if value.startswith("rgba"):
        parts = [p.strip() for p in value[value.index("(") + 1 : value.index(")")].split(",")]
        color = QColor(int(parts[0]), int(parts[1]), int(parts[2]))
        color.setAlphaF(float(parts[3]))
        return color
    return QColor(value)


class ThemeManager(QObject):
    themeChanged = Signal()
    coverStyleChanged = Signal()

    def __init__(self, mode: str = "dark", cover_style: str = "rounded", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode = mode if mode in PALETTES else "dark"
        self._cover_style = cover_style
        self._colors: dict[str, QColor] = {}
        self._rebuild_colors()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def palette(self) -> Palette:
        return PALETTES[self._mode]

    @property
    def cover_style(self) -> str:
        return self._cover_style

    def color(self, token: str) -> QColor:
        return QColor(self._colors[token])

    def cover_radius(self, size: float) -> float:
        return cover_radius(self._cover_style, size)

    def _rebuild_colors(self) -> None:
        palette = self.palette
        self._colors = {name: qcolor(getattr(palette, name)) for name in palette.__dataclass_fields__ if name != "name"}

    def apply(self, app: QApplication | None = None) -> None:
        app = app or QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self.palette))

    def set_mode(self, mode: str) -> None:
        if mode in PALETTES and mode != self._mode:
            self._mode = mode
            self._rebuild_colors()
            self.apply()
            self.themeChanged.emit()

    def set_cover_style(self, style: str) -> None:
        if style != self._cover_style:
            self._cover_style = style
            self.coverStyleChanged.emit()
