"""Track listing: model, painted row delegate, header and view."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QContextMenuEvent,
    QFont,
    QHelpEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QWidget,
)

from enderlitplayer.core.models import Track
from enderlitplayer.ui.assets.icons import paint_icon
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Radius, Size, Space, Type
from enderlitplayer.utils.formatting import format_time

NUM_W = 36
DURATION_W = 64
ACTION_W = 30
ALBUM_MIN_WIDTH = 720
PAD_L = Space.M
PAD_R = Space.S
COL_GAP = Space.M


@dataclass(frozen=True)
class Columns:
    number: QRectF
    title: QRectF
    album: QRectF | None
    duration: QRectF
    actions: QRectF


def layout_columns(rect: QRectF, show_album: bool, action_count: int) -> Columns:
    """Column geometry shared by the header and the row delegate."""
    left = rect.left() + PAD_L
    right = rect.right() - PAD_R
    actions_w = ACTION_W * max(2, action_count)
    actions = QRectF(right - actions_w, rect.top(), actions_w, rect.height())
    duration = QRectF(actions.left() - DURATION_W, rect.top(), DURATION_W - COL_GAP, rect.height())
    number = QRectF(left, rect.top(), NUM_W, rect.height())
    flex_left = number.right() + COL_GAP
    flex_w = max(40.0, duration.left() - COL_GAP - flex_left)
    album = None
    if show_album and rect.width() >= ALBUM_MIN_WIDTH:
        title_w = flex_w * 0.6
        title = QRectF(flex_left, rect.top(), title_w - COL_GAP, rect.height())
        album = QRectF(flex_left + title_w, rect.top(), flex_w - title_w, rect.height())
    else:
        title = QRectF(flex_left, rect.top(), flex_w, rect.height())
    return Columns(number, title, album, duration, actions)


@dataclass
class TrackRow:
    track: Track
    number: int
    album_title: str
    artist: str


class TrackListModel(QAbstractListModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[TrackRow] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return f"{row.number}. {row.track.title} — {row.artist}"
        return None

    def set_rows(self, rows: list[TrackRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row(self, index: int) -> TrackRow | None:
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def row_of_path(self, path: str) -> int:
        return next((i for i, row in enumerate(self._rows) if row.track.path == path), -1)

    def rows(self) -> list[TrackRow]:
        return list(self._rows)


class TrackRowDelegate(QStyledItemDelegate):
    def __init__(self, view: TrackListView, theme: ThemeManager) -> None:
        super().__init__(view)
        self._view = view
        self._theme = theme

    def sizeHint(self, _option: QStyleOptionViewItem, _index: QModelIndex) -> QSize:
        return QSize(200, Size.ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        view = self._view
        row = view.track_model.row(index.row())
        if row is None:
            return
        theme = self._theme
        rect = QRectF(option.rect)
        hovered = view.hover_row == index.row()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_playing_row = bool(view.playing_path) and row.track.path == view.playing_path

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("selected" if selected else "hover"))
            painter.drawRoundedRect(rect.adjusted(0, 1, 0, -1), Radius.M, Radius.M)

        cols = layout_columns(rect, view.show_album, len(view.row_actions(index.row())))
        base = QFont(option.font)

        # Number / play affordance / equalizer
        if hovered and not (is_playing_row and view.playing_active):
            icon = QRectF(0, 0, 14, 14)
            icon.moveCenter(cols.number.center())
            paint_icon(painter, "play", icon, theme.color("text"))
        elif is_playing_row:
            self._paint_equalizer(painter, cols.number, view.playing_active)
        else:
            number_font = QFont(base)
            number_font.setPixelSize(Type.BODY)
            painter.setFont(number_font)
            painter.setPen(theme.color("text_tertiary"))
            painter.drawText(cols.number, int(Qt.AlignmentFlag.AlignCenter), str(row.number))

        # Title + artist
        title_font = QFont(base)
        title_font.setPixelSize(Type.BODY + 1)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(theme.color("accent" if is_playing_row else "text"))
        title_rect = QRectF(cols.title.left(), rect.top() + 7, cols.title.width(), 20)
        painter.drawText(
            title_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(row.track.title, Qt.TextElideMode.ElideRight, int(title_rect.width())),
        )
        meta_font = QFont(base)
        meta_font.setPixelSize(Type.SMALL)
        painter.setFont(meta_font)
        painter.setPen(theme.color("text_secondary"))
        artist_rect = QRectF(cols.title.left(), title_rect.bottom(), cols.title.width(), 18)
        painter.drawText(
            artist_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(row.artist, Qt.TextElideMode.ElideRight, int(artist_rect.width())),
        )

        # Album
        if cols.album is not None:
            album_font = QFont(base)
            album_font.setPixelSize(Type.BODY)
            painter.setFont(album_font)
            painter.drawText(
                cols.album,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                painter.fontMetrics().elidedText(row.album_title, Qt.TextElideMode.ElideRight, int(cols.album.width())),
            )

        # Duration
        duration_font = QFont(base)
        duration_font.setPixelSize(Type.BODY)
        painter.setFont(duration_font)
        painter.setPen(theme.color("text_secondary"))
        painter.drawText(
            cols.duration,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            format_time(row.track.duration),
        )

        # Row actions (visible on hover / selection, always while reordering)
        if hovered or selected or view.reorder_mode:
            for name, action_rect, enabled in view.action_rects(index.row(), rect):
                active = enabled and view.hover_action == (index.row(), name)
                if active:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(theme.color("pressed"))
                    painter.drawRoundedRect(action_rect, Radius.S, Radius.S)
                token = "text_tertiary"
                if enabled:
                    token = ("danger" if name == "remove" else "text") if active else "text_secondary"
                icon = action_rect.adjusted(6, 6, -6, -6)
                paint_icon(painter, _ACTION_ICONS[name], icon, theme.color(token), stroke=1.9)
        painter.restore()

    def _paint_equalizer(self, painter: QPainter, area: QRectF, animated: bool) -> None:
        color = self._theme.color("accent")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        bar_w, gap, max_h = 3.0, 2.5, 14.0
        total = bar_w * 3 + gap * 2
        x = area.center().x() - total / 2
        base = area.center().y() + max_h / 2
        phase = self._view.eq_phase * 2 * math.pi
        for i in range(3):
            if animated:
                level = 0.3 + 0.7 * 0.5 * (1 + math.sin(phase + i * 2.1))
            else:
                level = (0.45, 0.8, 0.6)[i]
            height = max(3.0, max_h * level)
            painter.drawRoundedRect(QRectF(x, base - height, bar_w, height), 1.2, 1.2)
            x += bar_w + gap


_ACTION_ICONS = {
    "edit": "pencil",
    "remove": "trash",
    "up": "chevron_up",
    "down": "chevron_down",
}


class TrackListView(QListView):
    playRequested = Signal(int)
    actionTriggered = Signal(int, str)
    contextRequested = Signal(int, QPoint)

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TrackList")
        self.track_model = TrackListModel(self)
        self.setModel(self.track_model)
        self.setItemDelegate(TrackRowDelegate(self, theme))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(20)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.show_album = False
        self.reorder_mode = False
        self.removable = False
        self.editable = True
        self.playing_path = ""
        self.playing_active = False
        self.hover_row = -1
        self.hover_action: tuple[int, str] | None = None
        self.eq_phase = 0.0
        self._tooltips: dict[str, str] = {}
        self._eq_timer = QTimer(self)
        self._eq_timer.setInterval(70)
        self._eq_timer.timeout.connect(self._advance_eq)
        theme.themeChanged.connect(self.viewport().update)
        self.doubleClicked.connect(lambda index: self.playRequested.emit(index.row()))

    # Configuration --------------------------------------------------------------------
    def set_rows(self, rows: list[TrackRow]) -> None:
        self.hover_row = -1
        self.hover_action = None
        self.track_model.set_rows(rows)
        self._sync_eq_timer()

    def set_action_tooltips(self, tooltips: dict[str, str]) -> None:
        self._tooltips = tooltips

    def set_playing(self, path: str, active: bool) -> None:
        self.playing_path = path
        self.playing_active = active
        self._sync_eq_timer()
        self.viewport().update()

    def set_reorder_mode(self, enabled: bool) -> None:
        self.reorder_mode = enabled
        self.viewport().update()

    def row_actions(self, row: int) -> list[str]:
        if self.reorder_mode:
            return ["up", "down"]
        actions = []
        if self.editable:
            actions.append("edit")
        if self.removable:
            actions.append("remove")
        return actions

    def action_rects(self, row: int, rect: QRectF) -> list[tuple[str, QRectF, bool]]:
        names = self.row_actions(row)
        cols = layout_columns(rect, self.show_album, len(names))
        result = []
        x = cols.actions.right() - ACTION_W * len(names)
        for name in names:
            enabled = True
            if name == "up":
                enabled = row > 0
            elif name == "down":
                enabled = row < self.track_model.rowCount() - 1
            box = QRectF(x + 1, rect.center().y() - 14, ACTION_W - 2, 28)
            result.append((name, box, enabled))
            x += ACTION_W
        return result

    def _action_at(self, pos: QPoint) -> tuple[int, str] | None:
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        for name, box, enabled in self.action_rects(index.row(), QRectF(self.visualRect(index))):
            if enabled and box.contains(QPointF(pos)):
                return index.row(), name
        return None

    # Equalizer ------------------------------------------------------------------------
    def _sync_eq_timer(self) -> None:
        should_run = self.playing_active and self.track_model.row_of_path(self.playing_path) >= 0 and self.isVisible()
        if should_run and not self._eq_timer.isActive():
            self._eq_timer.start()
        elif not should_run:
            self._eq_timer.stop()

    def _advance_eq(self) -> None:
        self.eq_phase = (self.eq_phase + 0.045) % 1.0
        row = self.track_model.row_of_path(self.playing_path)
        if row >= 0:
            self.viewport().update(self.visualRect(self.track_model.index(row)))

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)
        self._sync_eq_timer()

    def hideEvent(self, event: QEvent) -> None:
        super().hideEvent(event)
        self._eq_timer.stop()

    # Mouse / keyboard -----------------------------------------------------------------
    def _refresh_row(self, row: int) -> None:
        if row >= 0:
            self.viewport().update(self.visualRect(self.track_model.index(row)))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        row = index.row() if index.isValid() else -1
        action = self._action_at(pos)
        if row != self.hover_row or action != self.hover_action:
            previous = self.hover_row
            self.hover_row = row
            self.hover_action = action
            self._refresh_row(previous)
            self._refresh_row(row)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if action else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        previous = self.hover_row
        self.hover_row = -1
        self.hover_action = None
        self._refresh_row(previous)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            action = self._action_at(pos)
            if action is not None:
                self.setCurrentIndex(self.track_model.index(action[0]))
                self.actionTriggered.emit(action[0], action[1])
                event.accept()
                return
            index = self.indexAt(pos)
            if index.isValid():
                cols = layout_columns(
                    QRectF(self.visualRect(index)), self.show_album, len(self.row_actions(index.row()))
                )
                if cols.number.adjusted(-PAD_L, 0, 0, 0).contains(event.position()):
                    self.setCurrentIndex(index)
                    self.playRequested.emit(index.row())
                    event.accept()
                    return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        row = self.currentIndex().row()
        if row >= 0:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.playRequested.emit(row)
                return
            if self.reorder_mode and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if event.key() == Qt.Key.Key_Up:
                    self.actionTriggered.emit(row, "up")
                    return
                if event.key() == Qt.Key.Key_Down:
                    self.actionTriggered.emit(row, "down")
                    return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self.indexAt(event.pos())
        if index.isValid():
            self.setCurrentIndex(index)
            self.contextRequested.emit(index.row(), event.globalPos())

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            action = self._action_at(event.pos())
            if action is not None and action[1] in self._tooltips:
                QToolTip.showText(event.globalPos(), self._tooltips[action[1]], self)
                return True
            QToolTip.hideText()
            event.ignore()
            return True
        return super().viewportEvent(event)

    def select_row(self, row: int) -> None:
        if 0 <= row < self.track_model.rowCount():
            index = self.track_model.index(row)
            self.setCurrentIndex(index)
            self.scrollTo(index)

    def selected_row(self) -> int:
        indexes = self.selectionModel().selectedIndexes() if self.selectionModel() else []
        return indexes[0].row() if indexes else -1


class TrackListHeader(QWidget):
    """Column captions aligned with :class:`TrackListView` rows."""

    def __init__(self, view: TrackListView, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view
        self._theme = theme
        self._labels = {"number": "#", "title": "", "album": "", "duration": ""}
        self.setFixedHeight(34)
        theme.themeChanged.connect(self.update)
        view.installEventFilter(self)

    def set_labels(self, title: str, album: str, duration: str) -> None:
        self._labels.update(title=title.upper(), album=album.upper(), duration=duration.upper())
        self.update()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._view and event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            self.update()
        return False

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        width = self._view.viewport().width() if self._view.isVisible() else self.width()
        rect = QRectF(0, 0, width, self.height())
        cols = layout_columns(rect, self._view.show_album, len(self._view.row_actions(0)))
        font = QFont(self.font())
        font.setPixelSize(Type.CAPTION)
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        painter.setFont(font)
        painter.setPen(self._theme.color("text_tertiary"))
        left = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.drawText(cols.number, int(Qt.AlignmentFlag.AlignCenter), self._labels["number"])
        painter.drawText(cols.title, left, self._labels["title"])
        if cols.album is not None:
            painter.drawText(cols.album, left, self._labels["album"])
        painter.drawText(
            cols.duration, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), self._labels["duration"]
        )
        painter.setPen(self._theme.color("border"))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


__all__ = ["TrackListHeader", "TrackListModel", "TrackListView", "TrackRow", "layout_columns"]
