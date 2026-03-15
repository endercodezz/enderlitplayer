from __future__ import annotations

import sys
import time
import math
import random
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QObject,
    QSize,
    QUrl,
    QSettings,
    QEvent,
    QRectF,
    QPointF,
    Property,
    QPropertyAnimation,
    QTimer,
    QEasingCurve,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QIcon, QPolygonF, QLinearGradient, QPainterPath
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QComboBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QStackedWidget,
    QHeaderView,
    QStyledItemDelegate,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QGraphicsOpacityEffect,
)

from mutagen import File as MutagenFile

from library import Album, Track, default_scan_path, scan_library, make_id

import json


class ScanWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            albums = scan_library(self.path)
        except FileNotFoundError:
            self.failed.emit("folder_not_found")
            return
        except Exception:
            self.failed.emit("scan_failed")
            return
        self.finished.emit(albums)


def format_time(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "0:00"
    minutes = int(seconds) // 60
    remaining = int(seconds) % 60
    return f"{minutes}:{remaining:02d}"


def build_placeholder(title: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#2a2a2a"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.fillRect(pixmap.rect(), QColor("#1f1f1f"))
    painter.setPen(QColor("#cfcfcf"))
    font = QFont("Avenir Next", 16, QFont.Bold)
    painter.setFont(font)
    initials = (title or "NA")[:2].upper()
    painter.drawText(pixmap.rect(), Qt.AlignCenter, initials)
    painter.end()
    return pixmap


def build_mix_cover(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#1db954"))
    gradient.setColorAt(1, QColor("#0f0f0f"))
    painter.fillRect(pixmap.rect(), gradient)
    painter.setPen(QColor("#0f0f0f"))
    font = QFont("Avenir Next", max(12, int(size * 0.22)), QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "MIX")
    painter.end()
    return pixmap


def rounded_pixmap(pixmap: QPixmap, radius: float) -> QPixmap:
    if pixmap.isNull():
        return pixmap
    if radius <= 0:
        return pixmap
    rounded = QPixmap(pixmap.size())
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.0, 0.0, float(pixmap.width()), float(pixmap.height())), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return rounded


def build_app_icon(size: int = 256) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    background = QColor("#121212")
    accent = QColor("#1db954")
    painter.setBrush(background)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.2, size * 0.2)

    circle_size = size * 0.62
    circle_rect = QRectF(
        (size - circle_size) / 2,
        (size - circle_size) / 2,
        circle_size,
        circle_size,
    )
    painter.setBrush(accent)
    painter.drawEllipse(circle_rect)

    triangle = QPolygonF(
        [
            QPointF(size * 0.46, size * 0.36),
            QPointF(size * 0.46, size * 0.64),
            QPointF(size * 0.68, size * 0.5),
        ]
    )
    painter.setBrush(QColor("#0f0f0f"))
    painter.drawPolygon(triangle)
    painter.end()
    return QIcon(pixmap)


class ClickSlider(QSlider):
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self.orientation() == Qt.Horizontal:
                position = event.position().x()
                value = int(
                    self.minimum()
                    + (self.maximum() - self.minimum()) * (position / max(1, self.width()))
                )
                self.setValue(value)
                self.sliderMoved.emit(value)
                self.sliderReleased.emit()
                super().mousePressEvent(event)
                return
        super().mousePressEvent(event)


class AlbumListWidget(QListWidget):
    playAlbumRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._overlay_opacity = 0.0
        self._overlay_target = 0.0
        self._hovered_row: Optional[int] = None
        self._overlay_anim = QPropertyAnimation(self, b"overlayOpacity")
        self._overlay_anim.setDuration(140)
        self._overlay_anim.valueChanged.connect(lambda _value: self.viewport().update())
        self._overlay_anim.finished.connect(self._on_overlay_anim_finished)

    def _on_overlay_anim_finished(self) -> None:
        if self._overlay_target == 0.0 and self._overlay_opacity <= 0.01:
            self._hovered_row = None
            self.viewport().update()

    def overlayOpacity(self) -> float:
        return self._overlay_opacity

    def setOverlayOpacity(self, value: float) -> None:
        self._overlay_opacity = max(0.0, min(1.0, float(value)))
        self.viewport().update()

    overlayOpacity = Property(float, overlayOpacity, setOverlayOpacity)

    def _animate_overlay(self, target: float) -> None:
        if self._overlay_target == target and self._overlay_anim.state() == QPropertyAnimation.Running:
            return
        self._overlay_target = target
        self._overlay_anim.stop()
        self._overlay_anim.setStartValue(self._overlay_opacity)
        self._overlay_anim.setEndValue(target)
        self._overlay_anim.start()

    def icon_rect_for_item_rect(self, item_rect) -> QRectF:
        icon_size = self.iconSize()
        top_pad = max(6, int(icon_size.height() * 0.08))
        x = item_rect.x() + (item_rect.width() - icon_size.width()) // 2
        y = item_rect.y() + top_pad
        return QRectF(x, y, icon_size.width(), icon_size.height())

    def overlay_rect_for_item_rect(self, item_rect) -> QRectF:
        icon_rect = self.icon_rect_for_item_rect(item_rect)
        size = max(24, int(icon_rect.width() * 0.28))
        margin = max(6, int(icon_rect.width() * 0.08))
        return QRectF(
            icon_rect.right() - size - margin,
            icon_rect.bottom() - size - margin,
            size,
            size,
        )

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item:
            overlay_rect = self.overlay_rect_for_item_rect(self.visualItemRect(item))
            if overlay_rect.contains(event.pos()):
                album_id = item.data(Qt.UserRole)
                if album_id:
                    self.playAlbumRequested.emit(album_id)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        row = self.row(item) if item else None
        if row is not None and row != -1:
            if row != self._hovered_row:
                self._hovered_row = row
            self._animate_overlay(1.0)
        else:
            if self._hovered_row is not None:
                self._animate_overlay(0.0)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hovered_row is not None:
            self._animate_overlay(0.0)
        super().leaveEvent(event)


class AlbumItemDelegate(QStyledItemDelegate):
    def __init__(self, list_widget: AlbumListWidget) -> None:
        super().__init__(list_widget)
        self.list_widget = list_widget

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        if self.list_widget._hovered_row == index.row() and self.list_widget.overlayOpacity > 0:
            overlay_rect = self.list_widget.overlay_rect_for_item_rect(option.rect)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            accent = QColor("#1db954")
            accent.setAlphaF(self.list_widget.overlayOpacity)
            painter.setBrush(accent)
            painter.drawEllipse(overlay_rect)

            size = min(overlay_rect.width(), overlay_rect.height())
            tri = QPolygonF(
                [
                    QPointF(overlay_rect.x() + size * 0.42, overlay_rect.y() + size * 0.3),
                    QPointF(overlay_rect.x() + size * 0.42, overlay_rect.y() + size * 0.7),
                    QPointF(overlay_rect.x() + size * 0.72, overlay_rect.y() + size * 0.5),
                ]
            )
            tri_color = QColor("#0f0f0f")
            tri_color.setAlphaF(self.list_widget.overlayOpacity)
            painter.setBrush(tri_color)
            painter.drawPolygon(tri)
            painter.restore()


class TrackTable(QTableWidget):
    orderChanged = Signal()
    playRequested = Signal(int)

    def __init__(self, rows=0, columns=0, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.hover_row = -1
        self.playing_track_id: Optional[str] = None
        self.playing_active = False
        self._play_phase = 0.0
        self._play_anim = QPropertyAnimation(self, b"playPhase")
        self._play_anim.setDuration(2800)
        self._play_anim.setStartValue(0.0)
        self._play_anim.setEndValue(1.0)
        self._play_anim.setLoopCount(-1)
        self.setMouseTracking(True)

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.orderChanged.emit()

    def set_playing_track(self, track_id: Optional[str]) -> None:
        self.playing_track_id = track_id
        self._update_play_anim_state()
        self.viewport().update()

    def set_playing_active(self, active: bool) -> None:
        self.playing_active = active
        self._update_play_anim_state()

    def _update_play_anim_state(self) -> None:
        if self.playing_track_id and self.playing_active:
            if self._play_anim.state() != QPropertyAnimation.Running:
                self._play_anim.start()
        else:
            self._play_anim.stop()

    def playPhase(self) -> float:
        return self._play_phase

    def setPlayPhase(self, value: float) -> None:
        self._play_phase = max(0.0, min(1.0, float(value)))
        if self.playing_track_id and self.playing_active:
            self.viewport().update()

    playPhase = Property(float, playPhase, setPlayPhase)

    def current_bar_pattern(self) -> tuple[float, float, float]:
        phase = self._play_phase * 2 * math.pi
        def wave(offset: float) -> float:
            return 0.35 + 0.35 * 0.5 * (1 + math.sin(phase + offset))
        return (
            wave(0.0),
            wave(2 * math.pi / 3),
            wave(4 * math.pi / 3),
        )

    def play_icon_rect(self, row: int) -> QRectF:
        index = self.model().index(row, 0)
        rect = self.visualRect(index)
        size = min(rect.height() - 8, rect.width() - 8, 18)
        size = max(10, size)
        center = rect.center()
        return QRectF(center.x() - size / 2, center.y() - size / 2, size, size)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            pos = event.position()
            row = self.rowAt(int(pos.y()))
            col = self.columnAt(int(pos.x()))
            if row >= 0 and col == 0 and row == self.hover_row:
                icon_rect = self.play_icon_rect(row)
                if icon_rect.contains(pos):
                    self.playRequested.emit(row)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        row = self.rowAt(int(event.position().y()))
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hover_row != -1:
            self.hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)


class TrackNumberDelegate(QStyledItemDelegate):
    def __init__(self, table: TrackTable) -> None:
        super().__init__(table)
        self.table = table

    def paint(self, painter, option, index) -> None:
        if index.column() == 0:
            size = min(option.rect.height() - 8, option.rect.width() - 8, 18)
            center = option.rect.center()
            rect = QRectF(
                center.x() - size / 2,
                center.y() - size / 2,
                size,
                size,
            )
            track_id = index.data(Qt.UserRole)
            if self.table.hover_row == index.row():
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#1db954"))
                tri = QPolygonF(
                    [
                        QPointF(rect.x() + size * 0.25, rect.y() + size * 0.2),
                        QPointF(rect.x() + size * 0.25, rect.y() + size * 0.8),
                        QPointF(rect.x() + size * 0.75, rect.y() + size * 0.5),
                    ]
                )
                painter.drawPolygon(tri)
                painter.restore()
                return
            if track_id and track_id == self.table.playing_track_id:
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)
                color = QColor("#1db954")
                painter.setBrush(color)
                bar_w = max(2, size * 0.2)
                gap = max(2, size * 0.1)
                base = rect.y() + size * 0.8
                h1, h2, h3 = self.table.current_bar_pattern()
                heights = [size * h1, size * h2, size * h3]
                x = rect.x() + (size - (bar_w * 3 + gap * 2)) / 2
                for h in heights:
                    painter.drawRoundedRect(QRectF(x, base - h, bar_w, h), 1.2, 1.2)
                    x += bar_w + gap
                painter.restore()
                return
        super().paint(painter, option, index)


