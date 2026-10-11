"""Common dialog chrome and simple confirmation dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Space
from enderlitplayer.ui.widgets.controls import Button


class Dialog(QDialog):
    """Dialog with a heading, a body area and a right-aligned action row."""

    def __init__(self, title: str, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.tr_ = translator
        self.setObjectName("Dialog")
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setModal(True)
        self.setMinimumWidth(440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.XL, Space.XL, Space.XL, Space.L + 4)
        outer.setSpacing(Space.L)
        self.heading = QLabel(title, self)
        self.heading.setObjectName("EmptyTitle")
        self.heading.setWordWrap(True)
        outer.addWidget(self.heading)
        self.body = QVBoxLayout()
        self.body.setSpacing(Space.M)
        outer.addLayout(self.body, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(Space.S)
        self.actions.addStretch(1)
        outer.addSpacing(Space.XS)
        outer.addLayout(self.actions)

    def add_action(
        self, text: str, kind: str = "SecondaryButton", *, accept: bool = False, reject: bool = False
    ) -> Button:
        button = Button(text, self.theme, kind=kind, parent=self)
        if accept:
            button.clicked.connect(self.accept)
            button.setDefault(True)
        if reject:
            button.clicked.connect(self.reject)
        self.actions.addWidget(button)
        return button

    def field_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("FieldLabel")
        return label


def confirm(
    parent: QWidget,
    theme: ThemeManager,
    translator: Translator,
    title: str,
    body: str,
    confirm_text: str,
    *,
    destructive: bool = False,
) -> bool:
    dialog = Dialog(title, theme, translator, parent)
    text = QLabel(body, dialog)
    text.setObjectName("EmptyBody")
    text.setWordWrap(True)
    dialog.body.addWidget(text)
    dialog.add_action(translator.t("cancel"), "GhostButton", reject=True)
    dialog.add_action(confirm_text, "DangerButton" if destructive else "PrimaryButton", accept=True)
    return dialog.exec() == QDialog.DialogCode.Accepted


def inform(parent: QWidget, theme: ThemeManager, translator: Translator, title: str, body: str) -> None:
    dialog = Dialog(title, theme, translator, parent)
    text = QLabel(body, dialog)
    text.setObjectName("EmptyBody")
    text.setWordWrap(True)
    dialog.body.addWidget(text)
    dialog.add_action(translator.t("ok"), "PrimaryButton", accept=True)
    dialog.exec()
