"""Persistent playback bar: now playing, transport, seek and volume."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size, Space
from enderlitplayer.ui.widgets.controls import ElidedLabel, IconButton
from enderlitplayer.ui.widgets.cover_view import CoverView
from enderlitplayer.ui.widgets.slider import SeekSlider
from enderlitplayer.utils.formatting import format_time

SIDE_MIN = 200
SIDE_MAX = 360
CENTER_MAX = 720


class PlayerBar(QFrame):
    toggleRequested = Signal()
    previousRequested = Signal()
    nextRequested = Signal()
    seekRequested = Signal(int)
    volumeRequested = Signal(int)
    muteRequested = Signal(bool)
    nowPlayingClicked = Signal()

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = translator
        self._has_track = False
        self._playing = False
        self._muted = False
        self._volume = 80
        self.setObjectName("PlayerBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(Size.PLAYER_BAR)

        grid = QGridLayout(self)
        grid.setContentsMargins(Space.L, Space.M, Space.XL, Space.M)
        grid.setHorizontalSpacing(Space.XL)

        # Now playing ---------------------------------------------------------------
        now = QWidget(self)
        now_layout = QHBoxLayout(now)
        now_layout.setContentsMargins(0, 0, 0, 0)
        now_layout.setSpacing(Space.M)
        self.cover = CoverView(theme, Size.PLAYER_COVER, clickable=True, parent=now)
        self.cover.clicked.connect(self.nowPlayingClicked)
        now_layout.addWidget(self.cover)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addStretch(1)
        self.title = ElidedLabel("", now)
        self.title.setObjectName("NowTitle")
        self.artist = ElidedLabel("", now)
        self.artist.setObjectName("NowArtist")
        text.addWidget(self.title)
        text.addWidget(self.artist)
        text.addStretch(1)
        now_layout.addLayout(text, 1)
        now.setMinimumWidth(SIDE_MIN)
        now.setMaximumWidth(SIDE_MAX)
        now.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Transport + seek ------------------------------------------------------------
        center = QWidget(self)
        center.setMaximumWidth(CENTER_MAX)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(Space.XS)
        transport = QHBoxLayout()
        transport.setSpacing(Space.M)
        transport.addStretch(1)
        self.prev_button = IconButton(
            "previous", theme, size=Size.TRANSPORT_BUTTON, icon_size=18, object_name="TransportButton"
        )
        self.play_button = IconButton(
            "play",
            theme,
            size=Size.PLAY_BUTTON,
            icon_size=18,
            color="window",
            hover_color="on_accent",
            object_name="PlayButton",
        )
        self.next_button = IconButton(
            "next", theme, size=Size.TRANSPORT_BUTTON, icon_size=18, object_name="TransportButton"
        )
        for button in (self.prev_button, self.play_button, self.next_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            transport.addWidget(button)
        transport.addStretch(1)
        self.prev_button.clicked.connect(self.previousRequested)
        self.play_button.clicked.connect(self.toggleRequested)
        self.next_button.clicked.connect(self.nextRequested)
        center_layout.addLayout(transport)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(Space.S + 2)
        self.elapsed = QLabel("0:00", center)
        self.elapsed.setObjectName("TimeLabel")
        self.elapsed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.elapsed.setMinimumWidth(40)
        self.total = QLabel("0:00", center)
        self.total.setObjectName("TimeLabel")
        self.total.setMinimumWidth(40)
        self.seek = SeekSlider(theme, parent=center)
        self.seek.moved.connect(lambda value: self.elapsed.setText(format_time(value / 1000)))
        self.seek.committed.connect(self.seekRequested)
        seek_row.addWidget(self.elapsed)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.total)
        center_layout.addLayout(seek_row)

        # Volume ----------------------------------------------------------------------
        right = QWidget(self)
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Space.S)
        right_layout.addStretch(1)
        self.volume_button = IconButton("volume", theme, size=32, icon_size=18)
        self.volume_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume_button.clicked.connect(lambda: self.muteRequested.emit(not self._muted))
        self.volume = SeekSlider(theme, live=True, step=5, parent=right)
        self.volume.set_maximum(100)
        self.volume.setFixedWidth(Size.VOLUME_WIDTH)
        self.volume.committed.connect(self.volumeRequested)
        right_layout.addWidget(self.volume_button)
        right_layout.addWidget(self.volume)
        right.setMinimumWidth(SIDE_MIN)
        right.setMaximumWidth(SIDE_MAX)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        grid.addWidget(now, 0, 0)
        grid.addWidget(center, 0, 1)
        grid.addWidget(right, 0, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)

        translator.languageChanged.connect(self.retranslate)
        self.set_idle()
        self.retranslate()

    # State ------------------------------------------------------------------------------
    def set_idle(self) -> None:
        self._has_track = False
        self.title.setText(self._tr.t("now_title_idle"))
        self.artist.setText(self._tr.t("now_artist_idle"))
        self.cover.set_cover(None, "songs")
        self.cover.setToolTip("")
        self.set_duration(0)
        self.set_position(0)
        self._update_enabled()

    def set_track(self, title: str, artist: str, pixmap: QPixmap | None) -> None:
        self._has_track = True
        self.title.setText(title)
        self.artist.setText(artist)
        self.cover.set_cover(pixmap, "album")
        self.cover.setToolTip(self._tr.t("tip_go_to_playing"))
        self._update_enabled()

    def set_cover(self, pixmap: QPixmap | None) -> None:
        if self._has_track:
            self.cover.set_cover(pixmap, "album")

    def _update_enabled(self) -> None:
        for button in (self.prev_button, self.play_button, self.next_button):
            button.setEnabled(self._has_track)

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.play_button.set_icon_name("pause" if playing else "play")
        self.play_button.set_tooltip(self._tr.t("tip_pause" if playing else "tip_play"))

    def set_position(self, position_ms: int) -> None:
        if not self.seek.is_dragging:
            self.seek.set_value(position_ms)
            self.elapsed.setText(format_time(position_ms / 1000))

    def set_duration(self, duration_ms: int) -> None:
        self.seek.set_maximum(max(0, duration_ms))
        self.total.setText(format_time(duration_ms / 1000))

    def set_volume(self, volume: int) -> None:
        self._volume = volume
        self.volume.set_value(volume)
        self._update_volume_icon()

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._update_volume_icon()

    def _update_volume_icon(self) -> None:
        if self._muted or self._volume == 0:
            name = "volume_mute"
        elif self._volume < 50:
            name = "volume_low"
        else:
            name = "volume"
        self.volume_button.set_icon_name(name)
        self.volume_button.set_tooltip(self._tr.t("tip_unmute" if self._muted else "tip_mute"))

    def retranslate(self) -> None:
        self.prev_button.set_tooltip(self._tr.t("tip_previous"))
        self.next_button.set_tooltip(self._tr.t("tip_next"))
        self.set_playing(self._playing)
        self._update_volume_icon()
        if not self._has_track:
            self.title.setText(self._tr.t("now_title_idle"))
            self.artist.setText(self._tr.t("now_artist_idle"))
        else:
            self.cover.setToolTip(self._tr.t("tip_go_to_playing"))