TRANSLATIONS = {
    "en": {
        "app_title": "Enderlit Player",
        "my_library": "My Library",
        "search_library": "Search in library",
        "choose_folder": "Choose a music folder",
        "browse": "Browse",
        "scan": "Scan Library",
        "albums": "Albums",
        "mix_button": "Random mix",
        "mix_hint": "Updates on request",
        "mix_refresh": "Pick mix",
        "found": "{count} found",
        "back_to_albums": "Back to albums",
        "play": "Play",
        "search_albums": "Search albums",
        "search_tracks": "Search tracks",
        "track_title": "Track title",
        "artist": "Artist",
        "file_name": "File name",
        "track_number": "Track #",
        "save_changes": "Save changes",
        "missing_folder_title": "Missing folder",
        "missing_folder_body": "Choose a folder to scan.",
        "scan_failed_title": "Scan failed",
        "scan_failed_body": "Scan failed. Try a different folder.",
        "folder_not_found": "Folder not found.",
        "missing_fields_title": "Missing fields",
        "missing_fields_body": "Title, artist, and file name are required.",
        "invalid_extension_title": "Invalid extension",
        "invalid_extension_body": "Use the same audio file extension.",
        "file_exists_title": "File exists",
        "file_exists_body": "A file with that name already exists.",
        "rename_failed_title": "Rename failed",
        "rename_failed_body": "Could not rename the file.",
        "tag_update_failed_title": "Tag update failed",
        "tag_update_failed_body": "Could not write metadata to this file.",
        "loading": "Scanning your library...",
        "album_meta": "{artist}  {tracks} tracks  {duration}",
        "reorder_hint": "Drag tracks to reorder",
        "reorder_hint_filtered": "Disable filter to reorder tracks",
        "unknown_artist": "Unknown Artist",
        "various_artists": "Various Artists",
        "now_title_idle": "Nothing playing",
        "now_artist_idle": "Select a track to start",
        "album_default": "Album",
        "header_no": "#",
        "header_title": "Title",
        "header_artist": "Artist",
        "header_length": "Length",
        "volume": "Volume",
    },
    "ru": {
        "app_title": "Enderlit Player",
        "my_library": "Моя медиатека",
        "search_library": "Искать в медиатеке",
        "choose_folder": "Выберите папку с музыкой",
        "browse": "Обзор",
        "scan": "Сканировать",
        "albums": "Альбомы",
        "mix_button": "Случайный микс",
        "mix_hint": "Обновляется по кнопке",
        "mix_refresh": "Подобрать",
        "found": "Найдено: {count}",
        "back_to_albums": "Назад к альбомам",
        "play": "Слушать",
        "search_albums": "Искать альбомы",
        "search_tracks": "Искать треки",
        "track_title": "Название трека",
        "artist": "Автор",
        "file_name": "Имя файла",
        "track_number": "Номер",
        "save_changes": "Сохранить",
        "missing_folder_title": "Нет папки",
        "missing_folder_body": "Выберите папку для сканирования.",
        "scan_failed_title": "Ошибка сканирования",
        "scan_failed_body": "Не удалось просканировать. Укажите другую папку.",
        "folder_not_found": "Папка не найдена.",
        "missing_fields_title": "Заполните поля",
        "missing_fields_body": "Нужны название, автор и имя файла.",
        "invalid_extension_title": "Неверное расширение",
        "invalid_extension_body": "Используйте то же расширение файла.",
        "file_exists_title": "Файл уже существует",
        "file_exists_body": "Файл с таким именем уже существует.",
        "rename_failed_title": "Не удалось переименовать",
        "rename_failed_body": "Не удалось переименовать файл.",
        "tag_update_failed_title": "Не удалось обновить теги",
        "tag_update_failed_body": "Не удалось записать теги.",
        "loading": "Сканируем вашу библиотеку...",
        "album_meta": "{artist}  {tracks} треков  {duration}",
        "reorder_hint": "Перетаскивайте треки для порядка",
        "reorder_hint_filtered": "Отключите поиск, чтобы менять порядок",
        "unknown_artist": "Неизвестный исполнитель",
        "various_artists": "Разные исполнители",
        "now_title_idle": "Ничего не играет",
        "now_artist_idle": "Выберите трек",
        "album_default": "Альбом",
        "header_no": "#",
        "header_title": "Название",
        "header_artist": "Автор",
        "header_length": "Длительность",
        "volume": "Громкость",
    },
}


class PlayerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Enderlit Player")
        self.setMinimumSize(1100, 720)

        self.albums: List[Album] = []
        self.current_album: Optional[Album] = None
        self.current_track: Optional[Track] = None
        self.selected_track: Optional[Track] = None
        self.track_filter = ""
        self.playing_album: Optional[Album] = None

        self.settings = QSettings("EnderLit", "EnderLitPlayer")
        self.track_order_map = self._load_track_orders()
        self.language = self.settings.value("language", "ru", type=str)
        self.cover_style = self.settings.value("cover_style", "rounded", type=str)
        if self.cover_style not in {"rounded", "square"}:
            self.cover_style = "rounded"
        self.volume_value = self._load_volume()
        self._last_track_path = self.settings.value("last_track_path", "", type=str)
        self._last_position_ms = max(0, self._load_int("last_position", 0))
        self._last_playing = self._load_bool("last_playing", False)
        self._restore_pending = False
        self._restore_position_ms = 0
        self._restore_autoplay = False
        self._save_state_timer = QTimer(self)
        self._save_state_timer.setSingleShot(True)
        self._save_state_timer.timeout.connect(self._save_playback_state)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.volume_value / 100.0)

        self._nav_last = {"back": 0.0, "forward": 0.0}
        self._transport_buttons: tuple[QPushButton, ...] = tuple()
        self._transport_button_effects: dict[QPushButton, QGraphicsOpacityEffect] = {}
        self._transport_button_anims: dict[QPushButton, QPropertyAnimation] = {}
        self.mix_album_id = "mix_random"
        self.mix_track_paths, self.mix_updated_at = self._load_mix_state()

        self._build_ui()
        self._apply_style()
        self._apply_cover_label_style()
        self._connect_signals()
        self._load_default_path()
        self.update_now_playing_cover()
        self.apply_language()
        self.update_responsive_layout()

        self.search_input.setMinimumWidth(160)
        self.path_input.setMinimumWidth(200)
        self.settings_button.setMinimumWidth(110)

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _load_track_orders(self) -> dict:
        raw = self.settings.value("track_orders", None)
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                raw = ""
        if not isinstance(raw, str):
            raw = str(raw)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_bool(self, key: str, default: bool = False) -> bool:
        raw = self.settings.value(key, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return default

    def _load_int(self, key: str, default: int = 0) -> int:
        raw = self.settings.value(key, default)
        try:
            return int(float(raw))
        except Exception:
            return default

    def _load_volume(self) -> int:
        raw = self.settings.value("volume", 80)
        try:
            value = int(float(raw))
        except Exception:
            value = 80
        return max(0, min(100, value))

    def _load_mix_state(self) -> tuple[list[str], float]:
        raw = self.settings.value("mix_tracks", "")
        updated_raw = self.settings.value("mix_updated_at", 0)
        try:
            updated = float(updated_raw)
        except Exception:
            updated = 0.0
        if isinstance(raw, list):
            return [str(item) for item in raw], updated
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                raw = ""
        if not isinstance(raw, str):
            raw = str(raw)
        if not raw:
            return [], updated
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(item) for item in data], updated
        except Exception:
            pass
        return [], updated

    def _save_mix_state(self) -> None:
        try:
            self.settings.setValue("mix_tracks", json.dumps(self.mix_track_paths))
            self.settings.setValue("mix_updated_at", float(self.mix_updated_at))
        except Exception:
            pass

    def _save_track_orders(self) -> None:
        try:
            self.settings.setValue("track_orders", json.dumps(self.track_order_map))
            self.settings.sync()
        except Exception:
            pass

    def t(self, key: str) -> str:
        bundle = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])
        return bundle.get(key, key)

    def apply_language(self) -> None:
        self.setWindowTitle(self.t("app_title"))
        self.brand_label.setText(self.t("my_library"))
        self.search_input.setPlaceholderText(self.t("search_library"))
        self.path_input.setPlaceholderText(self.t("choose_folder"))
        self.settings_button.setText("Settings" if self.language == "en" else "Настройки")
        self.browse_button.setText(self.t("browse"))
        self.scan_button.setText(self.t("scan"))
        self.album_header_label.setText(self.t("albums"))
        self.detail_mix_refresh.setText(self.t("mix_refresh"))
        self.album_search.setPlaceholderText(self.t("search_albums"))
        self.back_button.setText(self.t("back_to_albums"))
        self.detail_play.setText(self.t("play"))
        self.track_search.setPlaceholderText(self.t("search_tracks"))
        self.editor_title.setPlaceholderText(self.t("track_title"))
        self.editor_number.setPlaceholderText(self.t("track_number"))
        self.editor_artist.setPlaceholderText(self.t("artist"))
        self.editor_filename.setPlaceholderText(self.t("file_name"))
        self.editor_save.setText(self.t("save_changes"))
        self.volume_label.setText(self.t("volume"))
        self._update_volume_label(self.volume.value())
        self.loading_label.setText(self.t("loading"))
        self.track_table.setHorizontalHeaderLabels(
            [self.t("header_no"), self.t("header_title"), self.t("header_artist"), self.t("header_length")]
        )
        self.reorder_hint.setText(
            self.t("reorder_hint_filtered") if self.track_filter else self.t("reorder_hint")
        )
        self.populate_albums(preserve_selection=True)
        if not self.current_track:
            self.now_title.setText(self.t("now_title_idle"))
            self.now_artist.setText(self.t("now_artist_idle"))
        if not self.current_album:
            self.detail_title.setText(self.t("album_default"))
        if self.current_album:
            if self.current_album.id == self.mix_album_id:
                self.detail_title.setText(self.t("mix_button"))
            self.refresh_album_metadata()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        self.root_layout = QVBoxLayout(root)
        self.root_layout.setContentsMargins(24, 24, 24, 24)
        self.root_layout.setSpacing(16)

        self.topbar = QFrame()
        self.topbar.setObjectName("Topbar")
        self.top_layout = QHBoxLayout(self.topbar)
        self.top_layout.setContentsMargins(18, 12, 18, 12)
        self.top_layout.setSpacing(16)

        self.brand_label = QLabel("My Library")
        self.brand_label.setObjectName("Brand")
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Choose a music folder")
        self.browse_button = QPushButton("Browse")
        self.scan_button = QPushButton("Scan Library")
        self.scan_button.setObjectName("PrimaryButton")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in library")
        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("GhostButton")

        self.top_layout.addWidget(self.brand_label, 1)
        self.top_layout.addWidget(self.search_input, 3)
        self.top_layout.addWidget(self.path_input, 3)
        self.top_layout.addWidget(self.settings_button, 1)
        self.top_layout.addWidget(self.browse_button, 1)
        self.top_layout.addWidget(self.scan_button, 1)

        self.root_layout.addWidget(self.topbar)

        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(16)

        self.album_panel = self._build_album_panel()
        self.content_layout.addWidget(self.album_panel, 1)

        content_wrap = QWidget()
        content_wrap.setLayout(self.content_layout)
        self.root_layout.addWidget(content_wrap, 1)

        self.player_bar = self._build_player_bar()
        self.root_layout.addWidget(self.player_bar)

        self.loading_overlay = QFrame(root)
        self.loading_overlay.setObjectName("LoadingOverlay")
        self.loading_overlay.hide()
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignCenter)
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_label = QLabel("Scanning your library...")
        self.loading_label.setObjectName("LoadingLabel")
        overlay_layout.addWidget(self.loading_bar)
        overlay_layout.addWidget(self.loading_label)

    def _init_player_icons(self, icon_size: int = 18) -> None:
        self.icon_play = self._make_icon("play", icon_size, "#0f0f0f")
        self.icon_pause = self._make_icon("pause", icon_size, "#0f0f0f")
        self.icon_prev = self._make_icon("prev", icon_size, "#e9e9e9")
        self.icon_next = self._make_icon("next", icon_size, "#e9e9e9")

        self.prev_button.setIcon(self.icon_prev)
        self.prev_button.setIconSize(QSize(icon_size, icon_size))
        self.prev_button.setText("")

        self.play_button.setIcon(self.icon_play)
        self.play_button.setIconSize(QSize(icon_size, icon_size))
        self.play_button.setText("")

        self.next_button.setIcon(self.icon_next)
        self.next_button.setIconSize(QSize(icon_size, icon_size))
        self.next_button.setText("")

    def _setup_transport_button_animations(self) -> None:
        self._transport_buttons = (self.prev_button, self.play_button, self.next_button)
        self._transport_button_effects = {}
        self._transport_button_anims = {}
        for button in self._transport_buttons:
            effect = QGraphicsOpacityEffect(button)
            effect.setOpacity(0.9)
            button.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", button)
            anim.setDuration(140)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._transport_button_effects[button] = effect
            self._transport_button_anims[button] = anim
            button.installEventFilter(self)
            button.pressed.connect(lambda b=button: self._animate_transport_button(b, 0.72, 90))
            button.released.connect(
                lambda b=button: self._animate_transport_button(
                    b,
                    1.0 if b.underMouse() else 0.9,
                    120,
                )
            )

    def _animate_transport_button(self, button: QPushButton, target_opacity: float, duration: int = 140) -> None:
        effect = self._transport_button_effects.get(button)
        anim = self._transport_button_anims.get(button)
        if not effect or not anim:
            return
        anim.stop()
        anim.setDuration(duration)
        anim.setStartValue(effect.opacity())
        anim.setEndValue(max(0.55, min(1.0, float(target_opacity))))
        anim.start()

    def _make_icon(self, kind: str, size: int, color: str) -> QIcon:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))

        if kind == "play":
            points = QPolygonF(
                [
                    QPointF(size * 0.32, size * 0.2),
                    QPointF(size * 0.78, size * 0.5),
                    QPointF(size * 0.32, size * 0.8),
                ]
            )
            painter.drawPolygon(points)
        elif kind == "pause":
            bar_w = size * 0.18
            gap = size * 0.12
            x1 = size * 0.32
            y = size * 0.2
            h = size * 0.6
            painter.drawRoundedRect(QRectF(x1, y, bar_w, h), 2, 2)
            painter.drawRoundedRect(QRectF(x1 + bar_w + gap, y, bar_w, h), 2, 2)
        elif kind == "prev":
            bar_w = size * 0.12
            painter.drawRoundedRect(QRectF(size * 0.2, size * 0.2, bar_w, size * 0.6), 2, 2)
            points = QPolygonF(
                [
                    QPointF(size * 0.78, size * 0.2),
                    QPointF(size * 0.34, size * 0.5),
                    QPointF(size * 0.78, size * 0.8),
                ]
            )
            painter.drawPolygon(points)
        elif kind == "next":
            bar_w = size * 0.12
            painter.drawRoundedRect(QRectF(size * 0.68, size * 0.2, bar_w, size * 0.6), 2, 2)
            points = QPolygonF(
                [
                    QPointF(size * 0.22, size * 0.2),
                    QPointF(size * 0.66, size * 0.5),
                    QPointF(size * 0.22, size * 0.8),
                ]
            )
            painter.drawPolygon(points)

        painter.end()
        return QIcon(pixmap)

    def _build_album_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.library_stack = QStackedWidget()
        layout.addWidget(self.library_stack, 1)

        library_view = QWidget()
        library_layout = QVBoxLayout(library_view)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.setSpacing(12)

        header_row = QHBoxLayout()
        self.album_header_label = QLabel("Albums")
        self.album_header_label.setObjectName("PanelTitle")
        header_row.addWidget(self.album_header_label)
        header_row.addStretch(1)
        header_wrap = QWidget()
        header_wrap.setLayout(header_row)

        self.album_count = QLabel("0 found")
        self.album_count.setObjectName("PanelMeta")
        self.album_search = QLineEdit()
        self.album_search.setPlaceholderText("Search albums")

        library_layout.addWidget(header_wrap)
        library_layout.addWidget(self.album_count)
        library_layout.addWidget(self.album_search)

        self.album_list = AlbumListWidget()
        self.album_list.setObjectName("AlbumList")
        self.album_list.setViewMode(QListWidget.IconMode)
        self.album_list.setFlow(QListWidget.LeftToRight)
        self.album_list.setWrapping(True)
        self.album_list.setResizeMode(QListWidget.Adjust)
        self.album_list.setIconSize(QSize(140, 140))
        self.album_list.setGridSize(QSize(190, 230))
        self.album_list.setSpacing(14)
        self.album_list.setItemDelegate(AlbumItemDelegate(self.album_list))
        library_layout.addWidget(self.album_list, 1)

        detail_view = QWidget()
        detail_layout = QVBoxLayout(detail_view)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(12)

        back_row = QHBoxLayout()
        self.back_button = QPushButton("Back to albums")
        self.back_button.setObjectName("GhostButton")
        back_row.addWidget(self.back_button)
        back_row.addStretch(1)

        album_header = QHBoxLayout()
        self.detail_cover = QLabel()
        self.detail_cover.setFixedSize(160, 160)
        self.detail_cover.setObjectName("DetailCover")
        self.detail_title = QLabel("Album")
        self.detail_title.setObjectName("DetailTitle")
        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("PanelMeta")
        self.detail_play = QPushButton("Play")
        self.detail_play.setObjectName("PrimaryButton")
        self.detail_mix_refresh = QPushButton("Pick mix")
        self.detail_mix_refresh.setObjectName("GhostButton")
        self.detail_mix_refresh.setVisible(False)

        text_col = QVBoxLayout()
        text_col.addWidget(self.detail_title)
        text_col.addWidget(self.detail_meta)
        text_col.addWidget(self.detail_play)
        text_col.addWidget(self.detail_mix_refresh)
        text_wrap = QWidget()
        text_wrap.setLayout(text_col)

        album_header.addWidget(self.detail_cover)
        album_header.addWidget(text_wrap, 1)

        self.track_search = QLineEdit()
        self.track_search.setPlaceholderText("Search tracks")

        self.reorder_hint = QLabel("Drag tracks to reorder")
        self.reorder_hint.setObjectName("PanelMeta")

        self.track_table = TrackTable(0, 4)
        self.track_table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Length"])
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.track_table.setSelectionMode(QTableWidget.SingleSelection)
        self.track_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.track_table.setObjectName("TrackTable")
        self.track_table.setColumnWidth(0, 40)
        self.track_table.setColumnWidth(3, 70)
        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.track_table.setShowGrid(False)
        self.track_table.setAlternatingRowColors(False)
        self.track_table.setItemDelegateForColumn(0, TrackNumberDelegate(self.track_table))
        self.track_table.setDragEnabled(True)
        self.track_table.setAcceptDrops(True)
        self.track_table.setDropIndicatorShown(True)
        self.track_table.setDragDropOverwriteMode(False)
        self.track_table.setDefaultDropAction(Qt.MoveAction)

        self.editor_frame = QFrame()
        self.editor_frame.setObjectName("EditorFrame")
        self.editor_layout = QHBoxLayout(self.editor_frame)
        self.editor_layout.setContentsMargins(12, 10, 12, 10)
        self.editor_layout.setSpacing(10)

        self.editor_title = QLineEdit()
        self.editor_title.setPlaceholderText("Track title")
        self.editor_number = QLineEdit()
        self.editor_number.setPlaceholderText("Track #")
        self.editor_number.setFixedWidth(80)
        self.editor_artist = QLineEdit()
        self.editor_artist.setPlaceholderText("Artist")
        self.editor_filename = QLineEdit()
        self.editor_filename.setPlaceholderText("File name")
        self.editor_save = QPushButton("Save changes")
        self.editor_save.setObjectName("PrimaryButton")

        self.editor_layout.addWidget(self.editor_number, 1)
        self.editor_layout.addWidget(self.editor_title, 2)
        self.editor_layout.addWidget(self.editor_artist, 2)
        self.editor_layout.addWidget(self.editor_filename, 2)
        self.editor_layout.addWidget(self.editor_save, 1)

        detail_layout.addLayout(back_row)
        detail_layout.addLayout(album_header)
        detail_layout.addWidget(self.track_search)
        detail_layout.addWidget(self.reorder_hint)
        detail_layout.addWidget(self.track_table, 1)
        detail_layout.addWidget(self.editor_frame)

        self.library_stack.addWidget(library_view)
        self.library_stack.addWidget(detail_view)
        self.library_stack.setCurrentIndex(0)
        return panel

    def _build_track_panel(self) -> QFrame:
        raise RuntimeError("Track panel removed in favor of album detail view.")

    def _build_player_bar(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PlayerBar")
        self.player_layout = QHBoxLayout(panel)
        self.player_layout.setContentsMargins(16, 12, 16, 12)
        self.player_layout.setSpacing(16)

        self.cover_label = QLabel()
        self.cover_label.setObjectName("CoverLabel")
        self.cover_label.setFixedSize(64, 64)
        self.cover_label.setAlignment(Qt.AlignCenter)

        info_col = QVBoxLayout()
        self.now_title = QLabel("Nothing playing")
        self.now_title.setObjectName("NowTitle")
        self.now_artist = QLabel("Select a track to start")
        self.now_artist.setObjectName("PanelMeta")
        info_col.addWidget(self.now_title)
        info_col.addWidget(self.now_artist)
        info_wrap = QWidget()
        info_wrap.setLayout(info_col)

        controls_col = QVBoxLayout()
        control_row = QHBoxLayout()
        self.prev_button = QPushButton()
        self.play_button = QPushButton()
        self.play_button.setObjectName("PrimaryButton")
        self.next_button = QPushButton()
        self._init_player_icons()
        self._setup_transport_button_animations()
        control_row.addWidget(self.prev_button)
        control_row.addWidget(self.play_button)
        control_row.addWidget(self.next_button)

        self.progress = ClickSlider(Qt.Horizontal)
        self.progress.setRange(0, 100)
        self.progress.setObjectName("Progress")
        self.current_time = QLabel("0:00")
        self.total_time = QLabel("0:00")
        time_row = QHBoxLayout()
        time_row.addWidget(self.current_time)
        time_row.addWidget(self.progress, 1)
        time_row.addWidget(self.total_time)
        controls_col.addLayout(control_row)
        controls_col.addLayout(time_row)

        volume_col = QVBoxLayout()
        volume_header = QHBoxLayout()
        self.volume_label = QLabel("Volume")
        self.volume_label.setObjectName("PanelMeta")
        self.volume_value_label = QLabel("80%")
        self.volume_value_label.setObjectName("PanelMeta")
        volume_header.addWidget(self.volume_label)
        volume_header.addStretch(1)
        volume_header.addWidget(self.volume_value_label)
        self.volume = ClickSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setSingleStep(1)
        self.volume.setPageStep(5)
        self.volume.setValue(self.volume_value)
        self.volume.setObjectName("Volume")
        volume_col.addLayout(volume_header)
        volume_col.addWidget(self.volume)

        brand_col = QVBoxLayout()
        self.subbrand_label = QLabel("Enderlit Player by Enderlit")
        self.subbrand_label.setObjectName("SubBrand")
        self.version_label = QLabel("ver 0.4.3")
        self.version_label.setObjectName("SubBrand")
        self.subbrand_label.setAlignment(Qt.AlignRight)
        self.version_label.setAlignment(Qt.AlignRight)
        brand_col.addStretch(1)
        brand_col.addWidget(self.subbrand_label)
        brand_col.addWidget(self.version_label)
        brand_wrap = QWidget()
        brand_wrap.setLayout(brand_col)
        volume_wrap = QWidget()
        volume_wrap.setLayout(volume_col)

        self.player_layout.addWidget(self.cover_label)
        self.player_layout.addWidget(info_wrap, 2)
        self.player_layout.addLayout(controls_col, 4)
        self.player_layout.addWidget(volume_wrap, 2)
        self.player_layout.addWidget(brand_wrap, 1)

        return panel

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
              font-family: "Avenir Next", "Segoe UI", "Trebuchet MS", sans-serif;
              color: #e9e9e9;
            }
            QMainWindow {
              background: #0f0f0f;
            }
            #Topbar, #Panel {
              background: #121212;
              border-radius: 18px;
              border: 1px solid #1a1a1a;
            }
            #PlayerBar {
              background: #101010;
              border-radius: 18px;
              border: 1px solid #1a1a1a;
            }
            #Brand {
              font-weight: 700;
            }
            #PanelMeta {
              color: #a0a0a0;
              font-size: 12px;
            }
            #SubBrand {
              color: #8f8f8f;
              font-size: 10px;
            }
            #DetailTitle {
              font-weight: 700;
            }
            QLineEdit {
              background: #1a1a1a;
              border: 1px solid #2a2a2a;
              border-radius: 18px;
              padding: 8px 12px;
              color: #ffffff;
            }
            QLineEdit:hover {
              border: 1px solid #303030;
            }
            QComboBox {
              background: #1a1a1a;
              border: 1px solid #2a2a2a;
              border-radius: 18px;
              padding: 6px 10px;
              color: #ffffff;
            }
            QComboBox::drop-down {
              border: none;
              width: 18px;
            }
            QPushButton {
              background: #1a1a1a;
              border: 1px solid #2a2a2a;
              border-radius: 18px;
              padding: 8px 14px;
              font-weight: 600;
            }
            QPushButton:hover {
              border: 1px solid #3a3a3a;
            }
            #PlayerBar QPushButton {
              font-size: 16px;
              padding: 8px 16px;
              min-width: 44px;
              min-height: 36px;
            }
            #PrimaryButton {
              background: #1db954;
              color: #0f0f0f;
              border: none;
            }
            #PrimaryButton:hover {
              background: #22c95f;
            }
            #GhostButton {
              background: transparent;
              border: 1px solid #2e2e2e;
              color: #cfcfcf;
            }
            QListWidget, QTableWidget {
              background: transparent;
              border: none;
            }
            #TrackTable {
              background: #131313;
              border: 1px solid #1f1f1f;
              border-radius: 16px;
            }
            #AlbumList::item {
              background: transparent;
              border: 1px solid transparent;
              border-radius: 12px;
              padding: 6px;
              margin: 4px;
            }
            #AlbumList::item:hover {
              background: #1b1b1b;
            }
            #AlbumList::item:selected {
              border: 1px solid #1db954;
              background: #1f1f1f;
            }
            QHeaderView::section {
              background: #141414;
              color: #b5b5b5;
              padding: 6px;
              border: none;
              border-bottom: 1px solid #1f1f1f;
            }
            QTableWidget::item {
              padding: 10px 12px;
              border-bottom: 1px solid #1f1f1f;
            }
            #TrackTable::item:hover {
              background: #1a1a1a;
            }
            #TrackTable::item:selected {
              background: #1f1f1f;
            }
            #CoverLabel {
              background: #1a1a1a;
              border-radius: 10px;
            }
            #DetailCover {
              background: #1a1a1a;
              border-radius: 14px;
            }
            #EditorFrame {
              background: #111111;
              border-radius: 16px;
              border: 1px solid #1f1f1f;
            }
            QSlider::groove:horizontal {
              height: 5px;
              background: #2a2a2a;
              border-radius: 999px;
            }
            QSlider::handle:horizontal {
              width: 14px;
              background: #1db954;
              border: 1px solid #0f0f0f;
              border-radius: 7px;
              margin: -5px 0;
            }
            #LoadingOverlay {
              background: rgba(10, 10, 10, 220);
              border-radius: 22px;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.scan_button.clicked.connect(self.scan_library)
        self.browse_button.clicked.connect(self.choose_folder)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.album_list.itemSelectionChanged.connect(self.on_album_selected)
        self.album_list.playAlbumRequested.connect(self.on_album_quick_play)
        self.album_search.textChanged.connect(self.filter_albums)
        self.track_search.textChanged.connect(self.filter_tracks)
        self.track_table.cellDoubleClicked.connect(self.play_selected_track)
        self.track_table.itemSelectionChanged.connect(self.on_track_selected)
        self.track_table.orderChanged.connect(self.on_track_order_changed)
        self.track_table.playRequested.connect(self.on_track_quick_play)
        self.play_button.clicked.connect(self.toggle_play)
        self.next_button.clicked.connect(self.play_next)
        self.prev_button.clicked.connect(self.play_prev)
        self.volume.valueChanged.connect(self.update_volume)
        self.progress.sliderMoved.connect(self.seek)
        self.back_button.clicked.connect(self.show_library_view)
        self.detail_play.clicked.connect(self.play_album)
        self.detail_mix_refresh.clicked.connect(self.refresh_random_mix)
        self.editor_save.clicked.connect(self.save_track_edits)

        self.player.positionChanged.connect(self.update_progress)
        self.player.durationChanged.connect(self.update_duration)
        self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.search_input.textChanged.connect(self.album_search.setText)

    def _load_default_path(self) -> None:
        saved_path = self.settings.value("library_path", "", type=str)
        default_path = saved_path or default_scan_path() or ""
        self.path_input.setText(default_path)
        if default_path:
            self.scan_library()

    def set_language(self, code: str) -> None:
        if code not in {"en", "ru"}:
            return
        if self.language == code:
            return
        self.language = code
        self.settings.setValue("language", self.language)
        self.apply_language()

    def set_cover_style(self, cover_style: str) -> None:
        if cover_style not in {"rounded", "square"}:
            return
        if self.cover_style == cover_style:
            return
        self.cover_style = cover_style
        self.settings.setValue("cover_style", self.cover_style)
        self._apply_cover_label_style()
        self.populate_albums(preserve_selection=True)
        self.update_cover()
        self.update_now_playing_cover()

    def _apply_cover_label_style(self) -> None:
        now_radius = 10 if self.cover_style == "rounded" else 2
        detail_radius = 14 if self.cover_style == "rounded" else 2
        self.cover_label.setStyleSheet(f"background: #1a1a1a; border-radius: {now_radius}px;")
        self.detail_cover.setStyleSheet(f"background: #1a1a1a; border-radius: {detail_radius}px;")

    def open_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings" if self.language == "en" else "Настройки")
        dialog.setModal(True)
        dialog.setMinimumWidth(360)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        language_combo = QComboBox(dialog)
        language_combo.addItem("English", "en")
        language_combo.addItem("Русский", "ru")
        language_combo.setCurrentIndex(0 if self.language == "en" else 1)

        covers_combo = QComboBox(dialog)
        if self.language == "en":
            covers_combo.addItem("Rounded", "rounded")
            covers_combo.addItem("Square", "square")
        else:
            covers_combo.addItem("Скругленные", "rounded")
            covers_combo.addItem("Квадратные", "square")
        covers_combo.setCurrentIndex(0 if self.cover_style == "rounded" else 1)

        form.addRow("Language" if self.language == "en" else "Язык", language_combo)
        form.addRow("Cover style" if self.language == "en" else "Вид обложек", covers_combo)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel_button = QPushButton("Cancel" if self.language == "en" else "Отмена", dialog)
        apply_button = QPushButton("Apply" if self.language == "en" else "Применить", dialog)
        apply_button.setObjectName("PrimaryButton")
        actions.addWidget(cancel_button)
        actions.addWidget(apply_button)
        layout.addLayout(actions)

        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.Accepted:
            return

        self.set_language(language_combo.currentData())
        self.set_cover_style(covers_combo.currentData())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.loading_overlay.setGeometry(self.centralWidget().rect())
        self.update_responsive_layout()
        self.update_album_grid()
        self.update_detail_cover_size()

    def eventFilter(self, _obj, event) -> bool:
        if _obj in self._transport_buttons:
            if event.type() == QEvent.Enter:
                self._animate_transport_button(_obj, 1.0, 150)
                return False
            if event.type() == QEvent.Leave:
                self._animate_transport_button(_obj, 0.9, 130)
                return False
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            if event.button() == Qt.BackButton:
                if self._nav_debounced("back"):
                    self._handle_back_nav()
                return True
            if event.button() == Qt.ForwardButton:
                if self._nav_debounced("forward"):
                    self._handle_forward_nav()
                return True
        if event.type() == QEvent.KeyPress:
            if isinstance(self.focusWidget(), QLineEdit):
                return False
            if event.key() == Qt.Key_Space:
                self.toggle_play()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.library_stack.currentIndex() == 0:
                    if self.album_list.currentItem():
                        self.on_album_selected()
                        self.show_album_view()
                        return True
                else:
                    row = self.track_table.currentRow()
                    if row >= 0:
                        self.play_selected_track(row, 0)
                        return True
            if event.key() == Qt.Key_Backspace:
                self.show_library_view()
                return True
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_F:
                if self.library_stack.currentIndex() == 0:
                    self.search_input.setFocus()
                    self.search_input.selectAll()
                else:
                    self.track_search.setFocus()
                    self.track_search.selectAll()
                return True
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_L:
                self.path_input.setFocus()
                self.path_input.selectAll()
                return True
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
                if self.library_stack.currentIndex() == 1 and self.selected_track:
                    self.save_track_edits()
                    return True
            if event.key() == Qt.Key_Escape:
                self.show_library_view()
                return True
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Left:
                self.play_prev()
                return True
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Right:
                self.play_next()
                return True
        return False

    def _nav_debounced(self, key: str, threshold: float = 0.25) -> bool:
        now = time.monotonic()
        last = self._nav_last.get(key, 0.0)
        if now - last < threshold:
            return False
        self._nav_last[key] = now
        return True

    def _handle_back_nav(self) -> None:
        if self.library_stack.currentIndex() == 1:
            self.show_library_view()

    def _handle_forward_nav(self) -> None:
        if self.library_stack.currentIndex() == 0 and self.current_album:
            self.show_album_view()

    def show_loading(self, show: bool) -> None:
        self.loading_overlay.setVisible(show)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder:
            self.path_input.setText(folder)
            self.settings.setValue("library_path", folder)

    def scan_library(self) -> None:
        path = self.path_input.text().strip()
        if not path:
            QMessageBox.warning(self, self.t("missing_folder_title"), self.t("missing_folder_body"))
            return
        self.settings.setValue("library_path", path)

        self.show_loading(True)
        self.scan_thread = QThread()
        self.scan_worker = ScanWorker(path)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_thread.start()

    def on_scan_failed(self, message: str) -> None:
        self.show_loading(False)
        if message == "folder_not_found":
            body = self.t("folder_not_found")
        else:
            body = self.t("scan_failed_body")
        QMessageBox.warning(self, self.t("scan_failed_title"), body)

    def on_scan_finished(self, albums: List[Album]) -> None:
        self.show_loading(False)
        self.albums = albums
        for album in self.albums:
            self.apply_saved_order(album)
        self.album_search.setText("")
        self.track_search.setText("")
        self.populate_albums()
        if self.albums:
            self.show_library_view()
            self.restore_last_playback()
        else:
            self.library_stack.setCurrentIndex(0)

    def filter_albums(self) -> None:
        self.populate_albums(preserve_selection=True)

    def filter_tracks(self) -> None:
        self.track_filter = self.track_search.text().strip().lower()
        self.populate_tracks()

    def populate_albums(self, preserve_selection: bool = False) -> None:
        current_id = self.current_album.id if preserve_selection and self.current_album else None
        self.album_list.blockSignals(True)
        self.album_list.clear()
        query = self.album_search.text().strip().lower()
        filtered = [
            album
            for album in self.albums
            if not query
            or f"{album.title} {album.artist}".lower().find(query) >= 0
        ]
        self.album_count.setText(self.t("found").format(count=len(filtered)))

        mix_title = self.t("mix_button")
        mix_hint = self.t("mix_hint")
        if not query or mix_title.lower().find(query) >= 0 or mix_hint.lower().find(query) >= 0:
            mix_item = QListWidgetItem()
            mix_item.setText(f"{mix_title}\n{mix_hint}".strip())
            cover_size = self.album_list.iconSize().width() or 140
            mix_item.setIcon(QIcon(rounded_pixmap(build_mix_cover(cover_size), self._cover_radius(cover_size))))
            mix_item.setData(Qt.UserRole, self.mix_album_id)
            mix_item.setSizeHint(QSize(160, 200))
            self.album_list.addItem(mix_item)

        for album in filtered:
            item = QListWidgetItem()
            item.setText(f"{album.title}\n{self.display_artist(album.artist)}".strip())
            icon = self.album_pixmap(album, 140)
            item.setIcon(icon)
            item.setData(Qt.UserRole, album.id)
            item.setSizeHint(QSize(160, 200))
            self.album_list.addItem(item)
        if current_id:
            for index in range(self.album_list.count()):
                item = self.album_list.item(index)
                if item.data(Qt.UserRole) == current_id:
                    self.album_list.setCurrentItem(item)
                    break
        self.album_list.blockSignals(False)
        self.update_album_grid()

    def _cover_radius(self, size: int) -> float:
        if self.cover_style == "square":
            return 0.0
        return max(6.0, size * 0.085)

    def album_pixmap(self, album: Album, size: int) -> QPixmap:
        radius = self._cover_radius(size)
        if album.id == self.mix_album_id:
            return rounded_pixmap(build_mix_cover(size), radius)

        source = QPixmap()
        if album.cover_bytes:
            source.loadFromData(album.cover_bytes)
        if source.isNull() and album.cover_path and Path(album.cover_path).exists():
            source = QPixmap(album.cover_path)
        if source.isNull():
            source = build_placeholder(album.title, size)
        scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        return rounded_pixmap(scaled, radius)

    def on_album_selected(self) -> None:
        selected_items = self.album_list.selectedItems()
        if not selected_items:
            return
        album_id = selected_items[0].data(Qt.UserRole)
        if album_id == self.mix_album_id:
            mix_album = self.get_random_mix_album()
            if mix_album:
                self.open_album(mix_album)
            return
        album = next((a for a in self.albums if a.id == album_id), None)
        if not album:
            return
        self.open_album(album)

    def on_album_clicked(self, _item: QListWidgetItem) -> None:
        self.on_album_selected()

    def on_album_quick_play(self, album_id: str) -> None:
        if album_id == self.mix_album_id:
            mix_album = self.get_random_mix_album()
            if mix_album and mix_album.tracks:
                self.start_track(mix_album.tracks[0], mix_album)
            return
        album = next((a for a in self.albums if a.id == album_id), None)
        if not album or not album.tracks:
            return
        self.start_track(album.tracks[0], album)

    def open_album(self, album: Album) -> None:
        self.current_album = album
        if album.id == self.mix_album_id:
            self.detail_title.setText(self.t("mix_button"))
            self.detail_mix_refresh.setVisible(True)
        else:
            self.detail_title.setText(album.title)
            self.detail_mix_refresh.setVisible(False)
        self.refresh_album_metadata()
        self.track_filter = self.track_search.text().strip().lower()
        self.populate_tracks()
        self.update_cover()
        self.show_album_view()

    def populate_tracks(self) -> None:
        self.track_table.setRowCount(0)
        if not self.current_album:
            return
        is_mix = self.current_album.id == self.mix_album_id
        tracks = self.current_album.tracks
        if self.track_filter:
            tracks = [
                track
                for track in tracks
                if self.track_filter in f"{track.title} {track.artist}".lower()
            ]
            self.track_table.setDragDropMode(QAbstractItemView.NoDragDrop)
            if is_mix:
                self.reorder_hint.setText(self.t("mix_hint"))
            else:
                self.reorder_hint.setText(self.t("reorder_hint_filtered"))
        else:
            if is_mix:
                self.track_table.setDragDropMode(QAbstractItemView.NoDragDrop)
                self.reorder_hint.setText(self.t("mix_hint"))
            else:
                self.track_table.setDragDropMode(QAbstractItemView.InternalMove)
                self.reorder_hint.setText(self.t("reorder_hint"))

        self.editor_frame.setEnabled(not is_mix)

        self.track_table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            number_item = QTableWidgetItem(str(row + 1 if is_mix else (track.track_no or row + 1)))
            title_item = QTableWidgetItem(track.title)
            artist_item = QTableWidgetItem(track.artist)
            length_item = QTableWidgetItem(format_time(track.duration))
            number_item.setData(Qt.UserRole, track.id)
            self.track_table.setItem(row, 0, number_item)
            self.track_table.setItem(row, 1, title_item)
            self.track_table.setItem(row, 2, artist_item)
            self.track_table.setItem(row, 3, length_item)
        if self.current_album and self.current_track and self.playing_album == self.current_album:
            self.track_table.set_playing_track(self.current_track.id)
        else:
            self.track_table.set_playing_track(None)
        self.on_track_selected()

    def on_track_order_changed(self) -> None:
        if not self.current_album:
            return
        if self.current_album.id == self.mix_album_id:
            return
        if self.track_filter:
            return
        new_ids = []
        for row in range(self.track_table.rowCount()):
            item = self.track_table.item(row, 0)
            if item:
                new_ids.append(item.data(Qt.UserRole))
        id_to_track = {track.id: track for track in self.current_album.tracks}
        new_tracks = [id_to_track[track_id] for track_id in new_ids if track_id in id_to_track]
        existing_ids = {track.id for track in new_tracks}
        for track in self.current_album.tracks:
            if track.id not in existing_ids:
                new_tracks.append(track)
        self.current_album.tracks = new_tracks
        for index, track in enumerate(self.current_album.tracks, start=1):
            track.track_no = index
        self.track_order_map[self.current_album.id] = [track.path for track in self.current_album.tracks]
        self._save_track_orders()
        self.populate_tracks()

    def on_track_selected(self) -> None:
        items = self.track_table.selectedItems()
        if not items:
            self.selected_track = None
            self.editor_number.setText("")
            self.editor_title.setText("")
            self.editor_artist.setText("")
            self.editor_filename.setText("")
            return
        row = items[0].row()
        item = self.track_table.item(row, 0)
        if not item or not self.current_album:
            return
        track_id = item.data(Qt.UserRole)
        track = next((t for t in self.current_album.tracks if t.id == track_id), None)
        if not track:
            return
        self.selected_track = track
        self.editor_number.setText(str(track.track_no) if track.track_no else "")
        self.editor_title.setText(track.title)
        self.editor_artist.setText(track.artist)
        self.editor_filename.setText(Path(track.path).name)

    def update_cover(self) -> None:
        if not self.current_album:
            self.detail_cover.setPixmap(rounded_pixmap(build_placeholder("NA", 160), self._cover_radius(160)))
            return
        detail_size = self.detail_cover.width() or 160
        detail_pixmap = self.album_pixmap(self.current_album, max(320, detail_size))
        self.detail_cover.setPixmap(
            detail_pixmap.scaled(detail_size, detail_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        )

    def play_selected_track(self, row: int, _column: int) -> None:
        if not self.current_album:
            return
        item = self.track_table.item(row, 0)
        if not item:
            return
        track_id = item.data(Qt.UserRole)
        track = next((t for t in self.current_album.tracks if t.id == track_id), None)
        if not track:
            return
        self.start_track(track, self.current_album)

    def on_track_quick_play(self, row: int) -> None:
        self.track_table.selectRow(row)
        self.play_selected_track(row, 0)

    def start_track(self, track: Track, album: Optional[Album] = None) -> None:
        self.current_track = track
        self.playing_album = album or self.current_album
        self.player.setSource(QUrl.fromLocalFile(track.path))
        self.player.play()
        self._restore_pending = False
        self._last_position_ms = 0
        self.set_play_state(True)
        self.now_title.setText(track.title)
        self.now_artist.setText(track.artist)
        self.populate_tracks()
        if self.current_album and self.playing_album == self.current_album:
            self.track_table.set_playing_track(track.id)
        self.update_now_playing_cover()
        self._schedule_playback_save(immediate=True)

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.set_play_state(False)
        else:
            self.player.play()
            self.set_play_state(True)
        self._schedule_playback_save(immediate=True)

    def play_next(self) -> None:
        if not self.playing_album or not self.current_track:
            return
        tracks = self.playing_album.tracks
        try:
            index = next(i for i, t in enumerate(tracks) if t.id == self.current_track.id)
        except StopIteration:
            return
        next_index = index + 1
        if next_index < len(tracks):
            self.start_track(tracks[next_index], self.playing_album)
            return
        self.start_random_album_after_end()

    def play_prev(self) -> None:
        if not self.playing_album or not self.current_track:
            return
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        tracks = self.playing_album.tracks
        try:
            index = next(i for i, t in enumerate(tracks) if t.id == self.current_track.id)
        except StopIteration:
            return
        prev_index = max(0, index - 1)
        self.start_track(tracks[prev_index], self.playing_album)

    def start_random_album_after_end(self) -> None:
        candidates = [album for album in self.albums if album.tracks]
        if not candidates:
            return
        exclude_id = self.playing_album.id if self.playing_album else None
        if exclude_id:
            candidates = [album for album in candidates if album.id != exclude_id]
        if not candidates:
            return
        album = random.choice(candidates)
        self.start_track(album.tracks[0], album)

    def show_album_view(self) -> None:
        if self.library_stack.currentIndex() != 1:
            self.library_stack.setCurrentIndex(1)
            self._fade_current_view()

    def show_library_view(self) -> None:
        changed = self.library_stack.currentIndex() != 0
        if changed:
            self.library_stack.setCurrentIndex(0)
        self.album_list.clearSelection()
        self.album_list.setCurrentRow(-1)
        self.selected_track = None
        self.editor_frame.setEnabled(True)
        self.editor_number.setText("")
        self.editor_title.setText("")
        self.editor_artist.setText("")
        self.editor_filename.setText("")
        if changed:
            self._fade_current_view()

    def _fade_current_view(self) -> None:
        widget = self.library_stack.currentWidget()
        if not widget:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def play_album(self) -> None:
        if not self.current_album or not self.current_album.tracks:
            return
        self.start_track(self.current_album.tracks[0], self.current_album)

    def save_track_edits(self) -> None:
        if not self.selected_track:
            return

        new_title = self.editor_title.text().strip()
        new_artist = self.editor_artist.text().strip()
        new_filename = self.editor_filename.text().strip()
        new_number_raw = self.editor_number.text().strip()
        new_number = 0
        if new_number_raw:
            try:
                new_number = int(new_number_raw)
            except ValueError:
                new_number = 0

        if not new_title or not new_artist or not new_filename:
            QMessageBox.warning(self, self.t("missing_fields_title"), self.t("missing_fields_body"))
            return

        track = self.selected_track
        old_path = track.path
        original_path = Path(track.path)
        new_path = Path(new_filename)
        if new_path.suffix == "":
            new_path = new_path.with_suffix(original_path.suffix)
        if new_path.suffix.lower() != original_path.suffix.lower():
            QMessageBox.warning(self, self.t("invalid_extension_title"), self.t("invalid_extension_body"))
            return
        if new_path.name != original_path.name:
            candidate = original_path.with_name(new_path.name)
            if candidate.exists():
                QMessageBox.warning(self, self.t("file_exists_title"), self.t("file_exists_body"))
                return
            try:
                original_path.rename(candidate)
            except Exception:
                QMessageBox.warning(self, self.t("rename_failed_title"), self.t("rename_failed_body"))
                return
            track.path = str(candidate)
            if self.current_album and self.current_album.id in self.track_order_map:
                order_list = self.track_order_map[self.current_album.id]
                self.track_order_map[self.current_album.id] = [
                    track.path if path == old_path else path for path in order_list
                ]
                self._save_track_orders()

        try:
            audio = MutagenFile(track.path, easy=True)
            if audio is None:
                raise RuntimeError("Unsupported file")
            audio["title"] = [new_title]
            audio["artist"] = [new_artist]
            if new_number > 0:
                audio["tracknumber"] = [str(new_number)]
            audio.save()
        except Exception:
            QMessageBox.warning(self, self.t("tag_update_failed_title"), self.t("tag_update_failed_body"))
            return

        old_id = track.id
        track.title = new_title
        track.artist = new_artist
        if new_number > 0:
            track.track_no = new_number
        track.id = make_id(track.path)

        if self.current_track and self.current_track.id == old_id:
            was_playing = self.player.playbackState() == QMediaPlayer.PlayingState
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(track.path))
            if was_playing:
                self.player.play()
            self.current_track = track
            self.set_play_state(was_playing)

        self.refresh_album_metadata()
        if new_number > 0 and self.current_album:
            self.current_album.tracks.sort(
                key=lambda t: (t.track_no or 9999, t.title.lower())
            )
            self.track_order_map[self.current_album.id] = [
                t.path for t in self.current_album.tracks
            ]
            self._save_track_orders()
        self.populate_tracks()
        self.update_album_list_item(self.current_album)

    def apply_saved_order(self, album: Album) -> None:
        order = self.track_order_map.get(album.id)
        if not order:
            return
        path_to_track = {track.path: track for track in album.tracks}
        new_tracks: List[Track] = []
        for path in order:
            if path in path_to_track:
                new_tracks.append(path_to_track.pop(path))
        new_tracks.extend(path_to_track.values())
        album.tracks = new_tracks
        for index, track in enumerate(album.tracks, start=1):
            track.track_no = index

    def refresh_album_metadata(self) -> None:
        if not self.current_album:
            return
        if self.current_album.id == self.mix_album_id:
            total_duration = sum(track.duration for track in self.current_album.tracks)
            self.detail_meta.setText(
                self.t("album_meta").format(
                    artist=self.t("various_artists"),
                    tracks=len(self.current_album.tracks),
                    duration=format_time(total_duration),
                )
            )
            return
        artists = {track.artist for track in self.current_album.tracks if track.artist}
        if len(artists) == 1:
            self.current_album.artist = next(iter(artists))
        elif len(artists) == 0:
            self.current_album.artist = "Unknown Artist"
        else:
            self.current_album.artist = "Various Artists"
        self.detail_meta.setText(
            self.t("album_meta").format(
                artist=self.display_artist(self.current_album.artist),
                tracks=len(self.current_album.tracks),
                duration=format_time(self.current_album.duration),
            )
        )

    def display_artist(self, artist: str) -> str:
        if artist == "Unknown Artist":
            return self.t("unknown_artist")
        if artist == "Various Artists":
            return self.t("various_artists")
        return artist

    def _build_random_mix(self) -> None:
        path_to_track: dict[str, Track] = {}
        for album in self.albums:
            for track in album.tracks:
                path_to_track[track.path] = track
        all_paths = list(path_to_track.keys())
        random.shuffle(all_paths)
        selected_paths = all_paths[: min(20, len(all_paths))]
        self.mix_track_paths = selected_paths
        self.mix_updated_at = time.time()
        self._save_mix_state()

    def _resolve_mix_tracks(self) -> list[Track]:
        path_to_track: dict[str, Track] = {}
        for album in self.albums:
            for track in album.tracks:
                path_to_track[track.path] = track
        resolved = [path_to_track[path] for path in self.mix_track_paths if path in path_to_track]
        return resolved

    def get_random_mix_album(self, force: bool = False) -> Optional[Album]:
        if not self.albums:
            return None
        if force or not self.mix_track_paths:
            self._build_random_mix()
        tracks = self._resolve_mix_tracks()
        if len(tracks) != len(self.mix_track_paths):
            self._build_random_mix()
            tracks = self._resolve_mix_tracks()
        if not tracks:
            return None
        duration = sum(track.duration for track in tracks)
        return Album(
            id=self.mix_album_id,
            title=self.t("mix_button"),
            artist="Various Artists",
            year="",
            tracks=tracks,
            duration=duration,
            cover_path=None,
            cover_bytes=None,
            cover_mime=None,
        )

    def show_random_mix(self) -> None:
        mix_album = self.get_random_mix_album()
        if not mix_album:
            return
        self.open_album(mix_album)

    def refresh_random_mix(self) -> None:
        if not self.albums:
            return
        self._build_random_mix()
        if self.current_album and self.current_album.id == self.mix_album_id:
            mix_album = self.get_random_mix_album()
            if mix_album:
                self.open_album(mix_album)

    def update_album_list_item(self, album: Optional[Album]) -> None:
        if not album:
            return
        for index in range(self.album_list.count()):
            item = self.album_list.item(index)
            if item.data(Qt.UserRole) == album.id:
                item.setText(f"{album.title}\n{self.display_artist(album.artist)}".strip())
                break

    def update_volume(self, value: int) -> None:
        self.audio_output.setVolume(value / 100.0)
        self.settings.setValue("volume", value)
        self._update_volume_label(value)

    def _update_volume_label(self, value: int) -> None:
        if hasattr(self, "volume_value_label"):
            self.volume_value_label.setText(f"{value}%")

    def _schedule_playback_save(self, immediate: bool = False) -> None:
        if immediate:
            self._save_state_timer.stop()
            self._save_playback_state()
            return
        if not self._save_state_timer.isActive():
            self._save_state_timer.start(1200)

    def _save_playback_state(self) -> None:
        if not self.current_track:
            return
        try:
            self.settings.setValue("last_track_path", self.current_track.path)
            self.settings.setValue("last_position", int(self._last_position_ms))
            self.settings.setValue(
                "last_playing",
                self.player.playbackState() == QMediaPlayer.PlayingState,
            )
        except Exception:
            pass

    def _find_track_by_path(self, path: str) -> Optional[tuple[Track, Album]]:
        if not path:
            return None
        for album in self.albums:
            for track in album.tracks:
                if track.path == path:
                    return track, album
        return None

    def restore_last_playback(self) -> None:
        state = self._find_track_by_path(self._last_track_path)
        if not state:
            return
        track, album = state
        self.current_track = track
        self.playing_album = album
        self.now_title.setText(track.title)
        self.now_artist.setText(track.artist)
        self.update_now_playing_cover()
        self.player.setSource(QUrl.fromLocalFile(track.path))
        self._restore_position_ms = max(0, self._last_position_ms)
        self._restore_autoplay = False
        self._restore_pending = True
        if self._restore_position_ms == 0 and self._restore_autoplay:
            self.player.play()
            self.set_play_state(True)
        else:
            self.player.pause()
            self.set_play_state(False)

    def update_album_grid(self) -> None:
        if not self.album_list:
            return
        available = self.album_list.viewport().width()
        if available <= 0:
            return
        min_item = 150
        max_item = 220
        columns = max(2, available // min_item)
        item_width = max(min_item, min(max_item, available // columns))
        cover_size = max(110, item_width - 44)
        self.album_list.setIconSize(QSize(cover_size, cover_size))
        self.album_list.setGridSize(QSize(item_width, item_width + 46))
        self.album_list.update()

    def update_detail_cover_size(self) -> None:
        if not self.detail_cover:
            return
        available = self.album_panel.width()
        if available <= 0:
            return
        target = max(110, min(200, available // 7))
        if self.detail_cover.width() != target:
            self.detail_cover.setFixedSize(target, target)
            self.update_cover()

    def update_responsive_layout(self) -> None:
        width = self.width()
        scale = max(0.65, min(1.0, width / 1800))
        margin = int(22 * scale)
        spacing = int(14 * scale)
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(spacing)
        self.top_layout.setContentsMargins(
            int(16 * scale), int(10 * scale), int(16 * scale), int(10 * scale)
        )
        self.top_layout.setSpacing(int(12 * scale))
        self.content_layout.setSpacing(int(14 * scale))
        if self.player_layout:
            self.player_layout.setContentsMargins(
                int(14 * scale), int(10 * scale), int(14 * scale), int(10 * scale)
            )
            self.player_layout.setSpacing(int(12 * scale))
        if self.editor_layout:
            self.editor_layout.setContentsMargins(
                int(10 * scale), int(8 * scale), int(10 * scale), int(8 * scale)
            )
            self.editor_layout.setSpacing(int(8 * scale))
        if self.album_list:
            self.album_list.setSpacing(int(10 * scale))

        base_font = int(10 + 4 * scale)
        brand_font = int(14 + 6 * scale)
        detail_font = int(16 + 6 * scale)
        now_font = int(12 + 4 * scale)
        sub_font = int(9 + 2 * scale)

        brand = self.brand_label.font()
        brand.setPointSize(brand_font)
        self.brand_label.setFont(brand)

        detail = self.detail_title.font()
        detail.setPointSize(detail_font)
        self.detail_title.setFont(detail)

        now = self.now_title.font()
        now.setPointSize(now_font)
        self.now_title.setFont(now)

        if hasattr(self, "subbrand_label"):
            sub = self.subbrand_label.font()
            sub.setPointSize(sub_font)
            self.subbrand_label.setFont(sub)
            self.version_label.setFont(sub)

        play_height = int(30 * scale)
        play_width = int(220 * scale)
        self.detail_play.setFixedHeight(max(28, play_height))
        self.detail_play.setMaximumWidth(max(160, play_width))

        icon_size = max(14, int(16 * scale))
        self._init_player_icons(icon_size)

        cover_size = max(44, int(56 * scale))
        self.cover_label.setFixedSize(cover_size, cover_size)

        app_font = self.font()
        app_font.setPointSize(base_font)
        self.setFont(app_font)

        row_height = int(34 * scale)
        self.track_table.verticalHeader().setDefaultSectionSize(row_height)

    def set_play_state(self, is_playing: bool) -> None:
        self.play_button.setIcon(self.icon_pause if is_playing else self.icon_play)
        if hasattr(self, "track_table"):
            self.track_table.set_playing_active(is_playing)

    def update_now_playing_cover(self) -> None:
        if not self.playing_album:
            size = self.cover_label.width() or 56
            self.cover_label.setPixmap(
                rounded_pixmap(build_placeholder("NA", size), self._cover_radius(size))
            )
            return
        size = self.cover_label.width() or 56
        pixmap = self.album_pixmap(self.playing_album, max(128, size))
        self.cover_label.setPixmap(
            pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        )

    def seek(self, value: int) -> None:
        self.player.setPosition(value)

    def update_progress(self, position: int) -> None:
        self.progress.blockSignals(True)
        self.progress.setValue(position)
        self.progress.blockSignals(False)
        self.current_time.setText(format_time(position / 1000))
        if self.current_track:
            self._last_position_ms = position
            self._schedule_playback_save()

    def update_duration(self, duration: int) -> None:
        self.progress.setRange(0, max(duration, 0))
        self.total_time.setText(format_time(duration / 1000))

    def handle_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self.play_next()
            return
        if self._restore_pending and status in (
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferedMedia,
        ):
            if self._restore_position_ms > 0:
                self.player.setPosition(self._restore_position_ms)
            if self._restore_autoplay:
                self.player.play()
                self.set_play_state(True)
            else:
                self.player.pause()
                self.set_play_state(False)
            self._restore_pending = False

    def closeEvent(self, event) -> None:
        try:
            self._save_playback_state()
            self.settings.sync()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    icon = build_app_icon()
    app.setWindowIcon(icon)
    window = PlayerWindow()
    window.setWindowIcon(icon)
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
