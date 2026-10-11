"""Shared page scaffolding and the track list panel used by several pages."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from enderlitplayer.core.models import Track
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size, Space
from enderlitplayer.ui.widgets.controls import SearchField
from enderlitplayer.ui.widgets.feedback import EmptyState
from enderlitplayer.ui.widgets.track_list import TrackListHeader, TrackListView, TrackRow


class Page(QWidget):
    """Base page: consistent margins and a title row (title, meta, trailing controls)."""

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.tr_ = translator
        self.setObjectName("PageRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(Size.CONTENT_MARGIN, Space.XL + 4, Size.CONTENT_MARGIN, 0)
        self.root.setSpacing(Space.L)
        translator.languageChanged.connect(lambda _lang: self.retranslate())

    def build_title_row(self) -> tuple[QLabel, QLabel, QHBoxLayout]:
        row = QHBoxLayout()
        row.setSpacing(Space.M)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(self)
        title.setObjectName("PageTitle")
        meta = QLabel(self)
        meta.setObjectName("PageMeta")
        text.addWidget(title)
        text.addWidget(meta)
        row.addLayout(text, 1)
        trailing = QHBoxLayout()
        trailing.setSpacing(Space.S)
        row.addLayout(trailing)
        self.root.addLayout(row)
        return title, meta, trailing

    def search_field(self) -> SearchField | None:
        return None

    def retranslate(self) -> None:
        """Re-apply translated strings; overridden by pages."""


class TrackListPanel(QWidget):
    """Header + track list with text filtering. Emits :class:`Track` objects."""

    playRequested = Signal(object)
    actionRequested = Signal(object, str)
    contextRequested = Signal(object, QPoint)

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = translator
        self._tracks: list[Track] = []
        self._filter = ""
        self._numbering = "position"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = TrackListView(theme, self)
        self.header = TrackListHeader(self.view, theme, self)
        self.header.setObjectName("TrackHeader")
        self.stack = QStackedWidget(self)
        self.empty = EmptyState(theme, self)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.empty)
        layout.addWidget(self.header)
        layout.addSpacing(Space.XS)
        layout.addWidget(self.stack, 1)
        self.view.playRequested.connect(self._emit_play)
        self.view.actionTriggered.connect(self._emit_action)
        self.view.contextRequested.connect(self._emit_context)
        self.retranslate()

    # Data ------------------------------------------------------------------------------
    def set_tracks(
        self,
        tracks: list[Track],
        *,
        numbering: str = "position",
        show_album: bool = False,
        removable: bool = False,
        editable: bool = True,
    ) -> None:
        self._tracks = list(tracks)
        self._numbering = numbering
        self.view.show_album = show_album
        self.view.removable = removable
        self.view.editable = editable
        self._rebuild()

    def set_filter(self, text: str) -> None:
        text = text.strip().casefold()
        if text != self._filter:
            self._filter = text
            self._rebuild()

    @property
    def is_filtered(self) -> bool:
        return bool(self._filter)

    @property
    def filter_text(self) -> str:
        return self._filter

    def visible_count(self) -> int:
        return self.view.track_model.rowCount()

    def _matches(self, track: Track) -> bool:
        if not self._filter:
            return True
        haystack = f"{track.title} {track.artist} {track.album}".casefold()
        return self._filter in haystack

    def _rebuild(self) -> None:
        current = self.selected_track()
        rows = []
        for position, track in enumerate(self._tracks, start=1):
            if not self._matches(track):
                continue
            number = (track.track_no or position) if self._numbering == "track_no" else position
            rows.append(TrackRow(track, number, track.album, self._tr.artist(track.artist)))
        self.view.set_rows(rows)
        self.header.update()
        if current is not None:
            self.select_path(current.path, scroll=False)
        self.show_list()

    def show_list(self) -> None:
        self.stack.setCurrentWidget(self.view)
        self.header.setVisible(True)

    def show_empty(
        self, icon: str, title: str, body: str = "", action: str | None = None, action_icon: str | None = None
    ) -> None:
        self.empty.set_content(icon, title, body, action, action_icon)
        self.stack.setCurrentWidget(self.empty)
        self.header.setVisible(False)

    # Selection / state -----------------------------------------------------------------
    def track_at(self, row: int) -> Track | None:
        data = self.view.track_model.row(row)
        return data.track if data else None

    def row_of(self, track: Track) -> int:
        return self.view.track_model.row_of_path(track.path)

    def selected_track(self) -> Track | None:
        return self.track_at(self.view.selected_row()) if self.view.selectionModel() else None

    def select_path(self, path: str, scroll: bool = True) -> None:
        row = self.view.track_model.row_of_path(path)
        if row >= 0:
            index = self.view.track_model.index(row)
            self.view.setCurrentIndex(index)
            if scroll:
                self.view.scrollTo(index)

    def set_playing(self, path: str, active: bool) -> None:
        self.view.set_playing(path, active)

    def set_reorder_mode(self, enabled: bool) -> None:
        self.view.set_reorder_mode(enabled)
        self.header.update()

    def retranslate(self) -> None:
        t = self._tr.t
        self.header.set_labels(t("header_title"), t("header_album"), t("header_length"))
        self.view.set_action_tooltips(
            {
                "edit": t("tip_edit"),
                "remove": t("tip_remove"),
                "up": t("tip_move_up"),
                "down": t("tip_move_down"),
            }
        )
        if self._tracks:
            self._rebuild()

    # Signal adapters -------------------------------------------------------------------
    def _emit_play(self, row: int) -> None:
        track = self.track_at(row)
        if track is not None:
            self.playRequested.emit(track)

    def _emit_action(self, row: int, action: str) -> None:
        track = self.track_at(row)
        if track is not None:
            self.actionRequested.emit(track, action)

    def _emit_context(self, row: int, pos: QPoint) -> None:
        track = self.track_at(row)
        if track is not None:
            self.contextRequested.emit(track, pos)
