from __future__ import annotations

import sys
import time
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

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
    QEventLoop,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QIcon, QPolygonF, QLinearGradient, QPainterPath
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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
    QGraphicsOpacityEffect,
)

from mutagen import File as MutagenFile

from library import Album, Track, default_scan_path, scan_library, make_id

import json


@dataclass
class PlaylistData:
    id: str
    title: str
    icon_path: str
    track_paths: List[str]


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
    playRequested = Signal(int)
    deleteRequested = Signal(int)

    def __init__(self, rows=0, columns=0, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.hover_row = -1
        self.hover_col = -1
        self.playing_track_id: Optional[str] = None
        self.playing_active = False
        self.playlist_delete_enabled = False
        self._play_phase = 0.0
        self._play_anim = QPropertyAnimation(self, b"playPhase")
        self._play_anim.setDuration(2800)
        self._play_anim.setStartValue(0.0)
        self._play_anim.setEndValue(1.0)
        self._play_anim.setLoopCount(-1)
        self.setMouseTracking(True)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(24)

    def set_playing_track(self, track_id: Optional[str]) -> None:
        self.playing_track_id = track_id
        self._update_play_anim_state()
        self.viewport().update()

    def set_playing_active(self, active: bool) -> None:
        self.playing_active = active
        self._update_play_anim_state()

    def set_playlist_delete_enabled(self, enabled: bool) -> None:
        self.playlist_delete_enabled = bool(enabled)
        self.viewport().update()

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
            if row >= 0 and col == 4 and self.playlist_delete_enabled:
                icon_rect = self.action_icon_rect(row)
                if icon_rect.contains(pos):
                    self.deleteRequested.emit(row)
                    event.accept()
                    return
            if row >= 0 and col == 0 and row == self.hover_row:
                icon_rect = self.play_icon_rect(row)
                if icon_rect.contains(pos):
                    self.playRequested.emit(row)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        row = self.rowAt(int(event.position().y()))
        col = self.columnAt(int(event.position().x()))
        if row != self.hover_row or col != self.hover_col:
            self.hover_row = row
            self.hover_col = col
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hover_row != -1 or self.hover_col != -1:
            self.hover_row = -1
            self.hover_col = -1
            self.viewport().update()
        super().leaveEvent(event)

    def action_icon_rect(self, row: int) -> QRectF:
        index = self.model().index(row, 4)
        rect = self.visualRect(index)
        size = min(rect.height() - 10, rect.width() - 10, 16)
        size = max(10, size)
        center = rect.center()
        return QRectF(center.x() - size / 2, center.y() - size / 2, size, size)


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


class TrackActionDelegate(QStyledItemDelegate):
    def __init__(self, table: TrackTable) -> None:
        super().__init__(table)
        self.table = table

    def paint(self, painter, option, index) -> None:
        if index.column() != 4 or not self.table.playlist_delete_enabled:
            return
        icon_rect = self.table.action_icon_rect(index.row())
        hovered = self.table.hover_row == index.row() and self.table.hover_col == index.column()
        theme_mode = self.table.property("theme_mode") or "dark"
        base_color = QColor("#7a8088" if theme_mode == "light" else "#9aa0a9")
        if hovered:
            base_color = QColor("#ef4444")

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(base_color)

        lid_h = icon_rect.height() * 0.16
        body_w = icon_rect.width() * 0.6
        body_h = icon_rect.height() * 0.58
        body_x = icon_rect.center().x() - body_w / 2
        body_y = icon_rect.y() + lid_h + icon_rect.height() * 0.16
        painter.drawRoundedRect(QRectF(body_x, body_y, body_w, body_h), 1.2, 1.2)

        top_w = icon_rect.width() * 0.82
        top_h = max(1.0, lid_h)
        top_x = icon_rect.center().x() - top_w / 2
        top_y = icon_rect.y() + icon_rect.height() * 0.12
        painter.drawRoundedRect(QRectF(top_x, top_y, top_w, top_h), 1.0, 1.0)

        handle_w = icon_rect.width() * 0.28
        handle_h = icon_rect.height() * 0.08
        handle_x = icon_rect.center().x() - handle_w / 2
        handle_y = top_y - handle_h * 0.35
        painter.drawRoundedRect(QRectF(handle_x, handle_y, handle_w, handle_h), 1.0, 1.0)
        painter.restore()

TRANSLATIONS = {
    "en": {
        "app_title": "Enderlit Player",
        "my_library": "My Library",
        "search_library": "Search in library",
        "choose_folder": "Choose a music folder",
        "folder_path": "Folder path",
        "image_path": "Image path",
        "settings": "Settings",
        "browse": "Browse",
        "scan": "Scan Library",
        "albums": "Albums",
        "playlists": "Playlists",
        "theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "mix_button": "Random mix",
        "mix_hint": "Updates on request",
        "mix_refresh": "Pick mix",
        "found": "{count} found",
        "back_to_albums": "Back to albums",
        "edit_order": "Edit order",
        "finish_order": "Done",
        "move_up": "Up",
        "move_down": "Down",
        "search_playlists": "Search playlists",
        "create_playlist": "Create playlist",
        "delete_playlist": "Delete playlist",
        "playlist_name": "Playlist name",
        "playlist_icon": "Playlist icon",
        "choose_icon": "Choose icon",
        "change_icon": "Change icon",
        "add_tracks": "Add tracks",
        "remove_track": "Remove selected",
        "playlist_empty": "Playlist is empty",
        "playlist_meta": "Playlist  {tracks} tracks  {duration}",
        "playlist_card_meta": "{count} tracks",
        "create": "Create",
        "cancel": "Cancel",
        "add_selected": "Add selected",
        "select_tracks_title": "Add tracks to playlist",
        "no_tracks_to_add": "No tracks available. Scan your library first.",
        "playlist_name_required": "Enter playlist name.",
        "delete_playlist_title": "Delete playlist",
        "delete_playlist_body": "Delete playlist \"{name}\"?",
        "playlist_saved": "Saved",
        "latest_version_here": "Latest version here",
        "yes": "Yes",
        "no": "No",
        "ok": "OK",
        "apply": "Apply",
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
        "reorder_hint": "Change track number below and save",
        "reorder_hint_filtered": "Clear search to edit order by number",
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
        "folder_path": "Путь к папке",
        "image_path": "Путь к изображению",
        "settings": "Настройки",
        "browse": "Обзор",
        "scan": "Сканировать",
        "albums": "Альбомы",
        "playlists": "Плейлисты",
        "theme": "Тема",
        "theme_dark": "Темная",
        "theme_light": "Светлая",
        "mix_button": "Случайный микс",
        "mix_hint": "Обновляется по кнопке",
        "mix_refresh": "Подобрать",
        "found": "Найдено: {count}",
        "back_to_albums": "Назад к альбомам",
        "edit_order": "Редактировать порядок",
        "finish_order": "Готово",
        "move_up": "Вверх",
        "move_down": "Вниз",
        "search_playlists": "Искать плейлисты",
        "create_playlist": "Создать плейлист",
        "delete_playlist": "Удалить плейлист",
        "playlist_name": "Название плейлиста",
        "playlist_icon": "Иконка плейлиста",
        "choose_icon": "Выбрать иконку",
        "change_icon": "Сменить иконку",
        "add_tracks": "Добавить треки",
        "remove_track": "Убрать выбранный",
        "playlist_empty": "Плейлист пуст",
        "playlist_meta": "Плейлист  {tracks} треков  {duration}",
        "playlist_card_meta": "{count} треков",
        "create": "Создать",
        "cancel": "Отмена",
        "add_selected": "Добавить выбранные",
        "select_tracks_title": "Добавление треков в плейлист",
        "no_tracks_to_add": "Нет треков для добавления. Сначала просканируйте библиотеку.",
        "playlist_name_required": "Введите название плейлиста.",
        "delete_playlist_title": "Удалить плейлист",
        "delete_playlist_body": "Удалить плейлист \"{name}\"?",
        "playlist_saved": "Сохранено",
        "latest_version_here": "Актуальная версия тут",
        "yes": "Да",
        "no": "Нет",
        "ok": "ОК",
        "apply": "Применить",
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
        "reorder_hint": "Измените номер трека внизу и нажмите Сохранить",
        "reorder_hint_filtered": "Отключите поиск, чтобы менять порядок по номеру",
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
        self.order_edit_mode = False
        self.current_playlist: Optional[PlaylistData] = None
        self.library_mode = "albums"
        self.current_collection_kind = "album"

        self.settings = QSettings("EnderLit", "EnderLitPlayer")
        self.track_order_map = self._load_track_orders()
        self.language = self.settings.value("language", "ru", type=str)
        self.library_mode = self.settings.value("library_mode", "albums", type=str)
        if self.library_mode not in {"albums", "playlists"}:
            self.library_mode = "albums"
        self.theme = self.settings.value("theme", "dark", type=str)
        if self.theme not in {"dark", "light"}:
            self.theme = "dark"
        self.cover_style = self.settings.value("cover_style", "rounded", type=str)
        if self.cover_style not in {"rounded", "square"}:
            self.cover_style = "rounded"
        self.playlists: List[PlaylistData] = self._load_playlists()
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

    def _load_playlists(self) -> List[PlaylistData]:
        raw = self.settings.value("playlists", "")
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                raw = ""
        if isinstance(raw, list):
            data = raw
        else:
            if not isinstance(raw, str):
                raw = str(raw)
            if not raw:
                return []
            try:
                data = json.loads(raw)
            except Exception:
                return []
        if not isinstance(data, list):
            return []
        playlists: List[PlaylistData] = []
        seen_ids = set()
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            playlist_id = str(item.get("id") or make_id(f"playlist:{title}:{index}"))
            if playlist_id in seen_ids:
                playlist_id = make_id(f"{playlist_id}:{index}:{time.time_ns()}")
            seen_ids.add(playlist_id)
            icon_path = str(item.get("icon_path", "") or "")
            track_paths_raw = item.get("track_paths", [])
            if isinstance(track_paths_raw, list):
                track_paths = [str(path) for path in track_paths_raw if path]
            else:
                track_paths = []
            playlists.append(
                PlaylistData(
                    id=playlist_id,
                    title=title,
                    icon_path=icon_path,
                    track_paths=track_paths,
                )
            )
        return playlists

    def _save_playlists(self) -> None:
        payload = [
            {
                "id": playlist.id,
                "title": playlist.title,
                "icon_path": playlist.icon_path,
                "track_paths": list(playlist.track_paths),
            }
            for playlist in self.playlists
        ]
        try:
            self.settings.setValue("playlists", json.dumps(payload, ensure_ascii=False))
            self.settings.sync()
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

    def _update_library_mode_ui(self) -> None:
        albums_mode = self.library_mode == "albums"
        self.albums_tab_button.setChecked(albums_mode)
        self.playlists_tab_button.setChecked(not albums_mode)
        self.create_playlist_button.setVisible(not albums_mode)
        self.delete_playlist_button.setVisible(False)
        self.album_header_label.setText(self.t("albums") if albums_mode else self.t("playlists"))
        self.album_search.setPlaceholderText(
            self.t("search_albums") if albums_mode else self.t("search_playlists")
        )

    def set_library_mode(self, mode: str, preserve_selection: bool = False) -> None:
        if mode not in {"albums", "playlists"}:
            return
        if self.library_mode == mode and not preserve_selection:
            self._update_library_mode_ui()
            return
        self.library_mode = mode
        self.settings.setValue("library_mode", self.library_mode)
        self._update_library_mode_ui()
        if self.library_stack.currentIndex() == 1:
            if mode == "albums" and self.current_collection_kind == "playlist":
                self.show_library_view()
            if mode == "playlists" and self.current_collection_kind in {"album", "mix"}:
                self.show_library_view()
        self.populate_albums(preserve_selection=preserve_selection)

    def apply_language(self) -> None:
        self.setWindowTitle(self.t("app_title"))
        self.brand_label.setText(self.t("my_library"))
        self.search_input.setPlaceholderText(self.t("search_library"))
        self.path_input.setPlaceholderText(self.t("choose_folder"))
        self.settings_button.setText(self.t("settings"))
        self.browse_button.setText(self.t("browse"))
        self.scan_button.setText(self.t("scan"))
        self.albums_tab_button.setText(self.t("albums"))
        self.playlists_tab_button.setText(self.t("playlists"))
        self.create_playlist_button.setText(self.t("create_playlist"))
        self.delete_playlist_button.setText(self.t("delete_playlist"))
        self._update_library_mode_ui()
        self.detail_mix_refresh.setText(self.t("mix_refresh"))
        self.back_button.setText(self.t("back_to_albums"))
        self.detail_play.setText(self.t("play"))
        self.edit_order_button.setText(self.t("finish_order") if self.order_edit_mode else self.t("edit_order"))
        self.move_up_button.setText(self.t("move_up"))
        self.move_down_button.setText(self.t("move_down"))
        self.detail_playlist_add.setText(self.t("add_tracks"))
        self.detail_playlist_remove.setText(self.t("remove_track"))
        self.detail_playlist_delete.setText(self.t("delete_playlist"))
        self.detail_playlist_icon.setText(self.t("change_icon"))
        self.track_search.setPlaceholderText(self.t("search_tracks"))
        self.editor_title.setPlaceholderText(self.t("track_title"))
        self.editor_number.setPlaceholderText(self.t("track_number"))
        self.editor_artist.setPlaceholderText(self.t("artist"))
        self.editor_filename.setPlaceholderText(self.t("file_name"))
        self.editor_save.setText(self.t("save_changes"))
        self.volume_label.setText(self.t("volume"))
        self.latest_version_label.setText(self.t("latest_version_here"))
        self._update_volume_label(self.volume.value())
        self.loading_label.setText(self.t("loading"))
        self.track_table.setHorizontalHeaderLabels(
            [self.t("header_no"), self.t("header_title"), self.t("header_artist"), self.t("header_length"), ""]
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
            elif self.current_collection_kind == "playlist" and self.current_playlist:
                self.detail_title.setText(self.current_playlist.title)
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

        self.modal_overlay = QFrame(root)
        self.modal_overlay.setObjectName("ModalOverlay")
        self.modal_overlay.hide()
        modal_overlay_layout = QVBoxLayout(self.modal_overlay)
        modal_overlay_layout.setContentsMargins(28, 28, 28, 28)
        modal_overlay_layout.setAlignment(Qt.AlignCenter)

        self.modal_card = QFrame(self.modal_overlay)
        self.modal_card.setObjectName("ModalCard")
        modal_card_layout = QVBoxLayout(self.modal_card)
        modal_card_layout.setContentsMargins(18, 16, 18, 16)
        modal_card_layout.setSpacing(12)

        self.modal_title = QLabel("")
        self.modal_title.setObjectName("DetailTitle")
        self.modal_body_host = QWidget(self.modal_card)
        self.modal_body_layout = QVBoxLayout(self.modal_body_host)
        self.modal_body_layout.setContentsMargins(0, 0, 0, 0)
        self.modal_body_layout.setSpacing(10)
        self.modal_actions_host = QWidget(self.modal_card)
        self.modal_actions_layout = QHBoxLayout(self.modal_actions_host)
        self.modal_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.modal_actions_layout.setSpacing(8)

        modal_card_layout.addWidget(self.modal_title)
        modal_card_layout.addWidget(self.modal_body_host, 1)
        modal_card_layout.addWidget(self.modal_actions_host)
        modal_overlay_layout.addWidget(self.modal_card)

    def _init_player_icons(self, icon_size: int = 18) -> None:
        transport_color = "#e9e9e9" if self.theme == "dark" else "#232629"
        self.icon_play = self._make_icon("play", icon_size, "#0f0f0f")
        self.icon_pause = self._make_icon("pause", icon_size, "#0f0f0f")
        self.icon_prev = self._make_icon("prev", icon_size, transport_color)
        self.icon_next = self._make_icon("next", icon_size, transport_color)

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

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(8)
        self.albums_tab_button = QPushButton("Albums")
        self.albums_tab_button.setCheckable(True)
        self.albums_tab_button.setObjectName("TabButton")
        self.playlists_tab_button = QPushButton("Playlists")
        self.playlists_tab_button.setCheckable(True)
        self.playlists_tab_button.setObjectName("TabButton")
        self.create_playlist_button = QPushButton("Create playlist")
        self.create_playlist_button.setObjectName("GhostButton")
        self.delete_playlist_button = QPushButton("Delete playlist")
        self.delete_playlist_button.setObjectName("GhostButton")
        self.delete_playlist_button.hide()

        tabs_row.addWidget(self.albums_tab_button)
        tabs_row.addWidget(self.playlists_tab_button)
        tabs_row.addStretch(1)
        tabs_row.addWidget(self.create_playlist_button)
        tabs_wrap = QWidget()
        tabs_wrap.setLayout(tabs_row)

        self.album_count = QLabel("0 found")
        self.album_count.setObjectName("PanelMeta")
        self.album_search = QLineEdit()
        self.album_search.setPlaceholderText("Search albums")

        library_layout.addWidget(header_wrap)
        library_layout.addWidget(tabs_wrap)
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
        self.detail_playlist_add = QPushButton("Add tracks")
        self.detail_playlist_add.setObjectName("GhostButton")
        self.detail_playlist_add.setVisible(False)
        self.detail_playlist_remove = QPushButton("Remove selected")
        self.detail_playlist_remove.setObjectName("GhostButton")
        self.detail_playlist_remove.setVisible(False)
        self.detail_playlist_delete = QPushButton("Delete playlist")
        self.detail_playlist_delete.setObjectName("GhostButton")
        self.detail_playlist_delete.setVisible(False)
        self.detail_playlist_icon = QPushButton("Change icon")
        self.detail_playlist_icon.setObjectName("GhostButton")
        self.detail_playlist_icon.setVisible(False)

        text_col = QVBoxLayout()
        text_col.addWidget(self.detail_title)
        text_col.addWidget(self.detail_meta)
        text_col.addWidget(self.detail_play)
        text_col.addWidget(self.detail_mix_refresh)
        text_col.addWidget(self.detail_playlist_add)
        text_col.addWidget(self.detail_playlist_remove)
        text_col.addWidget(self.detail_playlist_delete)
        text_col.addWidget(self.detail_playlist_icon)
        text_wrap = QWidget()
        text_wrap.setLayout(text_col)

        album_header.addWidget(self.detail_cover)
        album_header.addWidget(text_wrap, 1)

        self.track_search = QLineEdit()
        self.track_search.setPlaceholderText("Search tracks")

        reorder_row = QHBoxLayout()
        reorder_row.setSpacing(8)
        self.reorder_hint = QLabel("Change track number below and save")
        self.reorder_hint.setObjectName("PanelMeta")
        self.edit_order_button = QPushButton("Edit order")
        self.edit_order_button.setObjectName("GhostButton")
        self.edit_order_button.setCheckable(True)
        self.move_up_button = QPushButton("Up")
        self.move_up_button.setObjectName("GhostButton")
        self.move_down_button = QPushButton("Down")
        self.move_down_button.setObjectName("GhostButton")
        reorder_row.addWidget(self.reorder_hint, 1)
        reorder_row.addWidget(self.edit_order_button)
        reorder_row.addWidget(self.move_up_button)
        reorder_row.addWidget(self.move_down_button)
        reorder_wrap = QWidget()
        reorder_wrap.setLayout(reorder_row)

        self.track_table = TrackTable(0, 5)
        self.track_table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Length", ""])
        self.track_table.setProperty("theme_mode", self.theme)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.track_table.setSelectionMode(QTableWidget.SingleSelection)
        self.track_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.track_table.setObjectName("TrackTable")
        self.track_table.setColumnWidth(0, 40)
        self.track_table.setColumnWidth(3, 70)
        self.track_table.setColumnWidth(4, 38)
        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.track_table.setShowGrid(False)
        self.track_table.setAlternatingRowColors(False)
        self.track_table.setItemDelegateForColumn(0, TrackNumberDelegate(self.track_table))
        self.track_table.setItemDelegateForColumn(4, TrackActionDelegate(self.track_table))
        self.track_table.setDragEnabled(False)
        self.track_table.setAcceptDrops(False)
        self.track_table.setDropIndicatorShown(False)
        self.track_table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.track_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

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
        detail_layout.addWidget(reorder_wrap)
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
        self.version_label = QLabel("ver 0.5.7")
        self.version_label.setObjectName("SubBrand")
        self.latest_version_label = QLabel("Latest version here")
        self.latest_version_label.setObjectName("SubBrand")
        self.latest_version_link = QLabel('<a href="https://github.com/endercodezz/enderlitplayer">GitHub</a>')
        self.latest_version_link.setObjectName("SubBrand")
        self.latest_version_link.setOpenExternalLinks(True)
        self.latest_version_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.latest_version_link.setCursor(Qt.PointingHandCursor)
        self.subbrand_label.setAlignment(Qt.AlignRight)
        self.version_label.setAlignment(Qt.AlignRight)
        self.latest_version_label.setAlignment(Qt.AlignRight)
        self.latest_version_link.setAlignment(Qt.AlignRight)
        brand_col.addStretch(1)
        brand_col.addWidget(self.subbrand_label)
        brand_col.addWidget(self.version_label)
        brand_col.addWidget(self.latest_version_label)
        brand_col.addWidget(self.latest_version_link)
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
        if self.theme == "light":
            colors = {
                "text": "#1f2937",
                "window": "#f2f4f8",
                "panel_bg": "#ffffff",
                "panel_border": "#d8dee8",
                "player_bg": "#ffffff",
                "meta_text": "#6b7280",
                "sub_text": "#8b95a5",
                "input_bg": "#f6f8fb",
                "input_border": "#d7dee8",
                "input_hover": "#bcc7d6",
                "btn_bg": "#eef2f7",
                "btn_border": "#d4dce8",
                "btn_hover": "#b9c5d6",
                "tab_bg": "#eef2f7",
                "tab_border": "#d4dce8",
                "primary_text": "#ffffff",
                "ghost_border": "#c8d2e0",
                "ghost_text": "#334155",
                "table_bg": "#ffffff",
                "table_border": "#dbe3ef",
                "album_item_hover": "#f1f5f9",
                "album_item_selected": "#eaf3ee",
                "header_bg": "#f7f9fc",
                "header_text": "#667085",
                "table_row_border": "#e6ebf2",
                "table_hover": "#f2f6fb",
                "table_selected": "#e8eef6",
                "cover_bg": "#eef2f7",
                "editor_bg": "#f8fafc",
                "slider_bg": "#d7deea",
                "slider_border": "#ffffff",
                "loading_bg": "rgba(238, 243, 249, 230)",
            }
        else:
            colors = {
                "text": "#e9e9e9",
                "window": "#0f0f0f",
                "panel_bg": "#121212",
                "panel_border": "#1a1a1a",
                "player_bg": "#101010",
                "meta_text": "#a0a0a0",
                "sub_text": "#8f8f8f",
                "input_bg": "#1a1a1a",
                "input_border": "#2a2a2a",
                "input_hover": "#303030",
                "btn_bg": "#1a1a1a",
                "btn_border": "#2a2a2a",
                "btn_hover": "#3a3a3a",
                "tab_bg": "#181818",
                "tab_border": "#2a2a2a",
                "primary_text": "#0f0f0f",
                "ghost_border": "#2e2e2e",
                "ghost_text": "#cfcfcf",
                "table_bg": "#131313",
                "table_border": "#1f1f1f",
                "album_item_hover": "#1b1b1b",
                "album_item_selected": "#1f1f1f",
                "header_bg": "#141414",
                "header_text": "#b5b5b5",
                "table_row_border": "#1f1f1f",
                "table_hover": "#1a1a1a",
                "table_selected": "#1f1f1f",
                "cover_bg": "#1a1a1a",
                "editor_bg": "#111111",
                "slider_bg": "#2a2a2a",
                "slider_border": "#0f0f0f",
                "loading_bg": "rgba(10, 10, 10, 220)",
            }
        self.setStyleSheet(
            f"""
            QWidget {{
              font-family: "Avenir Next", "Segoe UI", "Trebuchet MS", sans-serif;
              color: {colors["text"]};
            }}
            QMainWindow {{
              background: {colors["window"]};
            }}
            #Topbar, #Panel {{
              background: {colors["panel_bg"]};
              border-radius: 18px;
              border: 1px solid {colors["panel_border"]};
            }}
            #PlayerBar {{
              background: {colors["player_bg"]};
              border-radius: 18px;
              border: 1px solid {colors["panel_border"]};
            }}
            #Brand {{
              font-weight: 700;
            }}
            #PanelMeta {{
              color: {colors["meta_text"]};
              font-size: 12px;
            }}
            #SubBrand {{
              color: {colors["sub_text"]};
              font-size: 10px;
            }}
            #DetailTitle {{
              font-weight: 700;
            }}
            QLineEdit {{
              background: {colors["input_bg"]};
              border: 1px solid {colors["input_border"]};
              border-radius: 18px;
              padding: 8px 12px;
              color: {colors["text"]};
            }}
            QLineEdit:hover {{
              border: 1px solid {colors["input_hover"]};
            }}
            QComboBox {{
              background: {colors["input_bg"]};
              border: 1px solid {colors["input_border"]};
              border-radius: 18px;
              padding: 6px 10px;
              color: {colors["text"]};
            }}
            QComboBox::drop-down {{
              border: none;
              width: 18px;
            }}
            QComboBox QAbstractItemView {{
              background: {colors["input_bg"]};
              border: 1px solid {colors["input_border"]};
              color: {colors["text"]};
              selection-background-color: {colors["table_selected"]};
              selection-color: {colors["text"]};
              outline: none;
            }}
            QComboBox QAbstractItemView::item {{
              min-height: 24px;
              padding: 4px 8px;
            }}
            QPushButton {{
              background: {colors["btn_bg"]};
              border: 1px solid {colors["btn_border"]};
              border-radius: 18px;
              padding: 8px 14px;
              font-weight: 600;
            }}
            QPushButton:hover {{
              border: 1px solid {colors["btn_hover"]};
            }}
            #TabButton {{
              background: {colors["tab_bg"]};
              border: 1px solid {colors["tab_border"]};
              border-radius: 14px;
              padding: 7px 16px;
              min-width: 110px;
            }}
            #TabButton:checked {{
              background: #1db954;
              border: none;
              color: #0f0f0f;
            }}
            #PlayerBar QPushButton {{
              font-size: 16px;
              padding: 8px 16px;
              min-width: 44px;
              min-height: 36px;
            }}
            #PrimaryButton {{
              background: #1db954;
              color: {colors["primary_text"]};
              border: none;
            }}
            #PrimaryButton:hover {{
              background: #22c95f;
            }}
            #GhostButton {{
              background: transparent;
              border: 1px solid {colors["ghost_border"]};
              color: {colors["ghost_text"]};
            }}
            QListWidget, QTableWidget {{
              background: transparent;
              border: none;
            }}
            #TrackTable {{
              background: {colors["table_bg"]};
              border: 1px solid {colors["table_border"]};
              border-radius: 16px;
            }}
            #AlbumList::item {{
              background: transparent;
              border: 1px solid transparent;
              border-radius: 12px;
              padding: 6px;
              margin: 4px;
            }}
            #AlbumList::item:hover {{
              background: {colors["album_item_hover"]};
            }}
            #AlbumList::item:selected {{
              border: 1px solid #1db954;
              background: {colors["album_item_selected"]};
            }}
            QHeaderView::section {{
              background: {colors["header_bg"]};
              color: {colors["header_text"]};
              padding: 6px;
              border: none;
              border-bottom: 1px solid {colors["table_row_border"]};
            }}
            QTableWidget::item {{
              padding: 10px 12px;
              border-bottom: 1px solid {colors["table_row_border"]};
            }}
            #TrackTable::item:hover {{
              background: {colors["table_hover"]};
            }}
            #TrackTable::item:selected {{
              background: {colors["table_selected"]};
            }}
            #CoverLabel {{
              background: {colors["cover_bg"]};
              border-radius: 10px;
            }}
            #DetailCover {{
              background: {colors["cover_bg"]};
              border-radius: 14px;
            }}
            #EditorFrame {{
              background: {colors["editor_bg"]};
              border-radius: 16px;
              border: 1px solid {colors["table_border"]};
            }}
            QSlider::groove:horizontal {{
              height: 5px;
              background: {colors["slider_bg"]};
              border-radius: 999px;
            }}
            QSlider::handle:horizontal {{
              width: 14px;
              background: #1db954;
              border: 1px solid {colors["slider_border"]};
              border-radius: 7px;
              margin: -5px 0;
            }}
            #Progress::sub-page:horizontal {{
              background: #1db954;
              border-radius: 999px;
            }}
            #Progress::add-page:horizontal {{
              background: {colors["slider_bg"]};
              border-radius: 999px;
            }}
            #Volume::sub-page:horizontal {{
              background: #1db954;
              border-radius: 999px;
            }}
            #Volume::add-page:horizontal {{
              background: {colors["slider_bg"]};
              border-radius: 999px;
            }}
            #LoadingOverlay {{
              background: {colors["loading_bg"]};
              border-radius: 22px;
            }}
            #ModalOverlay {{
              background: rgba(0, 0, 0, 120);
              border-radius: 20px;
            }}
            #ModalCard {{
              background: {colors["panel_bg"]};
              border-radius: 18px;
              border: 1px solid {colors["panel_border"]};
            }}
            """
        )

    def _connect_signals(self) -> None:
        self.scan_button.clicked.connect(self.scan_library)
        self.browse_button.clicked.connect(self.choose_folder)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.albums_tab_button.clicked.connect(lambda: self.set_library_mode("albums"))
        self.playlists_tab_button.clicked.connect(lambda: self.set_library_mode("playlists"))
        self.create_playlist_button.clicked.connect(self.create_playlist)
        self.album_list.itemSelectionChanged.connect(self.on_album_selected)
        self.album_list.playAlbumRequested.connect(self.on_album_quick_play)
        self.album_search.textChanged.connect(self.filter_albums)
        self.track_search.textChanged.connect(self.filter_tracks)
        self.track_table.cellDoubleClicked.connect(self.play_selected_track)
        self.track_table.itemSelectionChanged.connect(self.on_track_selected)
        self.track_table.playRequested.connect(self.on_track_quick_play)
        self.track_table.deleteRequested.connect(lambda row: self.remove_selected_from_playlist(row))
        self.edit_order_button.toggled.connect(self.on_order_edit_toggled)
        self.move_up_button.clicked.connect(lambda: self.move_selected_track(-1))
        self.move_down_button.clicked.connect(lambda: self.move_selected_track(1))
        self.play_button.clicked.connect(self.toggle_play)
        self.next_button.clicked.connect(self.play_next)
        self.prev_button.clicked.connect(self.play_prev)
        self.volume.valueChanged.connect(self.update_volume)
        self.progress.sliderMoved.connect(self.seek)
        self.back_button.clicked.connect(self.show_library_view)
        self.detail_play.clicked.connect(self.play_album)
        self.detail_mix_refresh.clicked.connect(self.refresh_random_mix)
        self.detail_playlist_add.clicked.connect(self.add_tracks_to_current_playlist)
        self.detail_playlist_remove.clicked.connect(lambda: self.remove_selected_from_playlist())
        self.detail_playlist_delete.clicked.connect(self.delete_selected_playlist)
        self.detail_playlist_icon.clicked.connect(self.change_current_playlist_icon)
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

    def set_theme(self, theme: str) -> None:
        if theme not in {"dark", "light"}:
            return
        if self.theme == theme:
            return
        self.theme = theme
        self.settings.setValue("theme", self.theme)
        self._apply_style()
        self._apply_cover_label_style()
        self.track_table.setProperty("theme_mode", self.theme)
        self.track_table.viewport().update()
        icon_size = max(14, int(16 * max(0.65, min(1.0, self.width() / 1800))))
        self._init_player_icons(icon_size)
        self.set_play_state(self.player.playbackState() == QMediaPlayer.PlayingState)

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
        background = "#1a1a1a" if self.theme == "dark" else "#eef2f7"
        self.cover_label.setStyleSheet(f"background: {background}; border-radius: {now_radius}px;")
        self.detail_cover.setStyleSheet(f"background: {background}; border-radius: {detail_radius}px;")

    def open_settings_dialog(self) -> None:
        content = QWidget(self.modal_body_host)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignLeft)

        language_combo = QComboBox(content)
        language_combo.addItem("English", "en")
        language_combo.addItem("Русский", "ru")
        language_combo.setCurrentIndex(0 if self.language == "en" else 1)

        theme_combo = QComboBox(content)
        theme_combo.addItem(self.t("theme_dark"), "dark")
        theme_combo.addItem(self.t("theme_light"), "light")
        theme_combo.setCurrentIndex(0 if self.theme == "dark" else 1)

        covers_combo = QComboBox(content)
        if self.language == "en":
            covers_combo.addItem("Rounded", "rounded")
            covers_combo.addItem("Square", "square")
        else:
            covers_combo.addItem("Скругленные", "rounded")
            covers_combo.addItem("Квадратные", "square")
        covers_combo.setCurrentIndex(0 if self.cover_style == "rounded" else 1)

        form.addRow("Language" if self.language == "en" else "Язык", language_combo)
        form.addRow(self.t("theme"), theme_combo)
        form.addRow("Cover style" if self.language == "en" else "Вид обложек", covers_combo)
        layout.addLayout(form)

        action = self.run_inline_modal(
            self.t("settings"),
            content,
            [
                (self.t("cancel"), "cancel", "GhostButton"),
                (self.t("apply"), "apply", "PrimaryButton"),
            ],
        )
        if action != "apply":
            return

        selected_language = language_combo.currentData()
        selected_theme = theme_combo.currentData()
        self.set_theme(selected_theme)
        self.set_language(selected_language)
        self.set_cover_style(covers_combo.currentData())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.loading_overlay.setGeometry(self.centralWidget().rect())
        self.modal_overlay.setGeometry(self.centralWidget().rect())
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
            if self.current_collection_kind == "playlist" and self.library_mode != "playlists":
                return
            if self.current_collection_kind in {"album", "mix"} and self.library_mode != "albums":
                return
            self.show_album_view()

    def show_loading(self, show: bool) -> None:
        self.loading_overlay.setVisible(show)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def run_inline_modal(
        self,
        title: str,
        body_widget: QWidget,
        actions: List[tuple[str, str, str]],
    ) -> str:
        self.modal_title.setText(title)
        self._clear_layout(self.modal_body_layout)
        self._clear_layout(self.modal_actions_layout)
        self.modal_body_layout.addWidget(body_widget)
        self.modal_actions_layout.addStretch(1)

        result = {"action": ""}
        loop = QEventLoop(self)

        def close_with(action_key: str) -> None:
            result["action"] = action_key
            self.modal_overlay.hide()
            loop.quit()

        for text, action_key, object_name in actions:
            button = QPushButton(text, self.modal_actions_host)
            if object_name:
                button.setObjectName(object_name)
            button.clicked.connect(lambda _checked=False, key=action_key: close_with(key))
            self.modal_actions_layout.addWidget(button)

        self.modal_card.setMaximumWidth(max(420, int(self.width() * 0.64)))
        self.modal_card.setMinimumWidth(max(340, int(self.width() * 0.38)))
        self.modal_card.setMaximumHeight(max(260, int(self.height() * 0.78)))
        self.modal_overlay.setGeometry(self.centralWidget().rect())
        self.modal_overlay.show()
        self.modal_overlay.raise_()
        loop.exec()
        return result["action"]

    def show_inline_message(self, title: str, body: str) -> None:
        content = QWidget(self.modal_body_host)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        message_label = QLabel(body, content)
        message_label.setWordWrap(True)
        message_label.setObjectName("PanelMeta")
        content_layout.addWidget(message_label)
        self.run_inline_modal(
            title,
            content,
            [(self.t("ok"), "ok", "PrimaryButton")],
        )

    def ask_inline_confirmation(self, title: str, body: str) -> bool:
        content = QWidget(self.modal_body_host)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        message_label = QLabel(body, content)
        message_label.setWordWrap(True)
        message_label.setObjectName("PanelMeta")
        content_layout.addWidget(message_label)
        action = self.run_inline_modal(
            title,
            content,
            [
                (self.t("no"), "no", "GhostButton"),
                (self.t("yes"), "yes", "PrimaryButton"),
            ],
        )
        return action == "yes"

    def ask_inline_text(
        self,
        title: str,
        label_text: str,
        initial_value: str = "",
    ) -> str:
        content = QWidget(self.modal_body_host)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(label_text, content)
        label.setObjectName("PanelMeta")
        edit = QLineEdit(content)
        edit.setText(initial_value)
        content_layout.addWidget(label)
        content_layout.addWidget(edit)
        action = self.run_inline_modal(
            title,
            content,
            [
                (self.t("cancel"), "cancel", "GhostButton"),
                (self.t("apply"), "apply", "PrimaryButton"),
            ],
        )
        if action != "apply":
            return ""
        return edit.text().strip()

    def choose_folder(self) -> None:
        folder = self.ask_inline_text(
            self.t("choose_folder"),
            self.t("folder_path"),
            self.path_input.text().strip(),
        )
        if folder:
            self.path_input.setText(folder)
            self.settings.setValue("library_path", folder)

    def scan_library(self) -> None:
        path = self.path_input.text().strip()
        if not path:
            self.show_inline_message(self.t("missing_folder_title"), self.t("missing_folder_body"))
            return
        self.settings.setValue("library_path", path)

        self.show_loading(True)
        self.scan_thread = QThread(self)
        self.scan_worker = ScanWorker(path)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_worker.failed.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def on_scan_failed(self, message: str) -> None:
        self.show_loading(False)
        if message == "folder_not_found":
            body = self.t("folder_not_found")
        else:
            body = self.t("scan_failed_body")
        self.show_inline_message(self.t("scan_failed_title"), body)

    def on_scan_finished(self, albums: List[Album]) -> None:
        self.show_loading(False)
        self.albums = albums
        for album in self.albums:
            self.apply_saved_order(album)
        self.normalize_playlists()
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

    def on_order_edit_toggled(self, checked: bool) -> None:
        self.order_edit_mode = bool(checked)
        self.edit_order_button.setText(self.t("finish_order") if self.order_edit_mode else self.t("edit_order"))
        self.populate_tracks()

    def move_selected_track(self, delta: int) -> None:
        if not self.current_album or not self.order_edit_mode or self.track_filter:
            return
        selected_items = self.track_table.selectedItems()
        if not selected_items:
            return
        row = selected_items[0].row()
        target_row = row + delta
        if target_row < 0 or target_row >= len(self.current_album.tracks):
            return
        tracks = self.current_album.tracks
        moved = tracks.pop(row)
        tracks.insert(target_row, moved)
        self.current_album.tracks = tracks

        if self.current_collection_kind == "playlist" and self.current_playlist:
            self.current_playlist.track_paths = [track.path for track in tracks]
            self._save_playlists()
            if self.playing_album and self.playing_album.id == self.current_playlist.id:
                self.playing_album = self.build_playlist_album(self.current_playlist)
        else:
            for index, track in enumerate(self.current_album.tracks, start=1):
                track.track_no = index
            self.track_order_map[self.current_album.id] = [track.path for track in self.current_album.tracks]
            self._save_track_orders()
        self.populate_tracks()
        self.track_table.selectRow(target_row)

    def populate_albums(self, preserve_selection: bool = False) -> None:
        current_id = None
        if preserve_selection and self.current_album:
            current_id = self.current_album.id
        elif preserve_selection:
            current_item = self.album_list.currentItem()
            if current_item:
                current_id = current_item.data(Qt.UserRole)
        self.album_list.blockSignals(True)
        self.album_list.clear()
        query = self.album_search.text().strip().lower()
        if self.library_mode == "albums":
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
        else:
            filtered_playlists = [
                playlist
                for playlist in self.playlists
                if not query or query in playlist.title.lower()
            ]
            self.album_count.setText(self.t("found").format(count=len(filtered_playlists)))
            for playlist in filtered_playlists:
                playlist_tracks = self.resolve_playlist_tracks(playlist)
                item = QListWidgetItem()
                item.setText(
                    f"{playlist.title}\n{self.t('playlist_card_meta').format(count=len(playlist_tracks))}".strip()
                )
                item.setIcon(QIcon(self.playlist_icon_pixmap(playlist, 140)))
                item.setData(Qt.UserRole, playlist.id)
                item.setSizeHint(QSize(160, 200))
                self.album_list.addItem(item)
        if current_id:
            for index in range(self.album_list.count()):
                item = self.album_list.item(index)
                if item.data(Qt.UserRole) == current_id:
                    self.album_list.setCurrentItem(item)
                    break
        self.album_list.blockSignals(False)
        self._update_library_mode_ui()
        self.update_album_grid()

    def _cover_radius(self, size: int) -> float:
        if self.cover_style == "square":
            return 0.0
        return max(6.0, size * 0.085)

    def album_pixmap(self, album: Album, size: int) -> QPixmap:
        radius = self._cover_radius(size)
        if album.id == self.mix_album_id:
            return rounded_pixmap(build_mix_cover(size), radius)
        if album.id.startswith("playlist_"):
            playlist = next((pl for pl in self.playlists if pl.id == album.id), None)
            if playlist:
                return self.playlist_icon_pixmap(playlist, size)

        source = QPixmap()
        if album.cover_bytes:
            source.loadFromData(album.cover_bytes)
        if source.isNull() and album.cover_path and Path(album.cover_path).exists():
            source = QPixmap(album.cover_path)
        if source.isNull():
            source = build_placeholder(album.title, size)
        scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        return rounded_pixmap(scaled, radius)

    def all_tracks_by_path(self) -> Dict[str, Track]:
        tracks: Dict[str, Track] = {}
        for album in self.albums:
            for track in album.tracks:
                tracks[track.path] = track
        return tracks

    def resolve_playlist_tracks(self, playlist: PlaylistData) -> List[Track]:
        by_path = self.all_tracks_by_path()
        resolved: List[Track] = []
        seen_paths = set()
        for path in playlist.track_paths:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            track = by_path.get(path)
            if track:
                resolved.append(track)
        return resolved

    def normalize_playlists(self) -> None:
        by_path = self.all_tracks_by_path()
        changed = False
        for playlist in self.playlists:
            cleaned_paths = []
            seen_paths = set()
            for path in playlist.track_paths:
                if path in seen_paths or path not in by_path:
                    changed = True
                    continue
                seen_paths.add(path)
                cleaned_paths.append(path)
            if cleaned_paths != playlist.track_paths:
                playlist.track_paths = cleaned_paths
                changed = True
        if changed:
            self._save_playlists()

    def playlist_icon_pixmap(self, playlist: PlaylistData, size: int) -> QPixmap:
        radius = self._cover_radius(size)
        source = QPixmap()
        if playlist.icon_path and Path(playlist.icon_path).exists():
            source = QPixmap(playlist.icon_path)
        if source.isNull():
            playlist_paths = set(playlist.track_paths)
            for album in self.albums:
                if not any(track.path in playlist_paths for track in album.tracks):
                    continue
                if album.cover_bytes:
                    source.loadFromData(album.cover_bytes)
                if source.isNull() and album.cover_path and Path(album.cover_path).exists():
                    source = QPixmap(album.cover_path)
                if not source.isNull():
                    break
        if source.isNull():
            source = build_placeholder(playlist.title, size)
        scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        return rounded_pixmap(scaled, radius)

    def build_playlist_album(self, playlist: PlaylistData) -> Album:
        tracks = self.resolve_playlist_tracks(playlist)
        duration = sum(track.duration for track in tracks)
        cover_path = playlist.icon_path if playlist.icon_path and Path(playlist.icon_path).exists() else None
        return Album(
            id=playlist.id,
            title=playlist.title,
            artist="Various Artists",
            year="",
            tracks=tracks,
            duration=duration,
            cover_path=cover_path,
            cover_bytes=None,
            cover_mime=None,
        )

    def on_album_selected(self) -> None:
        selected_items = self.album_list.selectedItems()
        if not selected_items:
            return
        album_id = selected_items[0].data(Qt.UserRole)
        if self.library_mode == "playlists":
            playlist = next((pl for pl in self.playlists if pl.id == album_id), None)
            if playlist:
                self.open_playlist(playlist)
            return
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
        if self.library_mode == "playlists":
            playlist = next((pl for pl in self.playlists if pl.id == album_id), None)
            if not playlist:
                return
            tracks = self.resolve_playlist_tracks(playlist)
            if not tracks:
                return
            self.current_playlist = playlist
            self.start_track(tracks[0], self.build_playlist_album(playlist))
            return
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
        self.order_edit_mode = False
        self.current_collection_kind = "mix" if album.id == self.mix_album_id else "album"
        self.current_playlist = None
        self.current_album = album
        if album.id == self.mix_album_id:
            self.detail_title.setText(self.t("mix_button"))
            self.detail_mix_refresh.setVisible(True)
        else:
            self.detail_title.setText(album.title)
            self.detail_mix_refresh.setVisible(False)
        self.detail_playlist_add.setVisible(False)
        self.detail_playlist_remove.setVisible(False)
        self.detail_playlist_delete.setVisible(False)
        self.detail_playlist_icon.setVisible(False)
        self.refresh_album_metadata()
        self.track_filter = self.track_search.text().strip().lower()
        self.populate_tracks()
        self.update_cover()
        self.show_album_view()

    def open_playlist(self, playlist: PlaylistData) -> None:
        self.order_edit_mode = False
        self.current_collection_kind = "playlist"
        self.current_playlist = playlist
        self.current_album = self.build_playlist_album(playlist)
        self.detail_title.setText(playlist.title)
        self.detail_mix_refresh.setVisible(False)
        self.detail_playlist_add.setVisible(True)
        self.detail_playlist_remove.setVisible(False)
        self.detail_playlist_delete.setVisible(True)
        self.detail_playlist_icon.setVisible(True)
        self.refresh_album_metadata()
        self.track_filter = self.track_search.text().strip().lower()
        self.populate_tracks()
        self.update_cover()
        self.show_album_view()

    def _select_image_file(self) -> str:
        file_path = self.ask_inline_text(
            self.t("choose_icon"),
            self.t("image_path"),
        )
        return file_path or ""

    def create_playlist(self) -> None:
        content = QWidget(self.modal_body_host)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignLeft)

        name_input = QLineEdit(content)
        icon_input = QLineEdit(content)
        icon_input.setReadOnly(True)
        choose_icon = QPushButton(self.t("choose_icon"), content)
        choose_icon.setObjectName("GhostButton")

        icon_row = QHBoxLayout()
        icon_row.addWidget(icon_input, 1)
        icon_row.addWidget(choose_icon)
        icon_wrap = QWidget(content)
        icon_wrap.setLayout(icon_row)

        form.addRow(self.t("playlist_name"), name_input)
        form.addRow(self.t("playlist_icon"), icon_wrap)
        layout.addLayout(form)

        def on_choose_icon() -> None:
            icon_path = self._select_image_file()
            if icon_path:
                icon_input.setText(icon_path)

        choose_icon.clicked.connect(on_choose_icon)
        action = self.run_inline_modal(
            self.t("create_playlist"),
            content,
            [
                (self.t("cancel"), "cancel", "GhostButton"),
                (self.t("create"), "create", "PrimaryButton"),
            ],
        )
        if action != "create":
            return

        playlist_name = name_input.text().strip()
        if not playlist_name:
            self.show_inline_message(self.t("missing_fields_title"), self.t("playlist_name_required"))
            return

        icon_path = icon_input.text().strip()
        playlist_id = f"playlist_{make_id(f'{playlist_name}:{time.time_ns()}')}"
        playlist = PlaylistData(
            id=playlist_id,
            title=playlist_name,
            icon_path=icon_path,
            track_paths=[],
        )
        self.playlists.append(playlist)
        self.current_playlist = playlist
        self._save_playlists()
        self.set_library_mode("playlists", preserve_selection=False)
        self.populate_albums()
        for row in range(self.album_list.count()):
            item = self.album_list.item(row)
            if item.data(Qt.UserRole) == playlist.id:
                self.album_list.setCurrentItem(item)
                break

    def delete_selected_playlist(self) -> None:
        playlist_id = self.current_playlist.id if self.current_playlist else None
        if not playlist_id:
            selected = self.album_list.currentItem()
            if selected:
                playlist_id = selected.data(Qt.UserRole)
        if not playlist_id:
            return
        playlist = next((pl for pl in self.playlists if pl.id == playlist_id), None)
        if not playlist:
            return
        confirmed = self.ask_inline_confirmation(
            self.t("delete_playlist_title"),
            self.t("delete_playlist_body").format(name=playlist.title),
        )
        if not confirmed:
            return
        self.playlists = [pl for pl in self.playlists if pl.id != playlist.id]
        if self.current_playlist and self.current_playlist.id == playlist.id:
            self.current_playlist = None
            if self.current_collection_kind == "playlist":
                self.current_album = None
                self.current_collection_kind = "album"
        if self.playing_album and self.playing_album.id == playlist.id:
            fallback = self._find_track_by_path(self.current_track.path) if self.current_track else None
            self.playing_album = fallback[1] if fallback else None
            self.update_now_playing_cover()
        self._save_playlists()
        self.set_library_mode("playlists")
        self.show_library_view()
        self.populate_albums()

    def change_current_playlist_icon(self) -> None:
        if not self.current_playlist:
            return
        icon_path = self._select_image_file()
        if not icon_path:
            return
        self.current_playlist.icon_path = icon_path
        if self.current_album and self.current_album.id == self.current_playlist.id:
            self.current_album.cover_path = icon_path
        if self.playing_album and self.playing_album.id == self.current_playlist.id:
            self.playing_album.cover_path = icon_path
            self.update_now_playing_cover()
        self._save_playlists()
        self.update_cover()
        self.update_album_list_item(self.current_playlist)

    def add_tracks_to_current_playlist(self) -> None:
        if not self.current_playlist:
            return
        available_tracks: List[tuple[Track, str]] = []
        for album in self.albums:
            for track in album.tracks:
                available_tracks.append((track, album.title))
        if not available_tracks:
            self.show_inline_message(self.t("create_playlist"), self.t("no_tracks_to_add"))
            return

        available_tracks.sort(key=lambda item: (item[0].artist.lower(), item[0].title.lower()))
        existing_paths = set(self.current_playlist.track_paths)

        content = QWidget(self.modal_body_host)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        content.setMinimumSize(560, 360)

        search_input = QLineEdit(content)
        search_input.setPlaceholderText(self.t("search_tracks"))
        track_list = QListWidget(content)
        track_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        track_list.setAlternatingRowColors(False)

        for track, album_title in available_tracks:
            item = QListWidgetItem(f"{track.artist} — {track.title}  •  {album_title}")
            item.setData(Qt.UserRole, track.path)
            if track.path in existing_paths:
                item.setForeground(QColor("#7b7b7b"))
            track_list.addItem(item)

        def on_search_changed() -> None:
            query = search_input.text().strip().lower()
            for index in range(track_list.count()):
                item = track_list.item(index)
                item.setHidden(bool(query and query not in item.text().lower()))

        search_input.textChanged.connect(on_search_changed)

        layout.addWidget(search_input)
        layout.addWidget(track_list, 1)
        action = self.run_inline_modal(
            self.t("select_tracks_title"),
            content,
            [
                (self.t("cancel"), "cancel", "GhostButton"),
                (self.t("add_selected"), "add", "PrimaryButton"),
            ],
        )
        if action != "add":
            return

        selected_paths = []
        for item in track_list.selectedItems():
            path = item.data(Qt.UserRole)
            if not path or path in existing_paths:
                continue
            existing_paths.add(path)
            selected_paths.append(path)
        if not selected_paths:
            return
        self.current_playlist.track_paths.extend(selected_paths)
        self._save_playlists()
        self.current_album = self.build_playlist_album(self.current_playlist)
        if self.playing_album and self.playing_album.id == self.current_playlist.id:
            self.playing_album = self.build_playlist_album(self.current_playlist)
        self.refresh_album_metadata()
        self.populate_tracks()
        self.update_album_list_item(self.current_playlist)

    def remove_selected_from_playlist(self, row: Optional[int] = None) -> None:
        if not self.current_playlist or not self.current_album:
            return
        if row is None:
            selected_items = self.track_table.selectedItems()
            if not selected_items:
                return
            row = selected_items[0].row()
        item = self.track_table.item(row, 0)
        if not item:
            return
        track_id = item.data(Qt.UserRole)
        track = next((t for t in self.current_album.tracks if t.id == track_id), None)
        if not track:
            return
        removed = False
        updated_paths = []
        for path in self.current_playlist.track_paths:
            if not removed and path == track.path:
                removed = True
                continue
            updated_paths.append(path)
        if not removed:
            return
        self.current_playlist.track_paths = updated_paths
        self._save_playlists()
        self.current_album = self.build_playlist_album(self.current_playlist)
        if self.playing_album and self.playing_album.id == self.current_playlist.id:
            self.playing_album = self.build_playlist_album(self.current_playlist)
        self.refresh_album_metadata()
        self.populate_tracks()
        self.update_album_list_item(self.current_playlist)

    def populate_tracks(self) -> None:
        self.track_table.setRowCount(0)
        if not self.current_album:
            return
        is_mix = self.current_album.id == self.mix_album_id
        is_playlist = self.current_collection_kind == "playlist"
        can_reorder = not is_mix and not bool(self.track_filter) and len(self.current_album.tracks) > 1
        tracks = self.current_album.tracks
        if self.track_filter:
            tracks = [
                track
                for track in tracks
                if self.track_filter in f"{track.title} {track.artist}".lower()
            ]
            if is_mix:
                self.reorder_hint.setText(self.t("mix_hint"))
            else:
                self.reorder_hint.setText(self.t("reorder_hint_filtered"))
        else:
            if is_mix:
                self.reorder_hint.setText(self.t("mix_hint"))
            else:
                self.reorder_hint.setText(self.t("reorder_hint"))

        if not can_reorder and self.order_edit_mode:
            self.order_edit_mode = False

        self.edit_order_button.blockSignals(True)
        self.edit_order_button.setEnabled(can_reorder)
        self.edit_order_button.setChecked(self.order_edit_mode)
        self.edit_order_button.setText(self.t("finish_order") if self.order_edit_mode else self.t("edit_order"))
        self.edit_order_button.blockSignals(False)
        self.move_up_button.setVisible(self.order_edit_mode)
        self.move_down_button.setVisible(self.order_edit_mode)
        self.move_up_button.setEnabled(False)
        self.move_down_button.setEnabled(False)

        self.editor_frame.setEnabled(not is_mix)
        self.track_table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.track_table.setDragEnabled(False)
        self.track_table.setAcceptDrops(False)
        self.track_table.set_playlist_delete_enabled(is_playlist)
        self.track_table.setColumnHidden(4, not is_playlist)
        self.detail_playlist_remove.setEnabled(False)
        self.detail_playlist_delete.setVisible(is_playlist)

        self.track_table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            number_value = row + 1 if is_mix or is_playlist else (track.track_no or row + 1)
            number_item = QTableWidgetItem(str(number_value))
            title_item = QTableWidgetItem(track.title)
            artist_item = QTableWidgetItem(track.artist)
            length_item = QTableWidgetItem(format_time(track.duration))
            number_item.setData(Qt.UserRole, track.id)
            self.track_table.setItem(row, 0, number_item)
            self.track_table.setItem(row, 1, title_item)
            self.track_table.setItem(row, 2, artist_item)
            self.track_table.setItem(row, 3, length_item)
            action_item = QTableWidgetItem("")
            action_item.setData(Qt.UserRole, track.id)
            action_item.setTextAlignment(Qt.AlignCenter)
            action_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.track_table.setItem(row, 4, action_item)
        if self.current_album and self.current_track and self.playing_album == self.current_album:
            self.track_table.set_playing_track(self.current_track.id)
        else:
            self.track_table.set_playing_track(None)
        self.on_track_selected()

    def on_track_selected(self) -> None:
        items = self.track_table.selectedItems()
        if not items:
            self.selected_track = None
            self.editor_number.setText("")
            self.editor_title.setText("")
            self.editor_artist.setText("")
            self.editor_filename.setText("")
            self.move_up_button.setEnabled(False)
            self.move_down_button.setEnabled(False)
            if hasattr(self, "detail_playlist_remove"):
                self.detail_playlist_remove.setEnabled(False)
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
        if self.current_collection_kind == "playlist":
            self.editor_number.setText(str(row + 1))
        else:
            self.editor_number.setText(str(track.track_no) if track.track_no else "")
        self.editor_title.setText(track.title)
        self.editor_artist.setText(track.artist)
        self.editor_filename.setText(Path(track.path).name)
        can_move = self.order_edit_mode and not self.track_filter and self.current_album is not None
        if can_move:
            self.move_up_button.setEnabled(row > 0)
            self.move_down_button.setEnabled(row < len(self.current_album.tracks) - 1)
        else:
            self.move_up_button.setEnabled(False)
            self.move_down_button.setEnabled(False)
        if hasattr(self, "detail_playlist_remove"):
            self.detail_playlist_remove.setEnabled(self.current_collection_kind == "playlist")

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
        if not self.current_track:
            return
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
        if self.order_edit_mode:
            self.order_edit_mode = False
        self.edit_order_button.blockSignals(True)
        self.edit_order_button.setChecked(False)
        self.edit_order_button.setText(self.t("edit_order"))
        self.edit_order_button.blockSignals(False)
        self.move_up_button.setVisible(False)
        self.move_down_button.setVisible(False)
        self.move_up_button.setEnabled(False)
        self.move_down_button.setEnabled(False)
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
            self.show_inline_message(self.t("missing_fields_title"), self.t("missing_fields_body"))
            return

        track = self.selected_track
        old_path = track.path
        original_path = Path(track.path)
        new_path = Path(new_filename)
        if new_path.suffix == "":
            new_path = new_path.with_suffix(original_path.suffix)
        if new_path.suffix.lower() != original_path.suffix.lower():
            self.show_inline_message(self.t("invalid_extension_title"), self.t("invalid_extension_body"))
            return
        if new_path.name != original_path.name:
            candidate = original_path.with_name(new_path.name)
            if candidate.exists():
                self.show_inline_message(self.t("file_exists_title"), self.t("file_exists_body"))
                return
            try:
                original_path.rename(candidate)
            except Exception:
                self.show_inline_message(self.t("rename_failed_title"), self.t("rename_failed_body"))
                return
            track.path = str(candidate)
            orders_changed = False
            for album_id, order_list in list(self.track_order_map.items()):
                updated = [track.path if path == old_path else path for path in order_list]
                if updated != order_list:
                    self.track_order_map[album_id] = updated
                    orders_changed = True
            if orders_changed:
                self._save_track_orders()
            playlist_changed = False
            for playlist in self.playlists:
                updated_paths = [track.path if path == old_path else path for path in playlist.track_paths]
                if updated_paths != playlist.track_paths:
                    playlist.track_paths = updated_paths
                    playlist_changed = True
            if playlist_changed:
                self._save_playlists()

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
            self.show_inline_message(self.t("tag_update_failed_title"), self.t("tag_update_failed_body"))
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
            if self.current_collection_kind == "playlist" and self.current_playlist:
                playlist_tracks = list(self.current_album.tracks)
                try:
                    current_index = next(i for i, item in enumerate(playlist_tracks) if item.id == track.id)
                except StopIteration:
                    current_index = -1
                if current_index >= 0:
                    moved = playlist_tracks.pop(current_index)
                    target_index = max(0, min(len(playlist_tracks), new_number - 1))
                    playlist_tracks.insert(target_index, moved)
                    self.current_album.tracks = playlist_tracks
                    self.current_playlist.track_paths = [item.path for item in playlist_tracks]
                    self._save_playlists()
                    if self.playing_album and self.playing_album.id == self.current_playlist.id:
                        self.playing_album = self.build_playlist_album(self.current_playlist)
            else:
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
        if self.current_collection_kind == "playlist":
            total_duration = sum(track.duration for track in self.current_album.tracks)
            self.detail_meta.setText(
                self.t("playlist_meta").format(
                    tracks=len(self.current_album.tracks),
                    duration=format_time(total_duration),
                )
            )
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

    def update_album_list_item(self, item_data: Optional[object]) -> None:
        if not item_data:
            return
        item_id = getattr(item_data, "id", None)
        if not item_id:
            return
        for index in range(self.album_list.count()):
            item = self.album_list.item(index)
            if item.data(Qt.UserRole) != item_id:
                continue
            if self.library_mode == "playlists":
                playlist = item_data if isinstance(item_data, PlaylistData) else None
                if not playlist:
                    playlist = next((pl for pl in self.playlists if pl.id == item_id), None)
                if not playlist:
                    break
                item.setText(
                    f"{playlist.title}\n{self.t('playlist_card_meta').format(count=len(self.resolve_playlist_tracks(playlist)))}".strip()
                )
                item.setIcon(QIcon(self.playlist_icon_pixmap(playlist, 140)))
            else:
                album = item_data if isinstance(item_data, Album) else None
                if not album:
                    album = next((al for al in self.albums if al.id == item_id), None)
                if not album:
                    break
                item.setText(f"{album.title}\n{self.display_artist(album.artist)}".strip())
                item.setIcon(QIcon(self.album_pixmap(album, 140)))
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
        self._restore_autoplay = self._last_playing
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

        tab_width = max(92, int(112 * scale))
        self.albums_tab_button.setMinimumWidth(tab_width)
        self.playlists_tab_button.setMinimumWidth(tab_width)
        action_width = max(128, int(154 * scale))
        self.create_playlist_button.setMinimumWidth(action_width)
        self.delete_playlist_button.setMinimumWidth(action_width)
        reorder_btn_width = max(112, int(132 * scale))
        self.edit_order_button.setMinimumWidth(reorder_btn_width)
        step_btn_width = max(86, int(94 * scale))
        self.move_up_button.setMinimumWidth(step_btn_width)
        self.move_down_button.setMinimumWidth(step_btn_width)

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
