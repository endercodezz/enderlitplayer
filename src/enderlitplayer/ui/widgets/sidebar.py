"""Primary navigation sidebar."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.assets.artwork import build_icon_image
from enderlitplayer.ui.assets.icons import make_icon
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size, Space
from enderlitplayer.ui.widgets.controls import ElidedLabel

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("songs", "songs", "nav_songs"),
    ("albums", "album", "nav_albums"),
    ("playlists", "playlist", "nav_playlists"),
    ("mix", "shuffle", "nav_mix"),
)
SETTINGS_KEY = "settings"


class NavButton(QPushButton):
    def __init__(self, key: str, icon_name: str, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._icon_name = icon_name
        self._theme = theme
        self._label = ""
        self._compact = False
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(Size.ICON, Size.ICON))
        theme.themeChanged.connect(self.refresh)
        self.toggled.connect(lambda _checked: self.refresh())
        self.refresh()

    def set_label(self, text: str) -> None:
        self._label = text
        self.setToolTip(text if self._compact else "")
        self.setAccessibleName(text)
        self.setText("" if self._compact else f"  {text}")

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setProperty("compact", "true" if compact else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.set_label(self._label)

    def refresh(self) -> None:
        if self.isChecked():
            token = "accent"
        elif self.underMouse():
            token = "text"
        else:
            token = "text_secondary"
        self.setIcon(make_icon(self._icon_name, self._theme.color(token), Size.ICON))

    def enterEvent(self, event: QEvent) -> None:
        super().enterEvent(event)
        self.refresh()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.refresh()


class _Logo(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self._image = build_icon_image(112)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRectF(0, 0, 28, 28), self._image)


class Sidebar(QFrame):
    pageRequested = Signal(str)

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = translator
        self._theme = theme
        self._compact = False
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.M, Space.XL - 4, Space.M, Space.L)
        layout.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(Space.S, 0, 0, 0)
        brand.setSpacing(Space.S + 2)
        brand.addWidget(_Logo(self))
        self._brand = QLabel("Enderlit", self)
        self._brand.setObjectName("BrandLabel")
        brand.addWidget(self._brand, 1)
        layout.addLayout(brand)
        layout.addSpacing(Space.XL)

        self._section = QLabel(self)
        self._section.setObjectName("NavSection")
        layout.addWidget(self._section)
        layout.addSpacing(Space.XS)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, NavButton] = {}
        for key, icon, _label_key in NAV_ITEMS:
            button = self._add_button(key, icon)
            layout.addWidget(button)

        layout.addStretch(1)
        self._status = ElidedLabel("", self)
        self._status.setObjectName("SidebarStatus")
        self._status.hide()
        layout.addWidget(self._status)
        layout.addSpacing(Space.S)
        layout.addWidget(self._add_button(SETTINGS_KEY, "settings"))

        translator.languageChanged.connect(self.retranslate)
        self.retranslate()
        self.set_compact(False)

    def _add_button(self, key: str, icon: str) -> NavButton:
        button = NavButton(key, icon, self._theme, self)
        button.clicked.connect(lambda _checked=False, k=key: self.pageRequested.emit(k))
        self._group.addButton(button)
        self._buttons[key] = button
        return button

    def retranslate(self) -> None:
        self._section.setText(self._tr.t("nav_section_library").upper())
        for key, _icon, label_key in NAV_ITEMS:
            self._buttons[key].set_label(self._tr.t(label_key))
        self._buttons[SETTINGS_KEY].set_label(self._tr.t("nav_settings"))

    def set_current(self, key: str | None) -> None:
        button = self._buttons.get(key or "")
        if button is not None:
            button.setChecked(True)
        else:
            checked = self._group.checkedButton()
            if checked is not None:
                self._group.setExclusive(False)
                checked.setChecked(False)
                self._group.setExclusive(True)

    def set_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.setVisible(bool(text) and not self._compact)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedWidth(Size.SIDEBAR_COMPACT if compact else Size.SIDEBAR)
        self._brand.setVisible(not compact)
        self._section.setVisible(not compact)
        self._status.setVisible(bool(self._status.full_text()) and not compact)
        for button in self._buttons.values():
            button.set_compact(compact)

    @property
    def compact(self) -> bool:
        return self._compact
