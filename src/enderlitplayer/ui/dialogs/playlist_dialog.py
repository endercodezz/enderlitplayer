"""Create/edit playlist dialog (name and optional custom cover image)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from enderlitplayer.i18n.translator import Translator
from enderlitplayer.services.covers import CoverSource, load_square_image
from enderlitplayer.ui.dialogs.base import Dialog
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Space
from enderlitplayer.ui.widgets.controls import Button
from enderlitplayer.ui.widgets.cover_view import CoverView

PREVIEW = 104


def choose_image(parent: QWidget, translator: Translator, start: str = "") -> str:
    start_dir = str(Path(start).parent) if start and Path(start).exists() else str(Path.home())
    path, _ = QFileDialog.getOpenFileName(
        parent,
        translator.t("choose_image_title"),
        start_dir,
        f"{translator.t('images_filter')} (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;"
        f"{translator.t('all_files_filter')} (*)",
    )
    return path or ""


class PlaylistDialog(Dialog):
    def __init__(
        self,
        theme: ThemeManager,
        translator: Translator,
        *,
        title: str,
        accept_text: str,
        name: str = "",
        icon_path: str = "",
        fallback_cover: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, theme, translator, parent)
        self._icon_path = icon_path
        self._fallback = fallback_cover

        row = QHBoxLayout()
        row.setSpacing(Space.L + 4)
        self._preview = CoverView(theme, PREVIEW, parent=self)
        row.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignTop)

        fields = QVBoxLayout()
        fields.setSpacing(Space.XS + 2)
        fields.addWidget(self.field_label(translator.t("playlist_name")))
        self.name_edit = QLineEdit(name, self)
        self.name_edit.setPlaceholderText(translator.t("playlist_name_placeholder"))
        fields.addWidget(self.name_edit)
        fields.addSpacing(Space.S)
        fields.addWidget(self.field_label(translator.t("playlist_cover")))
        buttons = QHBoxLayout()
        buttons.setSpacing(Space.S)
        self._choose = Button(translator.t("choose_image"), theme, icon_name="image", parent=self)
        self._choose.clicked.connect(self._on_choose)
        self._remove = Button(translator.t("remove_image"), theme, kind="GhostButton", parent=self)
        self._remove.clicked.connect(self._on_remove)
        buttons.addWidget(self._choose)
        buttons.addWidget(self._remove)
        buttons.addStretch(1)
        fields.addLayout(buttons)
        hint = QLabel(translator.t("cover_auto_hint"), self)
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        fields.addWidget(hint)
        self._error = QLabel(self)
        self._error.setObjectName("ErrorLabel")
        self._error.hide()
        fields.addWidget(self._error)
        row.addLayout(fields, 1)
        self.body.addLayout(row)

        self.add_action(translator.t("cancel"), "GhostButton", reject=True)
        self._ok = self.add_action(accept_text, "PrimaryButton")
        self._ok.setDefault(True)
        self._ok.clicked.connect(self._on_accept)
        self.name_edit.returnPressed.connect(self._on_accept)
        self._refresh_preview()
        self.name_edit.setFocus()

    @property
    def name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def icon_path(self) -> str:
        return self._icon_path

    def _refresh_preview(self) -> None:
        pixmap = self._fallback
        if self._icon_path:
            image = load_square_image(CoverSource("preview", path=self._icon_path), PREVIEW * 2)
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
        self._preview.set_cover(pixmap, "playlist")
        self._remove.setVisible(bool(self._icon_path))

    def _on_choose(self) -> None:
        path = choose_image(self, self.tr_, self._icon_path)
        if path:
            self._icon_path = path
            self._refresh_preview()

    def _on_remove(self) -> None:
        self._icon_path = ""
        self._refresh_preview()

    def _on_accept(self) -> None:
        if not self.name:
            self._error.setText(self.tr_.t("playlist_name_required"))
            self._error.show()
            self.name_edit.setProperty("invalid", "true")
            self.name_edit.style().unpolish(self.name_edit)
            self.name_edit.style().polish(self.name_edit)
            self.name_edit.setFocus()
            return
        self.accept()
