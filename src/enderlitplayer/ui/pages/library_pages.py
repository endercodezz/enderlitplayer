"""Top-level library pages: Songs, Albums and Playlists."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Signal
from PySide6.QtWidgets import QStackedWidget, QWidget

from enderlitplayer.core.models import Album
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.services.covers import CoverProvider
from enderlitplayer.ui.pages.common import Page, TrackListPanel
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.widgets.album_grid import AlbumGridView, GridItem
from enderlitplayer.ui.widgets.controls import Button, SearchField
from enderlitplayer.ui.widgets.feedback import EmptyState
from enderlitplayer.utils.formatting import format_time


class LibraryState:
    """Why a page might have nothing to show."""

    NO_FOLDER = "no_folder"
    SCANNING = "scanning"
    EMPTY = "empty"
    READY = "ready"


def apply_library_empty_state(empty: EmptyState, tr: Translator, state: str) -> None:
    if state == LibraryState.NO_FOLDER:
        empty.set_content(
            "folder", tr.t("empty_no_folder_title"), tr.t("empty_no_folder_body"), tr.t("choose_folder"), "folder"
        )
    elif state == LibraryState.SCANNING:
        empty.set_content("refresh", tr.t("scanning_title"), tr.t("scanning_body"))
    else:
        empty.set_content(
            "songs", tr.t("empty_library_title"), tr.t("empty_library_body"), tr.t("change_folder"), "folder"
        )


class SongsPage(Page):
    """Every track in the library as one playable list."""

    playRequested = Signal(object)
    actionRequested = Signal(object, str)
    contextRequested = Signal(object, QPoint)
    chooseFolderRequested = Signal()

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(theme, translator, parent)
        self._collection: Album | None = None
        self._state = LibraryState.NO_FOLDER
        self.title, self.meta, trailing = self.build_title_row()
        self.search = SearchField(theme, "", self)
        trailing.addWidget(self.search)
        self.panel = TrackListPanel(theme, translator, self)
        self.root.addWidget(self.panel, 1)
        self.panel.playRequested.connect(self.playRequested)
        self.panel.actionRequested.connect(self.actionRequested)
        self.panel.contextRequested.connect(self.contextRequested)
        self.panel.empty.actionTriggered.connect(self.chooseFolderRequested)
        self.search.textChanged.connect(self._on_search)
        self.retranslate()

    @property
    def collection(self) -> Album | None:
        return self._collection

    def search_field(self) -> SearchField:
        return self.search

    def set_state(self, state: str, collection: Album | None) -> None:
        self._state = state
        self._collection = collection
        if collection is not None:
            self.panel.set_tracks(collection.tracks, show_album=True)
        else:
            self.panel.set_tracks([])
        self._refresh()

    def _on_search(self, text: str) -> None:
        self.panel.set_filter(text)
        self._refresh()

    def _refresh(self) -> None:
        tr = self.tr_
        tracks = self._collection.tracks if self._collection else []
        self.search.setVisible(bool(tracks))
        if tracks:
            self.meta.setText(f"{tr.plural('tracks', len(tracks))}  ·  {format_time(sum(t.duration for t in tracks))}")
        else:
            self.meta.setText("")
        if not tracks:
            apply_library_empty_state(self.panel.empty, tr, self._state)
            self.panel.stack.setCurrentWidget(self.panel.empty)
            self.panel.header.hide()
        elif self.panel.visible_count() == 0:
            self.panel.show_empty(
                "search", tr.t("empty_search_title"), tr.t("empty_search_body", query=self.search.text().strip())
            )
        else:
            self.panel.show_list()

    def retranslate(self) -> None:
        self.title.setText(self.tr_.t("nav_songs"))
        self.search.setPlaceholderText(self.tr_.t("search_songs"))
        self._refresh()


class GridPage(Page):
    """Artwork grid with search, empty states and an optional header action."""

    openRequested = Signal(str)
    playRequested = Signal(str)
    contextRequested = Signal(str, QPoint)
    emptyActionRequested = Signal()

    def __init__(
        self,
        theme: ThemeManager,
        translator: Translator,
        covers: CoverProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(theme, translator, parent)
        self._items: list[GridItem] = []
        self._state = LibraryState.NO_FOLDER
        self.title, self.meta, self.trailing = self.build_title_row()
        self.search = SearchField(theme, "", self)
        self.trailing.addWidget(self.search)
        self.stack = QStackedWidget(self)
        self.grid = AlbumGridView(theme, covers, self)
        self.empty = EmptyState(theme, self)
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.empty)
        self.root.addWidget(self.stack, 1)
        # The grid draws its own cell padding; pull it flush with the page title.
        self.root.setContentsMargins(
            self.root.contentsMargins().left() - 6,
            self.root.contentsMargins().top(),
            self.root.contentsMargins().right() - 6,
            0,
        )
        self.root.itemAt(0).layout().setContentsMargins(6, 0, 6, 0)
        self.grid.openRequested.connect(self.openRequested)
        self.grid.playRequested.connect(self.playRequested)
        self.grid.contextRequested.connect(self.contextRequested)
        self.empty.actionTriggered.connect(self.emptyActionRequested)
        self.search.textChanged.connect(lambda _text: self._apply_filter())

    def search_field(self) -> SearchField:
        return self.search

    def set_items(self, items: list[GridItem], state: str = LibraryState.READY) -> None:
        self._items = items
        self._state = state
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search.text().strip().casefold()
        visible = [item for item in self._items if not query or query in f"{item.title} {item.subtitle}".casefold()]
        self.grid.set_items(visible)
        self.search.setVisible(bool(self._items))
        self.meta.setText(self.count_text(len(self._items)) if self._items else "")
        if not self._items:
            self.show_empty_state(self._state)
            self.stack.setCurrentWidget(self.empty)
        elif not visible:
            self.empty.set_content(
                "search",
                self.tr_.t("empty_search_title"),
                self.tr_.t("empty_search_body", query=self.search.text().strip()),
            )
            self.stack.setCurrentWidget(self.empty)
        else:
            self.stack.setCurrentWidget(self.grid)

    def count_text(self, count: int) -> str:
        raise NotImplementedError

    def show_empty_state(self, state: str) -> None:
        raise NotImplementedError

    def retranslate(self) -> None:
        self._apply_filter()


class AlbumsPage(GridPage):
    def __init__(
        self, theme: ThemeManager, translator: Translator, covers: CoverProvider, parent: QWidget | None = None
    ) -> None:
        super().__init__(theme, translator, covers, parent)
        self.retranslate()

    def count_text(self, count: int) -> str:
        return self.tr_.plural("albums", count)

    def show_empty_state(self, state: str) -> None:
        apply_library_empty_state(self.empty, self.tr_, state)

    def retranslate(self) -> None:
        self.title.setText(self.tr_.t("nav_albums"))
        self.search.setPlaceholderText(self.tr_.t("search_albums"))
        super().retranslate()


class PlaylistsPage(GridPage):
    createRequested = Signal()

    def __init__(
        self, theme: ThemeManager, translator: Translator, covers: CoverProvider, parent: QWidget | None = None
    ) -> None:
        super().__init__(theme, translator, covers, parent)
        self.create_button = Button("", theme, kind="PrimaryButton", icon_name="plus", parent=self)
        self.create_button.clicked.connect(self.createRequested)
        self.trailing.addWidget(self.create_button)
        self.emptyActionRequested.connect(self.createRequested)
        self.retranslate()

    def set_items(self, items: list[GridItem], state: str = LibraryState.READY) -> None:
        # The empty state carries its own call to action; avoid showing two.
        self.create_button.setVisible(bool(items))
        super().set_items(items, state)

    def count_text(self, count: int) -> str:
        return self.tr_.plural("playlists", count)

    def show_empty_state(self, _state: str) -> None:
        self.empty.set_content(
            "playlist",
            self.tr_.t("empty_playlists_title"),
            self.tr_.t("empty_playlists_body"),
            self.tr_.t("dialog_new_playlist"),
            "plus",
        )

    def retranslate(self) -> None:
        self.title.setText(self.tr_.t("nav_playlists"))
        self.search.setPlaceholderText(self.tr_.t("search_playlists"))
        if hasattr(self, "create_button"):
            self.create_button.setText(self.tr_.t("dialog_new_playlist"))
        super().retranslate()


__all__ = ["AlbumsPage", "GridPage", "LibraryState", "PlaylistsPage", "SongsPage"]
