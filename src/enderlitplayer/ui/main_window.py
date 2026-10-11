"""Main window: composes the sidebar, pages and player bar and wires them to services.

The window owns no business logic. Library state lives in :class:`LibraryService`,
playback in :class:`PlaybackController`, persistence in :class:`SettingsStore`.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QMouseEvent, QPixmap, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from enderlitplayer.audio.controller import PlaybackController
from enderlitplayer.core.models import Album, CollectionKind, Track
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.library.editing import EditError, TrackEdit, TrackEditError
from enderlitplayer.library.scanner import default_scan_path
from enderlitplayer.services.covers import CoverProvider
from enderlitplayer.services.library_service import LibraryService
from enderlitplayer.storage.settings import SettingsStore
from enderlitplayer.ui.assets.icons import make_icon
from enderlitplayer.ui.dialogs import AddTracksDialog, PlaylistDialog, TrackEditDialog, confirm, inform
from enderlitplayer.ui.pages import AlbumsPage, CollectionPage, LibraryState, PlaylistsPage, SettingsPage, SongsPage
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size
from enderlitplayer.ui.widgets.album_grid import GridItem
from enderlitplayer.ui.widgets.feedback import Toast
from enderlitplayer.ui.widgets.player_bar import PlayerBar
from enderlitplayer.ui.widgets.sidebar import Sidebar

log = logging.getLogger(__name__)

ROOT_PAGES = ("songs", "albums", "playlists")
NAV_DEBOUNCE_S = 0.25
DETAIL_COVER_PX = Size.DETAIL_COVER_MAX * 2
PLAYER_COVER_PX = Size.PLAYER_COVER * 2


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: SettingsStore,
        library: LibraryService,
        controller: PlaybackController,
        covers: CoverProvider,
        theme: ThemeManager,
        translator: Translator,
    ) -> None:
        super().__init__()
        self.store = store
        self.library = library
        self.controller = controller
        self.covers = covers
        self.theme = theme
        self.tr_ = translator
        self._current = "albums"
        self._origin = "albums"
        self._last_collection: tuple[CollectionKind, str] | None = None
        self._restored = False
        self._nav_last = {"back": 0.0, "forward": 0.0}
        self._fade: QPropertyAnimation | None = None

        self.setWindowTitle(translator.t("app_title"))
        self.setMinimumSize(900, 600)
        self._build()
        self._connect()
        self._install_shortcuts()
        QApplication.instance().installEventFilter(self)

        self.player_bar.set_volume(controller.volume)
        self.settings_page.set_values(theme.mode, theme.cover_style, translator.language)
        self.refresh_library_views()
        start = store.library_mode
        self.navigate(start if start in ROOT_PAGES else "albums")

    # Construction -------------------------------------------------------------------
    def _build(self) -> None:
        root = QWidget(self)
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = Sidebar(self.theme, self.tr_, root)
        body.addWidget(self.sidebar)

        self.content = QWidget(root)
        self.content.setObjectName("ContentHost")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.scan_bar = QProgressBar(self.content)
        self.scan_bar.setObjectName("ScanBar")
        self.scan_bar.setRange(0, 0)
        self.scan_bar.setTextVisible(False)
        self.scan_bar.setVisible(False)
        content_layout.addWidget(self.scan_bar)
        self.stack = QStackedWidget(self.content)
        content_layout.addWidget(self.stack, 1)
        body.addWidget(self.content, 1)
        outer.addLayout(body, 1)

        self.player_bar = PlayerBar(self.theme, self.tr_, root)
        outer.addWidget(self.player_bar)

        self.songs_page = SongsPage(self.theme, self.tr_)
        self.albums_page = AlbumsPage(self.theme, self.tr_, self.covers)
        self.playlists_page = PlaylistsPage(self.theme, self.tr_, self.covers)
        self.collection_page = CollectionPage(self.theme, self.tr_)
        self.settings_page = SettingsPage(self.theme, self.tr_)
        self.pages = {
            "songs": self.songs_page,
            "albums": self.albums_page,
            "playlists": self.playlists_page,
            "collection": self.collection_page,
            "settings": self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.toast = Toast(self.content)

    def _connect(self) -> None:
        lib, ctl = self.library, self.controller
        self.sidebar.pageRequested.connect(self.navigate)

        lib.scanStarted.connect(self._on_scan_started)
        lib.scanProgress.connect(self._on_scan_progress)
        lib.scanFinished.connect(self._on_scan_finished)
        lib.scanFailed.connect(self._on_scan_failed)
        lib.tracksChanged.connect(self._on_tracks_changed)

        ctl.trackChanged.connect(self._on_track_changed)
        ctl.playingChanged.connect(self._on_playing_changed)
        ctl.positionChanged.connect(self.player_bar.set_position)
        ctl.durationChanged.connect(self.player_bar.set_duration)
        ctl.volumeChanged.connect(self.player_bar.set_volume)
        ctl.mutedChanged.connect(self.player_bar.set_muted)
        ctl.playbackFailed.connect(self._on_playback_failed)

        bar = self.player_bar
        bar.toggleRequested.connect(ctl.toggle)
        bar.previousRequested.connect(ctl.previous)
        bar.nextRequested.connect(ctl.next)
        bar.seekRequested.connect(ctl.seek)
        bar.volumeRequested.connect(ctl.set_volume)
        bar.muteRequested.connect(ctl.set_muted)
        bar.nowPlayingClicked.connect(self.show_playing)

        songs = self.songs_page
        songs.playRequested.connect(lambda track: self._play_from(track, songs.collection))
        songs.actionRequested.connect(lambda track, action: self._on_track_action(track, action, songs.collection))
        songs.contextRequested.connect(lambda track, pos: self._track_menu(track, songs.collection, pos))
        songs.chooseFolderRequested.connect(self.choose_folder)

        self.albums_page.openRequested.connect(self.open_album)
        self.albums_page.playRequested.connect(self._play_album_id)
        self.albums_page.contextRequested.connect(self._album_menu)
        self.albums_page.emptyActionRequested.connect(self.choose_folder)

        self.playlists_page.openRequested.connect(self.open_playlist)
        self.playlists_page.playRequested.connect(self._play_playlist_id)
        self.playlists_page.contextRequested.connect(self._playlist_menu)
        self.playlists_page.createRequested.connect(lambda: self.create_playlist())

        page = self.collection_page
        page.backRequested.connect(self.go_back)
        page.playCollectionRequested.connect(self._play_current_collection)
        page.togglePlaybackRequested.connect(ctl.toggle)
        page.playTrackRequested.connect(lambda track: self._play_from(track, page.collection))
        page.trackActionRequested.connect(lambda track, action: self._on_track_action(track, action, page.collection))
        page.trackContextRequested.connect(lambda track, pos: self._track_menu(track, page.collection, pos))
        page.newMixRequested.connect(self.new_mix)
        page.addTracksRequested.connect(self.add_tracks_to_playlist)
        page.editPlaylistRequested.connect(lambda: self.edit_playlist(page.collection.id if page.collection else ""))
        page.deletePlaylistRequested.connect(
            lambda: self.delete_playlist(page.collection.id if page.collection else "")
        )

        settings = self.settings_page
        settings.chooseFolderRequested.connect(self.choose_folder)
        settings.rescanRequested.connect(lambda: self.library.scan())
        settings.themeRequested.connect(self._set_theme)
        settings.coverStyleRequested.connect(self._set_cover_style)
        settings.languageRequested.connect(self._set_language)

        self.tr_.languageChanged.connect(self._on_language_changed)

    def _install_shortcuts(self) -> None:
        bindings: list[tuple[QKeySequence | str, object]] = [
            (QKeySequence(Qt.Key.Key_Space), self.controller.toggle),
            (QKeySequence(Qt.Key.Key_MediaTogglePlayPause), self.controller.toggle),
            (QKeySequence(Qt.Key.Key_MediaPlay), self.controller.toggle),
            (QKeySequence("Ctrl+Left"), self.controller.previous),
            (QKeySequence(Qt.Key.Key_MediaPrevious), self.controller.previous),
            (QKeySequence("Ctrl+Right"), self.controller.next),
            (QKeySequence(Qt.Key.Key_MediaNext), self.controller.next),
            (QKeySequence(Qt.Key.Key_Escape), self.go_back),
            (QKeySequence(Qt.Key.Key_Backspace), self.go_back),
            (QKeySequence.StandardKey.Find, self.focus_search),
            (QKeySequence("Ctrl+L"), lambda: self.navigate("settings")),
            (QKeySequence(Qt.Key.Key_F2), self.edit_selected_track),
            (QKeySequence("Ctrl+E"), self.edit_selected_track),
        ]
        self._shortcuts = []
        for sequence, slot in bindings:
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

    def show_initial(self) -> None:
        geometry = self.store.load_geometry()
        if geometry is not None and self.restoreGeometry(geometry):
            self.show()
        else:
            self.resize(1280, 820)
            self.showMaximized()
        path = self.library.root_path or default_scan_path() or ""
        if path:
            self.library.scan(path)
        else:
            self.refresh_library_views()

    # Navigation ---------------------------------------------------------------------
    @property
    def current_page(self) -> str:
        return self._current

    def navigate(self, key: str) -> None:
        if key == "mix":
            self.open_mix()
            return
        page = self.pages.get(key)
        if page is None:
            return
        if self._current == "collection" and self.collection_page.collection is not None:
            col = self.collection_page.collection
            self._last_collection = (col.kind, col.id)
        if key in ROOT_PAGES:
            self._origin = key
            self.store.library_mode = key
        self._show_page(key)
        self.sidebar.set_current(key)

    def _show_page(self, key: str) -> None:
        changed = self._current != key or self.stack.currentWidget() is not self.pages[key]
        self._current = key
        self.stack.setCurrentWidget(self.pages[key])
        if changed:
            self._fade_in(self.pages[key])

    def _fade_in(self, widget: QWidget) -> None:
        if self._fade is not None:
            self._fade.stop()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._fade = anim
        anim.destroyed.connect(self._clear_fade)

    def _clear_fade(self) -> None:
        self._fade = None

    def go_back(self) -> None:
        if self._current == "collection" or self._current == "settings":
            self.navigate(self._origin)

    def go_forward(self) -> None:
        if self._current == "collection" or self._last_collection is None:
            return
        kind, collection_id = self._last_collection
        collection = self._resolve(kind, collection_id)
        if collection is not None:
            self.open_collection(collection)

    def focus_search(self) -> None:
        page = self.pages.get(self._current)
        field = page.search_field() if page is not None else None
        if field is not None and field.isVisible():
            field.setFocus()
            field.selectAll()

    def _resolve(self, kind: CollectionKind, collection_id: str) -> Album | None:
        title = self.tr_.t("nav_mix") if kind == CollectionKind.MIX else self.tr_.t("nav_songs")
        return self.library.resolve(kind, collection_id, title)

    def open_collection(self, collection: Album) -> None:
        self.collection_page.show_collection(collection, self._collection_cover(collection))
        self._sync_playing()
        self._show_page("collection")
        sidebar_key = {
            CollectionKind.ALBUM: "albums",
            CollectionKind.PLAYLIST: "playlists",
            CollectionKind.MIX: "mix",
            CollectionKind.LIBRARY: "songs",
        }[collection.kind]
        self.sidebar.set_current(sidebar_key)
        if collection.kind == CollectionKind.ALBUM and self._origin not in ("albums", "songs"):
            self._origin = "albums"
        elif collection.kind == CollectionKind.PLAYLIST:
            self._origin = "playlists"

    def open_album(self, album_id: str) -> None:
        album = self.library.album(album_id)
        if album is not None:
            self.open_collection(album)

    def open_playlist(self, playlist_id: str) -> None:
        collection = self.library.playlist_collection(playlist_id)
        if collection is not None:
            self.open_collection(collection)

    def open_mix(self) -> None:
        mix = self.library.mix_collection(self.tr_.t("nav_mix"))
        if mix is None:
            mix = Album("mix_random", self.tr_.t("nav_mix"), "", "", [], 0.0, kind=CollectionKind.MIX)
        self.open_collection(mix)

    def show_playing(self) -> None:
        collection = self.controller.collection
        if collection is None:
            return
        if collection.kind == CollectionKind.LIBRARY:
            self.navigate("songs")
        else:
            fresh = (
                self._resolve(collection.kind, collection.id) if collection.kind != CollectionKind.MIX else collection
            )
            self.open_collection(fresh or collection)
        track = self.controller.track
        if track is not None:
            panel = self.songs_page.panel if self._current == "songs" else self.collection_page.panel
            panel.select_path(track.path)

    # Library ------------------------------------------------------------------------
    def _library_state(self) -> str:
        if not self.library.root_path:
            return LibraryState.NO_FOLDER
        if self.library.albums:
            return LibraryState.READY
        if self.library.is_scanning or not self.library.has_scanned:
            return LibraryState.SCANNING
        return LibraryState.EMPTY

    def refresh_library_views(self) -> None:
        tr = self.tr_
        state = self._library_state()
        albums = self.library.albums
        collection = self.library.library_collection(tr.t("nav_songs")) if albums else None
        self.songs_page.set_state(state, collection)
        self.albums_page.set_items(
            [
                GridItem(album.id, album.title, tr.artist(album.artist), self.library.album_cover_source(album))
                for album in albums
            ],
            state,
        )
        self.refresh_playlists_view()
        self.settings_page.set_library(
            self.library.root_path, len(albums), self.library.track_count, self.library.is_scanning
        )
        self._sync_playing()

    def refresh_playlists_view(self) -> None:
        by_path = self.library.tracks_by_path
        items = []
        for playlist in self.library.playlists.playlists:
            count = len(self.library.playlists.resolve_tracks(playlist, by_path))
            items.append(
                GridItem(
                    playlist.id,
                    playlist.title,
                    self.tr_.plural("tracks", count),
                    self.library.playlist_cover_source(playlist),
                    glyph="playlist",
                )
            )
        self.playlists_page.set_items(items)

    def _refresh_collection_page(self) -> None:
        current = self.collection_page.collection
        if current is None:
            return
        if current.kind == CollectionKind.MIX:
            fresh = self.library.mix_collection(self.tr_.t("nav_mix"))
        else:
            fresh = self._resolve(current.kind, current.id)
        if fresh is None:
            if self._current == "collection":
                self.navigate(self._origin)
            return
        self.collection_page.show_collection(fresh, self._collection_cover(fresh), keep_state=True)
        self.controller.update_collection(fresh)
        self._sync_playing()

    def choose_folder(self) -> None:
        current = self.library.root_path
        start = current if current and Path(current).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, self.tr_.t("choose_folder_title"), start)
        if folder:
            self.library.scan(folder)

    def _on_scan_started(self, _path: str) -> None:
        self.scan_bar.show()
        self.sidebar.set_status(self.tr_.t("scanning"))
        self.refresh_library_views()

    def _on_scan_progress(self, count: int) -> None:
        self.sidebar.set_status(self.tr_.plural("files_scanned", count))

    def _on_scan_finished(self) -> None:
        self.scan_bar.hide()
        self.sidebar.set_status("")
        self.covers.clear()
        self.refresh_library_views()
        if not self._restored:
            self._restored = True
            self._restore_playback()
        else:
            self._rebind_playback()
        if self._current == "collection":
            self._refresh_collection_page()

    def _on_scan_failed(self, reason: str) -> None:
        self.scan_bar.hide()
        self.sidebar.set_status("")
        self.refresh_library_views()
        body = self.tr_.t("folder_not_found") if reason == "folder_not_found" else self.tr_.t("scan_failed_body")
        inform(self, self.theme, self.tr_, self.tr_.t("scan_failed_title"), body)

    def _restore_playback(self) -> None:
        path, position, _playing = self.store.load_playback()
        track = self.library.track(path) if path else None
        if track is None:
            return
        album = self.library.album_for_track(track)
        if album is not None:
            self.controller.restore(track, album, position)

    def _rebind_playback(self) -> None:
        current = self.controller.track
        collection = self.controller.collection
        if current is None:
            return
        fresh_track = self.library.track(current.path)
        if fresh_track is None:
            return
        fresh_collection = None
        if collection is not None and collection.kind != CollectionKind.MIX:
            fresh_collection = self._resolve(collection.kind, collection.id)
        elif collection is not None:
            fresh_collection = self.library.mix_collection(self.tr_.t("nav_mix"))
        self.controller.rebind(fresh_track, fresh_collection)

    def _on_tracks_changed(self) -> None:
        self.refresh_library_views()
        self._refresh_collection_page()
        self._on_track_changed(self.controller.track, self.controller.collection)

    # Playback -----------------------------------------------------------------------
    def _play_from(self, track: Track, collection: Album | None) -> None:
        if collection is None:
            collection = self.library.album_for_track(track)
        self.controller.play_track(track, collection)

    def _play_current_collection(self) -> None:
        collection = self.collection_page.collection
        if collection is not None and collection.tracks:
            self.controller.play_collection(collection)

    def _play_album_id(self, album_id: str) -> None:
        album = self.library.album(album_id)
        if album is not None:
            self.controller.play_collection(album)

    def _play_playlist_id(self, playlist_id: str) -> None:
        collection = self.library.playlist_collection(playlist_id)
        if collection is not None and collection.tracks:
            self.controller.play_collection(collection)

    def _on_track_changed(self, track: Track | None, _collection: Album | None) -> None:
        if track is None:
            self.player_bar.set_idle()
        else:
            self.player_bar.set_track(track.title, self.tr_.artist(track.artist), self._track_cover(track))
        self._sync_playing()

    def _on_playing_changed(self, playing: bool) -> None:
        self.player_bar.set_playing(playing)
        self._sync_playing()

    def _sync_playing(self) -> None:
        track = self.controller.track
        path = track.path if track is not None else ""
        active = self.controller.is_playing
        self.songs_page.panel.set_playing(path, active)
        page_collection = self.collection_page.collection
        playing_collection = self.controller.collection
        is_current = bool(
            page_collection and playing_collection and page_collection.same_collection(playing_collection)
        )
        self.collection_page.set_playback_state(path, is_current, active)

    def _on_playback_failed(self, path: str) -> None:
        self.toast.show_message(self.tr_.t("playback_failed", name=Path(path).name))

    # Covers -------------------------------------------------------------------------
    def _collection_cover(self, collection: Album) -> QPixmap | None:
        return self.covers.load_now(self.library.cover_source(collection), DETAIL_COVER_PX)

    def _track_cover(self, track: Track) -> QPixmap | None:
        return self.covers.load_now(self.library.track_cover_source(track), PLAYER_COVER_PX)

    # Track actions ------------------------------------------------------------------
    def _on_track_action(self, track: Track, action: str, collection: Album | None) -> None:
        if action == "edit":
            self.edit_track(track, collection)
        elif action == "remove" and collection is not None and collection.kind == CollectionKind.PLAYLIST:
            self.remove_from_playlist(collection.id, track)
        elif action in ("up", "down") and collection is not None:
            self.move_track(collection, track, -1 if action == "up" else 1)

    def selected_panel_track(self) -> tuple[Track, Album | None] | None:
        if self._current == "songs":
            track = self.songs_page.panel.selected_track()
            return (track, self.songs_page.collection) if track else None
        if self._current == "collection":
            track = self.collection_page.panel.selected_track()
            return (track, self.collection_page.collection) if track else None
        return None

    def edit_selected_track(self) -> None:
        selected = self.selected_panel_track()
        if selected is not None:
            self.edit_track(*selected)

    def edit_track(self, track: Track, collection: Album | None) -> None:
        if collection is not None and collection.kind == CollectionKind.PLAYLIST:
            number = collection.index_of(track.id) + 1
        else:
            number = track.track_no

        def on_save(edit: TrackEdit) -> EditError | None:
            suspended = self.controller.suspend() if self.controller.is_current(track) else None
            try:
                self.library.edit_track(track, edit, collection)
            except TrackEditError as exc:
                return exc.code
            finally:
                if suspended is not None:
                    self.controller.resume(suspended)
            return None

        TrackEditDialog(self.theme, self.tr_, track, number, on_save, self).exec()

    def move_track(self, collection: Album, track: Track, delta: int) -> None:
        row = collection.index_of(track.id)
        if row < 0:
            return
        if self.library.move_track(collection, row, delta) is None:
            return
        self.controller.update_collection(collection)
        self.collection_page.show_collection(collection, self._collection_cover(collection), keep_state=True)
        self.collection_page.panel.select_path(track.path)
        self._sync_playing()
        if collection.kind == CollectionKind.PLAYLIST:
            self.refresh_playlists_view()

    # Playlists ----------------------------------------------------------------------
    def create_playlist(self, track_paths: list[str] | None = None) -> None:
        dialog = PlaylistDialog(
            self.theme,
            self.tr_,
            title=self.tr_.t("dialog_new_playlist"),
            accept_text=self.tr_.t("create"),
            parent=self,
        )
        if dialog.exec() != PlaylistDialog.DialogCode.Accepted:
            return
        playlist = self.library.playlists.create(dialog.name, dialog.icon_path)
        if track_paths:
            self.library.playlists.add_tracks(playlist.id, track_paths)
            self.toast.show_message(self.tr_.t("tracks_added", name=playlist.title))
            self.refresh_playlists_view()
        else:
            self.refresh_playlists_view()
            self.open_playlist(playlist.id)

    def edit_playlist(self, playlist_id: str) -> None:
        playlist = self.library.playlists.get(playlist_id)
        if playlist is None:
            return
        fallback = None
        for path in playlist.track_paths:
            track = self.library.track(path)
            if track is not None:
                fallback = self.covers.load_now(self.library.track_cover_source(track), 208)
                break
        dialog = PlaylistDialog(
            self.theme,
            self.tr_,
            title=self.tr_.t("dialog_edit_playlist"),
            accept_text=self.tr_.t("save"),
            name=playlist.title,
            icon_path=playlist.icon_path,
            fallback_cover=fallback,
            parent=self,
        )
        if dialog.exec() != PlaylistDialog.DialogCode.Accepted:
            return
        self.library.playlists.update(playlist_id, title=dialog.name, icon_path=dialog.icon_path)
        self.refresh_playlists_view()
        self._refresh_collection_page()

    def delete_playlist(self, playlist_id: str) -> None:
        playlist = self.library.playlists.get(playlist_id)
        if playlist is None:
            return
        if not confirm(
            self,
            self.theme,
            self.tr_,
            self.tr_.t("delete_playlist_title"),
            self.tr_.t("delete_playlist_body", name=playlist.title),
            self.tr_.t("delete"),
            destructive=True,
        ):
            return
        self.library.playlists.delete(playlist_id)
        playing = self.controller.collection
        if playing is not None and playing.kind == CollectionKind.PLAYLIST and playing.id == playlist_id:
            track = self.controller.track
            album = self.library.album_for_track(track) if track is not None else None
            if track is not None:
                self.controller.rebind(track, album)
        if self._last_collection == (CollectionKind.PLAYLIST, playlist_id):
            self._last_collection = None
        self.refresh_playlists_view()
        if self._current == "collection" and self.collection_page.kind == CollectionKind.PLAYLIST:
            self.collection_page.collection = None
            self.navigate("playlists")

    def add_tracks_to_playlist(self) -> None:
        collection = self.collection_page.collection
        if collection is None or collection.kind != CollectionKind.PLAYLIST:
            return
        playlist = self.library.playlists.get(collection.id)
        if playlist is None:
            return
        tracks = [(track, album.title) for album in self.library.albums for track in album.tracks]
        if not tracks:
            inform(self, self.theme, self.tr_, self.tr_.t("add_tracks"), self.tr_.t("no_tracks_to_add"))
            return
        dialog = AddTracksDialog(self.theme, self.tr_, playlist.title, tracks, set(playlist.track_paths), self)
        if dialog.exec() != AddTracksDialog.DialogCode.Accepted:
            return
        if self.library.playlists.add_tracks(playlist.id, dialog.selected_paths()):
            self.refresh_playlists_view()
            self._refresh_collection_page()

    def add_to_playlist(self, playlist_id: str, track: Track) -> None:
        playlist = self.library.playlists.get(playlist_id)
        if playlist is None:
            return
        self.library.playlists.add_tracks(playlist_id, [track.path])
        self.toast.show_message(self.tr_.t("tracks_added", name=playlist.title))
        self.refresh_playlists_view()
        if self.collection_page.kind == CollectionKind.PLAYLIST and self.collection_page.collection.id == playlist_id:
            self._refresh_collection_page()

    def remove_from_playlist(self, playlist_id: str, track: Track) -> None:
        if self.library.playlists.remove_track(playlist_id, track.path):
            self.refresh_playlists_view()
            self._refresh_collection_page()

    def new_mix(self) -> None:
        mix = self.library.mix_collection(self.tr_.t("nav_mix"), regenerate=True)
        if mix is not None:
            self.collection_page.show_collection(mix, None)
            self._sync_playing()

    # Context menus ------------------------------------------------------------------
    def _menu_icon(self, name: str, token: str = "text_secondary") -> object:
        return make_icon(name, self.theme.color(token), 16)

    def _track_menu(self, track: Track, collection: Album | None, pos: QPoint) -> None:
        tr = self.tr_
        menu = QMenu(self)
        menu.addAction(self._menu_icon("play"), tr.t("menu_play"), lambda: self._play_from(track, collection))
        menu.addAction(self._menu_icon("pencil"), tr.t("menu_edit"), lambda: self.edit_track(track, collection))
        submenu = menu.addMenu(self._menu_icon("playlist"), tr.t("menu_add_to_playlist"))
        submenu.addAction(
            self._menu_icon("plus"), tr.t("menu_new_playlist"), lambda: self.create_playlist([track.path])
        )
        playlists = [pl for pl in self.library.playlists.playlists if collection is None or pl.id != collection.id]
        if playlists:
            submenu.addSeparator()
            for playlist in playlists:
                action = submenu.addAction(playlist.title, lambda pid=playlist.id: self.add_to_playlist(pid, track))
                action.setEnabled(track.path not in playlist.track_paths)
        if collection is None or collection.kind != CollectionKind.ALBUM:
            album = self.library.album_for_track(track)
            if album is not None:
                menu.addAction(self._menu_icon("album"), tr.t("menu_go_to_album"), lambda: self.open_collection(album))
        if collection is not None and collection.kind == CollectionKind.PLAYLIST:
            menu.addSeparator()
            menu.addAction(
                self._menu_icon("trash", "danger"),
                tr.t("menu_remove_from_playlist"),
                lambda: self.remove_from_playlist(collection.id, track),
            )
        menu.exec(pos)

    def _album_menu(self, album_id: str, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction(self._menu_icon("play"), self.tr_.t("menu_play"), lambda: self._play_album_id(album_id))
        menu.addAction(self._menu_icon("album"), self.tr_.t("menu_open"), lambda: self.open_album(album_id))
        menu.exec(pos)

    def _playlist_menu(self, playlist_id: str, pos: QPoint) -> None:
        tr = self.tr_
        menu = QMenu(self)
        menu.addAction(self._menu_icon("play"), tr.t("menu_play"), lambda: self._play_playlist_id(playlist_id))
        menu.addAction(self._menu_icon("playlist"), tr.t("menu_open"), lambda: self.open_playlist(playlist_id))
        menu.addAction(self._menu_icon("pencil"), tr.t("edit_playlist"), lambda: self.edit_playlist(playlist_id))
        menu.addSeparator()
        menu.addAction(
            self._menu_icon("trash", "danger"), tr.t("delete_playlist"), lambda: self.delete_playlist(playlist_id)
        )
        menu.exec(pos)

    # Preferences --------------------------------------------------------------------
    def _set_theme(self, mode: str) -> None:
        self.store.theme = mode
        self.theme.set_mode(mode)

    def _set_cover_style(self, style: str) -> None:
        self.store.cover_style = style
        self.theme.set_cover_style(style)

    def _set_language(self, language: str) -> None:
        self.store.language = language
        self.tr_.set_language(language)

    def _on_language_changed(self, _language: str) -> None:
        self.setWindowTitle(self.tr_.t("app_title"))
        self.refresh_library_views()
        if self.collection_page.collection is not None and self.collection_page.kind == CollectionKind.MIX:
            self.collection_page.collection.title = self.tr_.t("nav_mix")
            self.collection_page.retranslate()
        self._on_track_changed(self.controller.track, self.controller.collection)

    # Qt events ----------------------------------------------------------------------
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease) and isinstance(
            event, QMouseEvent
        ):
            if event.button() in (Qt.MouseButton.BackButton, Qt.MouseButton.ForwardButton):
                if not self.isActiveWindow():
                    return False
                if event.type() == QEvent.Type.MouseButtonPress:
                    key = "back" if event.button() == Qt.MouseButton.BackButton else "forward"
                    now = time.monotonic()
                    if now - self._nav_last[key] >= NAV_DEBOUNCE_S:
                        self._nav_last[key] = now
                        if key == "back":
                            self.go_back()
                        else:
                            self.go_forward()
                return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        compact = self.width() < Size.SIDEBAR_COMPACT_BELOW
        if compact != self.sidebar.compact:
            self.sidebar.set_compact(compact)
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.store.save_geometry(self.saveGeometry())
            self.controller.save_state()
            self.store.sync()
        except Exception:
            log.exception("Could not save state on exit")
        QApplication.instance().removeEventFilter(self)
        self.library.shutdown()
        self.covers.shutdown()
        super().closeEvent(event)


__all__ = ["MainWindow"]
