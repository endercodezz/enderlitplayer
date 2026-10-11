"""Detail page shared by albums, playlists and the Random Mix."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from enderlitplayer.core.models import Album, CollectionKind
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.assets.icons import make_icon
from enderlitplayer.ui.pages.common import Page, TrackListPanel
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size, Space
from enderlitplayer.ui.widgets.controls import Button, IconButton, SearchField
from enderlitplayer.ui.widgets.cover_view import CoverView
from enderlitplayer.utils.formatting import format_time

_KIND_LABELS = {
    CollectionKind.ALBUM: "kind_album",
    CollectionKind.PLAYLIST: "kind_playlist",
    CollectionKind.MIX: "kind_mix",
    CollectionKind.LIBRARY: "kind_library",
}


class CollectionPage(Page):
    backRequested = Signal()
    playCollectionRequested = Signal()
    togglePlaybackRequested = Signal()
    playTrackRequested = Signal(object)
    trackActionRequested = Signal(object, str)
    trackContextRequested = Signal(object, QPoint)
    newMixRequested = Signal()
    addTracksRequested = Signal()
    editPlaylistRequested = Signal()
    deletePlaylistRequested = Signal()

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(theme, translator, parent)
        self.collection: Album | None = None
        self._is_current = False
        self._is_playing = False
        self.root.setContentsMargins(Size.CONTENT_MARGIN, Space.L, Size.CONTENT_MARGIN, 0)
        self.root.setSpacing(Space.M)

        nav = QHBoxLayout()
        self.back_button = IconButton("arrow_left", theme, size=32, icon_size=18)
        self.back_button.clicked.connect(self.backRequested)
        nav.addWidget(self.back_button)
        nav.addStretch(1)
        self.root.addLayout(nav)

        # Hero -------------------------------------------------------------------------
        hero = QHBoxLayout()
        hero.setSpacing(Space.XL + 4)
        self.cover = CoverView(theme, Size.DETAIL_COVER_MAX, parent=self)
        hero.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignBottom)
        info = QVBoxLayout()
        info.setSpacing(Space.XS)
        info.addStretch(1)
        self.kind_label = QLabel(self)
        self.kind_label.setObjectName("KindLabel")
        self.title_label = QLabel(self)
        self.title_label.setObjectName("DetailTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.meta_label = QLabel(self)
        self.meta_label.setObjectName("DetailMeta")
        self.meta_label.setWordWrap(True)
        self.description = QLabel(self)
        self.description.setObjectName("DetailHint")
        self.description.setWordWrap(True)
        info.addWidget(self.kind_label)
        info.addWidget(self.title_label)
        info.addSpacing(2)
        info.addWidget(self.meta_label)
        info.addWidget(self.description)
        info.addSpacing(Space.L)

        actions = QHBoxLayout()
        actions.setSpacing(Space.S)
        self.play_button = Button("", theme, kind="PrimaryButton", icon_name="play", parent=self)
        self.play_button.clicked.connect(self._on_play_clicked)
        self.new_mix_button = Button("", theme, icon_name="refresh", parent=self)
        self.new_mix_button.clicked.connect(self.newMixRequested)
        self.add_button = Button("", theme, icon_name="plus", parent=self)
        self.add_button.clicked.connect(self.addTracksRequested)
        self.reorder_button = Button("", theme, kind="GhostButton", icon_name="reorder", parent=self)
        self.reorder_button.setCheckable(True)
        self.reorder_button.toggled.connect(self._on_reorder_toggled)
        self.more_button = IconButton("more", theme, size=Size.BUTTON_HEIGHT, icon_size=18)
        self.more_menu = QMenu(self)
        self._edit_action = self.more_menu.addAction("")
        self._edit_action.triggered.connect(self.editPlaylistRequested)
        self.more_menu.addSeparator()
        self._delete_action = self.more_menu.addAction("")
        self._delete_action.triggered.connect(self.deletePlaylistRequested)
        self.more_button.clicked.connect(self._show_more_menu)
        for widget in (self.play_button, self.new_mix_button, self.add_button, self.reorder_button, self.more_button):
            actions.addWidget(widget)
        actions.addStretch(1)
        self.search = SearchField(theme, "", self)
        actions.addWidget(self.search)
        info.addLayout(actions)
        hero.addLayout(info, 1)
        self.root.addLayout(hero)

        self.reorder_hint = QLabel(self)
        self.reorder_hint.setObjectName("DetailHint")
        self.reorder_hint.hide()
        self.root.addWidget(self.reorder_hint)

        self.panel = TrackListPanel(theme, translator, self)
        self.root.addWidget(self.panel, 1)
        self.panel.playRequested.connect(self.playTrackRequested)
        self.panel.actionRequested.connect(self.trackActionRequested)
        self.panel.contextRequested.connect(self.trackContextRequested)
        self.panel.empty.actionTriggered.connect(self.addTracksRequested)
        self.search.textChanged.connect(self._on_search)
        theme.themeChanged.connect(self._refresh_menu_icons)
        self.retranslate()

    # Public API ---------------------------------------------------------------------------
    def search_field(self) -> SearchField:
        return self.search

    @property
    def kind(self) -> CollectionKind | None:
        return self.collection.kind if self.collection else None

    def show_collection(self, collection: Album, cover: QPixmap | None, *, keep_state: bool = False) -> None:
        same = self.collection is not None and self.collection.same_collection(collection)
        self.collection = collection
        if not (keep_state and same):
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.panel.set_filter("")
            self.reorder_button.setChecked(False)
        kind = collection.kind
        self.panel.set_tracks(
            collection.tracks,
            numbering="track_no" if kind == CollectionKind.ALBUM else "position",
            show_album=kind != CollectionKind.ALBUM,
            removable=kind == CollectionKind.PLAYLIST,
        )
        glyph = {CollectionKind.MIX: "shuffle", CollectionKind.PLAYLIST: "playlist"}.get(kind, "album")
        self.cover.set_cover(cover, glyph)
        self._update_header()
        self._update_actions()
        self._update_body()

    def set_cover(self, cover: QPixmap | None) -> None:
        if self.collection is not None:
            glyph = {CollectionKind.MIX: "shuffle", CollectionKind.PLAYLIST: "playlist"}.get(
                self.collection.kind, "album"
            )
            self.cover.set_cover(cover, glyph)

    def set_playback_state(self, playing_path: str, is_current: bool, playing: bool) -> None:
        self._is_current = is_current
        self._is_playing = playing
        self.panel.set_playing(playing_path, playing)
        self._update_play_button()

    @property
    def reorder_mode(self) -> bool:
        return self.reorder_button.isChecked()

    # Internals ----------------------------------------------------------------------------
    def _update_header(self) -> None:
        collection = self.collection
        if collection is None:
            return
        tr = self.tr_
        self.kind_label.setText(tr.t(_KIND_LABELS[collection.kind]).upper())
        self.title_label.setText(collection.title)
        long_title = len(collection.title) > 42
        self.title_label.setObjectName("PageTitle" if long_title else "DetailTitle")
        self.title_label.style().unpolish(self.title_label)
        self.title_label.style().polish(self.title_label)
        parts: list[str] = []
        if collection.kind == CollectionKind.ALBUM:
            parts.append(tr.artist(collection.artist))
            if collection.year:
                parts.append(collection.year)
        parts.append(tr.plural("tracks", len(collection.tracks)))
        if collection.tracks:
            parts.append(format_time(collection.duration))
        self.meta_label.setText("  ·  ".join(parts))
        self.description.setText(tr.t("mix_description"))
        self.description.setVisible(collection.kind == CollectionKind.MIX)

    def _update_actions(self) -> None:
        kind = self.kind
        has_tracks = bool(self.collection and self.collection.tracks)
        self.play_button.setEnabled(has_tracks)
        self.new_mix_button.setVisible(kind == CollectionKind.MIX)
        self.add_button.setVisible(kind == CollectionKind.PLAYLIST)
        self.more_button.setVisible(kind == CollectionKind.PLAYLIST)
        can_reorder = bool(self.collection and self.collection.is_editable_order and len(self.collection.tracks) > 1)
        self.reorder_button.setVisible(can_reorder)
        self.search.setVisible(has_tracks)
        self._update_reorder_availability()
        self._update_play_button()

    def _update_play_button(self) -> None:
        playing_here = self._is_current and self._is_playing
        self.play_button.setText(self.tr_.t("pause" if playing_here else "play"))
        self.play_button.set_icon_name("pause" if playing_here else "play")

    def _update_reorder_availability(self) -> None:
        filtered = self.panel.is_filtered
        if filtered and self.reorder_button.isChecked():
            self.reorder_button.setChecked(False)
        self.reorder_button.setEnabled(not filtered)
        self.reorder_hint.setVisible(self.reorder_button.isChecked())

    def _update_body(self) -> None:
        tr = self.tr_
        if self.collection is None:
            return
        if not self.collection.tracks:
            if self.collection.kind == CollectionKind.PLAYLIST:
                self.panel.show_empty(
                    "playlist", tr.t("empty_playlist_title"), tr.t("empty_playlist_body"), tr.t("add_tracks"), "plus"
                )
            else:
                self.panel.show_empty("shuffle", tr.t("empty_mix_title"), tr.t("empty_mix_body"))
        elif self.panel.visible_count() == 0:
            self.panel.show_empty(
                "search", tr.t("empty_search_title"), tr.t("empty_search_body", query=self.search.text().strip())
            )
        else:
            self.panel.show_list()

    def _on_search(self, text: str) -> None:
        self.panel.set_filter(text)
        self._update_reorder_availability()
        self._update_body()

    def _on_reorder_toggled(self, checked: bool) -> None:
        self.panel.set_reorder_mode(checked)
        self.reorder_button.setText(self.tr_.t("reorder_done" if checked else "reorder"))
        self.reorder_button.set_icon_name("check" if checked else "reorder")
        self.reorder_hint.setVisible(checked)

    def _on_play_clicked(self) -> None:
        if self._is_current:
            self.togglePlaybackRequested.emit()
        else:
            self.playCollectionRequested.emit()

    def _show_more_menu(self) -> None:
        self._refresh_menu_icons()
        self.more_menu.exec(self.more_button.mapToGlobal(QPoint(0, self.more_button.height() + 4)))

    def _refresh_menu_icons(self) -> None:
        self._edit_action.setIcon(make_icon("pencil", self.theme.color("text_secondary"), 16))
        self._delete_action.setIcon(make_icon("trash", self.theme.color("danger"), 16))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        width, height = self.width(), self.height()
        side = int(min(Size.DETAIL_COVER_MAX, max(Size.DETAIL_COVER_MIN, width * 0.2)))
        if height < 620:
            side = Size.DETAIL_COVER_MIN
        if side != self.cover.width():
            self.cover.set_side(side)

    def retranslate(self) -> None:
        tr = self.tr_
        self.back_button.set_tooltip(tr.t("back"))
        self.new_mix_button.setText(tr.t("new_mix"))
        self.add_button.setText(tr.t("add_tracks"))
        self.reorder_button.setText(tr.t("reorder_done" if self.reorder_button.isChecked() else "reorder"))
        self.reorder_hint.setText(tr.t("reorder_hint"))
        self.more_button.set_tooltip(tr.t("more_actions"))
        self._edit_action.setText(tr.t("edit_playlist"))
        self._delete_action.setText(tr.t("delete_playlist"))
        self.search.setPlaceholderText(tr.t("search_tracks"))
        if self.collection is not None:
            self.panel.retranslate()
            self._update_header()
            self._update_body()
        self._update_play_button()


__all__ = ["CollectionPage"]
