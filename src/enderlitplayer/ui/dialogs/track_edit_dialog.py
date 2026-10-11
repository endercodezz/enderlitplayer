"""Metadata editor for a single track: number, title, artist and file name."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget

from enderlitplayer.core.models import Track
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.library.editing import EditError, TrackEdit, TrackEditError, parse_track_number
from enderlitplayer.ui.dialogs.base import Dialog
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Space

SaveHandler = Callable[[TrackEdit], EditError | None]


class TrackEditDialog(Dialog):
    """Calls ``on_save``; closes on success, otherwise shows the error inline."""

    def __init__(
        self,
        theme: ThemeManager,
        translator: Translator,
        track: Track,
        number: int,
        on_save: SaveHandler,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(translator.t("edit_track_title"), theme, translator, parent)
        self.setMinimumWidth(520)
        self._on_save = on_save
        grid = QGridLayout()
        grid.setHorizontalSpacing(Space.M)
        grid.setVerticalSpacing(Space.XS + 2)

        self.number_edit = QLineEdit(str(number) if number else "", self)
        self.number_edit.setValidator(QIntValidator(0, 9999, self))
        self.number_edit.setMaximumWidth(96)
        self.title_edit = QLineEdit(track.title, self)
        self.artist_edit = QLineEdit(track.artist, self)
        self.file_edit = QLineEdit(Path(track.path).name, self)

        grid.addWidget(self.field_label(translator.t("field_number")), 0, 0)
        grid.addWidget(self.field_label(translator.t("field_title")), 0, 1)
        grid.addWidget(self.number_edit, 1, 0)
        grid.addWidget(self.title_edit, 1, 1)
        grid.addWidget(self.field_label(translator.t("field_artist")), 2, 0, 1, 2)
        grid.addWidget(self.artist_edit, 3, 0, 1, 2)
        grid.addWidget(self.field_label(translator.t("field_file_name")), 4, 0, 1, 2)
        grid.addWidget(self.file_edit, 5, 0, 1, 2)
        grid.setRowMinimumHeight(2, 26)
        grid.setRowMinimumHeight(4, 26)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        hint = QLabel(translator.t("file_name_hint", ext=Path(track.path).suffix.lower()), self)
        hint.setObjectName("HintLabel")
        self.body.addWidget(hint)
        self.error = QLabel(self)
        self.error.setObjectName("ErrorLabel")
        self.error.setWordWrap(True)
        self.error.hide()
        self.body.addWidget(self.error)

        self.add_action(translator.t("cancel"), "GhostButton", reject=True)
        save = self.add_action(translator.t("save"), "PrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self.submit)
        for edit in (self.number_edit, self.title_edit, self.artist_edit, self.file_edit):
            edit.returnPressed.connect(self.submit)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.submit)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _show_error(self, code: EditError) -> None:
        self.error.setText(self.tr_.t(f"err_{code.value}"))
        self.error.show()

    def submit(self) -> None:
        try:
            number = parse_track_number(self.number_edit.text())
        except TrackEditError as exc:
            self._show_error(exc.code)
            return
        edit = TrackEdit(
            title=self.title_edit.text(),
            artist=self.artist_edit.text(),
            file_name=self.file_edit.text(),
            track_no=number,
        )
        error = self._on_save(edit)
        if error is None:
            self.accept()
        else:
            self._show_error(error)
