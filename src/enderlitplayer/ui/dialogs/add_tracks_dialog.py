"""Pick tracks from the whole library to add to a playlist."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from enderlitplayer.core.models import Track
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.dialogs.base import Dialog
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.widgets.controls import SearchField

PATH_ROLE = Qt.ItemDataRole.UserRole


class AddTracksDialog(Dialog):
    def __init__(
        self,
        theme: ThemeManager,
        translator: Translator,
        playlist_title: str,
        tracks: list[tuple[Track, str]],
        existing_paths: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(translator.t("select_tracks_title", name=playlist_title), theme, translator, parent)
        self.setMinimumSize(560, 520)
        self.search = SearchField(theme, translator.t("search_tracks"), self)
        self.search.setMaximumWidth(16777215)
        self.body.addWidget(self.search)
        self.list = QListWidget(self)
        self.list.setObjectName("PickList")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        added_suffix = translator.t("already_added")
        ordered = sorted(tracks, key=lambda item: (item[0].artist.casefold(), item[0].title.casefold()))
        for track, album_title in ordered:
            artist = translator.artist(track.artist)
            item = QListWidgetItem(f"{track.title}  ·  {artist}  ·  {album_title}")
            item.setData(PATH_ROLE, track.path)
            item.setToolTip(track.path)
            if track.path in existing_paths:
                item.setText(f"{item.text()}  —  {added_suffix}")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.body.addWidget(self.list, 1)
        self.list.itemChanged.connect(self._update_button)
        self.list.itemClicked.connect(self._toggle_item)
        self.search.textChanged.connect(self._filter)

        self.add_action(translator.t("cancel"), "GhostButton", reject=True)
        self._add = self.add_action(translator.t("add_selected"), "PrimaryButton", accept=True)
        self._update_button()
        self.search.setFocus()

    def _toggle_item(self, item: QListWidgetItem) -> None:
        if not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return
        # Clicking anywhere on the row toggles it, not only the tiny indicator.
        if self.list.viewport().mapFromGlobal(self.cursor().pos()).x() > 28:
            checked = item.checkState() == Qt.CheckState.Checked
            item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

    def _filter(self, text: str) -> None:
        query = text.strip().casefold()
        for index in range(self.list.count()):
            item = self.list.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())

    def selected_paths(self) -> list[str]:
        paths = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState() == Qt.CheckState.Checked:
                paths.append(str(item.data(PATH_ROLE)))
        return paths

    def _update_button(self, *_args: object) -> None:
        count = len(self.selected_paths())
        self._add.setEnabled(count > 0)
        self._add.setText(self.tr_.t("add_selected_count", count=count) if count else self.tr_.t("add_selected"))
