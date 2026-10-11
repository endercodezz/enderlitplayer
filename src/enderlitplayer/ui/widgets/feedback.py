"""Empty states and transient notifications."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from enderlitplayer.ui.assets.icons import paint_icon
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Space
from enderlitplayer.ui.widgets.controls import Button


class _Glyph(QWidget):
    def __init__(self, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._name = "album"
        self.setFixedSize(64, 64)
        theme.themeChanged.connect(self.update)

    def set_name(self, name: str) -> None:
        self._name = name
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._theme.color("surface_alt"))
        painter.drawEllipse(QRectF(0, 0, 64, 64))
        paint_icon(painter, self._name, QRectF(20, 20, 24, 24), self._theme.color("text_secondary"))


class EmptyState(QWidget):
    """Centered icon, title, explanation and an optional call to action."""

    actionTriggered = Signal()

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.XL, Space.XXXL, Space.XL, Space.XXXL)
        layout.setSpacing(Space.S)
        layout.addStretch(2)
        self._glyph = _Glyph(theme, self)
        layout.addWidget(self._glyph, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(Space.S)
        self._title = QLabel(self)
        self._title.setObjectName("EmptyTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setFixedWidth(420)
        layout.addWidget(self._title, 0, Qt.AlignmentFlag.AlignHCenter)
        self._body = QLabel(self)
        self._body.setObjectName("EmptyBody")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        # A fixed width lets QLabel compute its wrapped height correctly.
        self._body.setFixedWidth(420)
        layout.addWidget(self._body, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(Space.M)
        self._button = Button("", theme, kind="PrimaryButton", parent=self)
        self._button.clicked.connect(self.actionTriggered)
        layout.addWidget(self._button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(3)

    def set_content(
        self,
        icon: str,
        title: str,
        body: str = "",
        action: str | None = None,
        action_icon: str | None = None,
    ) -> None:
        self._glyph.set_name(icon)
        self._title.setText(title)
        self._body.setText(body)
        # QStackedWidget does not propagate height-for-width, so size wrapped labels explicitly.
        for label in (self._title, self._body):
            label.ensurePolished()
            rect = label.fontMetrics().boundingRect(
                QRect(0, 0, label.width(), 10_000), int(Qt.TextFlag.TextWordWrap), label.text()
            )
            label.setMinimumHeight(rect.height() + 2)
        self._body.setVisible(bool(body))
        self._button.setVisible(bool(action))
        if action:
            self._button.setText(action)
            self._button.set_icon_name(action_icon)


class Toast(QWidget):
    """Short message shown at the bottom of the content area."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Space.L, Space.S + 2, Space.L, Space.S + 2)
        self._label = QLabel(self)
        self._label.setObjectName("ToastLabel")
        layout.addWidget(self._label)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, duration_ms: int = 3200) -> None:
        self._label.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(duration_ms)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        hint: QSize = self.sizeHint()
        width = min(hint.width(), parent.width() - 2 * Space.XL)
        self.resize(width, hint.height())
        self.move((parent.width() - width) // 2, parent.height() - hint.height() - Space.XL)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()
