"""Responsive artwork grid for albums and playlists."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractListModel,
    QEasingCurve,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QContextMenuEvent, QFont, QKeyEvent, QMouseEvent, QPainter, QPen, QResizeEvent
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from enderlitplayer.services.covers import CoverProvider, CoverSource
from enderlitplayer.ui.assets.artwork import paint_cover
from enderlitplayer.ui.assets.icons import paint_icon
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Radius, Size, Type

H_GAP = 12
V_GAP = 6
CARD_PAD = 10
TEXT_GAP = 10
TITLE_H = 20
SUBTITLE_H = 18
PLAY_SIZE = 44


@dataclass
class GridItem:
    id: str
    title: str
    subtitle: str
    cover: CoverSource | None
    glyph: str = "album"


class GridModel(QAbstractListModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[GridItem] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return f"{item.title} — {item.subtitle}" if item.subtitle else item.title
        if role == Qt.ItemDataRole.UserRole:
            return item.id
        return None

    def set_items(self, items: list[GridItem]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def item(self, row: int) -> GridItem | None:
        return self._items[row] if 0 <= row < len(self._items) else None

    def row_of(self, item_id: str) -> int:
        return next((i for i, item in enumerate(self._items) if item.id == item_id), -1)

    def refresh_cover(self, key: str) -> None:
        for row, item in enumerate(self._items):
            if item.cover is not None and item.cover.key == key:
                index = self.index(row)
                self.dataChanged.emit(index, index)


def card_rect(cell: QRect) -> QRectF:
    return QRectF(cell).adjusted(H_GAP / 2, V_GAP / 2, -H_GAP / 2, -V_GAP / 2)


def cover_rect(cell: QRect) -> QRectF:
    card = card_rect(cell)
    side = card.width() - 2 * CARD_PAD
    return QRectF(card.left() + CARD_PAD, card.top() + CARD_PAD, side, side)


def play_rect(cell: QRect) -> QRectF:
    cover = cover_rect(cell)
    margin = 10
    return QRectF(cover.right() - PLAY_SIZE - margin, cover.bottom() - PLAY_SIZE - margin, PLAY_SIZE, PLAY_SIZE)


class CardDelegate(QStyledItemDelegate):
    def __init__(self, view: AlbumGridView, theme: ThemeManager, covers: CoverProvider) -> None:
        super().__init__(view)
        self._view = view
        self._theme = theme
        self._covers = covers

    def sizeHint(self, _option: QStyleOptionViewItem, _index: QModelIndex) -> QSize:
        return self._view.gridSize()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item = self._view.grid_model.item(index.row())
        if item is None:
            return
        theme = self._theme
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = card_rect(option.rect)
        hovered = self._view.hover_row == index.row()
        progress = self._view.hover_progress if hovered else 0.0
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus) and self._view.hasFocus()

        if progress > 0:
            bg = theme.color("hover")
            bg.setAlphaF(bg.alphaF() * progress)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(card, Radius.L, Radius.L)
        if focused:
            pen = QPen(theme.color("accent"), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card.adjusted(1, 1, -1, -1), Radius.L, Radius.L)

        cover = cover_rect(option.rect)
        dpr = painter.device().devicePixelRatioF() if painter.device() else 1.0
        pixmap = self._covers.pixmap(item.cover, int(cover.width() * dpr))
        paint_cover(painter, cover, pixmap, theme, item.glyph)

        if progress > 0:
            target = play_rect(option.rect).translated(0, (1 - progress) * 6)
            painter.setOpacity(progress)
            painter.setPen(Qt.PenStyle.NoPen)
            shadow = theme.color("shadow")
            painter.setBrush(shadow)
            painter.drawEllipse(target.translated(0, 2))
            painter.setBrush(theme.color("accent"))
            painter.drawEllipse(target)
            inner = target.adjusted(13, 13, -12, -13)
            paint_icon(painter, "play", inner, theme.color("on_accent"))
            painter.setOpacity(1.0)

        text_left = cover.left()
        text_width = cover.width()
        title_font = QFont(option.font)
        title_font.setPixelSize(Type.BODY)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(theme.color("text"))
        title_rect = QRectF(text_left, cover.bottom() + TEXT_GAP, text_width, TITLE_H)
        metrics = painter.fontMetrics()
        painter.drawText(
            title_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(item.title, Qt.TextElideMode.ElideRight, int(text_width)),
        )
        sub_font = QFont(option.font)
        sub_font.setPixelSize(Type.SMALL)
        painter.setFont(sub_font)
        painter.setPen(theme.color("text_secondary"))
        sub_rect = QRectF(text_left, title_rect.bottom(), text_width, SUBTITLE_H)
        painter.drawText(
            sub_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(item.subtitle, Qt.TextElideMode.ElideRight, int(text_width)),
        )
        painter.restore()


class AlbumGridView(QListView):
    openRequested = Signal(str)
    playRequested = Signal(str)
    contextRequested = Signal(str, QPoint)

    def __init__(self, theme: ThemeManager, covers: CoverProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlbumGrid")
        self.grid_model = GridModel(self)
        self.setModel(self.grid_model)
        self.setItemDelegate(CardDelegate(self, theme, covers))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover_row = -1
        self.hover_progress = 0.0
        self._pressed_row = -1
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_hover_anim)
        covers.coverReady.connect(self.grid_model.refresh_cover)
        theme.themeChanged.connect(self.viewport().update)
        theme.coverStyleChanged.connect(self.viewport().update)
        self._update_grid()

    def set_items(self, items: list[GridItem]) -> None:
        self.hover_row = -1
        self.hover_progress = 0.0
        self.grid_model.set_items(items)

    # Layout ---------------------------------------------------------------------------
    def _update_grid(self) -> None:
        # QListView reserves room for the scrollbar when wrapping, even while it is hidden.
        reserved = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent) + 2
        available = max(1, self.viewport().width() - reserved)
        min_cell = Size.CARD_MIN + H_GAP
        max_cell = Size.CARD_MAX + H_GAP
        columns = max(1, available // min_cell)
        cell_w = min(max_cell, available // columns)
        card_w = cell_w - H_GAP
        cell_h = int(card_w - 2 * CARD_PAD + CARD_PAD + TEXT_GAP + TITLE_H + SUBTITLE_H + CARD_PAD + V_GAP)
        size = QSize(int(cell_w), cell_h)
        if size != self.gridSize():
            self.setGridSize(size)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_grid()

    # Hover animation ------------------------------------------------------------------
    def _on_hover_anim(self, value: float) -> None:
        self.hover_progress = float(value)
        self._update_row(self.hover_row)

    def _update_row(self, row: int) -> None:
        if row >= 0:
            self.viewport().update(self.visualRect(self.grid_model.index(row)))

    def _set_hover(self, row: int) -> None:
        if row == self.hover_row:
            return
        previous = self.hover_row
        self.hover_row = row
        self._update_row(previous)
        self._anim.stop()
        if row >= 0:
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self.hover_progress = 0.0

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        row = index.row() if index.isValid() and card_rect(self.visualRect(index)).contains(event.position()) else -1
        self._set_hover(row)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: object) -> None:
        self._set_hover(-1)
        super().leaveEvent(event)

    # Interaction ----------------------------------------------------------------------
    def _item_id(self, row: int) -> str | None:
        item = self.grid_model.item(row)
        return item.id if item else None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        self._pressed_row = index.row() if index.isValid() else -1
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self.indexAt(event.position().toPoint())
        if not index.isValid() or index.row() != self._pressed_row:
            return
        rect = self.visualRect(index)
        if not card_rect(rect).contains(event.position()):
            return
        item_id = self._item_id(index.row())
        if item_id is None:
            return
        if play_rect(rect).contains(event.position()):
            self.playRequested.emit(item_id)
        else:
            self.openRequested.emit(item_id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentIndex().isValid():
            item_id = self._item_id(self.currentIndex().row())
            if item_id:
                self.openRequested.emit(item_id)
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self.indexAt(event.pos())
        item_id = self._item_id(index.row()) if index.isValid() else None
        if item_id:
            self.setCurrentIndex(index)
            self.contextRequested.emit(item_id, event.globalPos())
