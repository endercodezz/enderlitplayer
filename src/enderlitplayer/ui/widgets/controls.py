"""Small reusable controls: themed icon buttons, search field, segmented control, labels."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeyEvent, QPainter, QPalette
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from enderlitplayer.ui.assets.icons import make_icon
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size


class IconButton(QToolButton):
    """Borderless icon button whose glyph color follows theme and hover state."""

    def __init__(
        self,
        icon_name: str,
        theme: ThemeManager,
        *,
        size: int = 32,
        icon_size: int = Size.ICON,
        tooltip: str = "",
        color: str = "text_secondary",
        hover_color: str = "text",
        object_name: str = "IconButton",
        checkable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_name = icon_name
        self._color = color
        self._hover_color = hover_color
        self._icon_size = icon_size
        self.setObjectName(object_name)
        self.setCheckable(checkable)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        theme.themeChanged.connect(self.refresh)
        self.toggled.connect(lambda _checked: self.refresh())
        self.refresh()

    def set_icon_name(self, name: str) -> None:
        if name != self._icon_name:
            self._icon_name = name
            self.refresh()

    def set_colors(self, color: str, hover_color: str | None = None) -> None:
        self._color = color
        self._hover_color = hover_color or color
        self.refresh()

    def set_tooltip(self, text: str) -> None:
        self.setToolTip(text)
        self.setAccessibleName(text)

    def refresh(self) -> None:
        if not self.isEnabled():
            token = "text_tertiary"
        elif self.isCheckable() and self.isChecked():
            token = "accent"
        elif self.underMouse():
            token = self._hover_color
        else:
            token = self._color
        self.setIcon(make_icon(self._icon_name, self._theme.color(token), self._icon_size))

    def enterEvent(self, event: QEvent) -> None:
        super().enterEvent(event)
        self.refresh()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.refresh()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.refresh()


class Button(QPushButton):
    """Text button with an optional themed leading icon. ``kind`` selects the style."""

    _ICON_COLORS = {
        "PrimaryButton": "on_accent",
        "DangerButton": "on_accent",
        "GhostButton": "text_secondary",
        "SecondaryButton": "text",
    }

    def __init__(
        self,
        text: str,
        theme: ThemeManager,
        *,
        kind: str = "SecondaryButton",
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._theme = theme
        self._icon_name = icon_name
        self.setObjectName(kind)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        theme.themeChanged.connect(self.refresh)
        self.toggled.connect(lambda _checked: self.refresh())
        self.refresh()

    def set_icon_name(self, name: str | None) -> None:
        self._icon_name = name
        self.refresh()

    def refresh(self) -> None:
        if not self._icon_name:
            self.setIcon(QIcon())
            return
        if self.isChecked():
            token = "accent"
        elif not self.isEnabled():
            token = "text_tertiary"
        else:
            token = self._ICON_COLORS.get(self.objectName(), "text")
        self.setIcon(make_icon(self._icon_name, self._theme.color(token), Size.ICON_SMALL))
        self.setIconSize(QSize(Size.ICON_SMALL, Size.ICON_SMALL))

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.refresh()


class SearchField(QLineEdit):
    """Rounded search input with a leading glyph. Esc clears text before bubbling up."""

    def __init__(self, theme: ThemeManager, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("SearchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self._search_action = self.addAction(
            make_icon("search", theme.color("text_tertiary"), Size.ICON_SMALL),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.setMinimumWidth(160)
        self.setMaximumWidth(Size.SEARCH_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.themeChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self._search_action.setIcon(make_icon("search", self._theme.color("text_tertiary"), Size.ICON_SMALL))
        clear = self.findChild(QAction, "_q_qlineeditclearaction")
        if clear is not None:
            clear.setIcon(make_icon("close", self._theme.color("text_secondary"), Size.ICON_SMALL))

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Escape and self.text():
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            return
        super().keyPressEvent(event)


class SegmentedControl(QFrame):
    """Mutually exclusive options rendered as a compact pill group."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for value, label in options:
            button = QPushButton(label, self)
            button.setObjectName("SegmentButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, v=value: self._on_clicked(v))
            self._group.addButton(button)
            self._buttons[value] = button
            layout.addWidget(button)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _on_clicked(self, value: str) -> None:
        self.changed.emit(value)

    def set_value(self, value: str) -> None:
        button = self._buttons.get(value)
        if button is not None:
            button.setChecked(True)

    def value(self) -> str:
        return next((value for value, button in self._buttons.items() if button.isChecked()), "")

    def set_labels(self, labels: dict[str, str]) -> None:
        for value, text in labels.items():
            if value in self._buttons:
                self._buttons[value].setText(text)


class ElidedLabel(QLabel):
    """Single-line label that elides with "…" instead of growing or clipping."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(24)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text or ""
        super().setText(self._full_text)
        self.setToolTip(self._full_text if self._is_elided() else "")
        self.update()

    def full_text(self) -> str:
        return self._full_text

    def _is_elided(self) -> bool:
        return self.fontMetrics().horizontalAdvance(self._full_text) > self.width()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self.setToolTip(self._full_text if self._is_elided() else "")

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(24, hint.height())

    def paintEvent(self, event: QEvent) -> None:
        painter = QPainter(self)
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, rect.width())
        self.style().drawItemText(
            painter,
            rect,
            int(self.alignment()) | int(Qt.AlignmentFlag.AlignVCenter),
            self.palette(),
            self.isEnabled(),
            elided,
            QPalette.ColorRole.WindowText,
        )


def h_line(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("CardDivider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line
