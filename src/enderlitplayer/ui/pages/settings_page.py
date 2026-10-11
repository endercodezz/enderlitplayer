"""Settings: library folder, appearance, language, shortcuts and About."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from enderlitplayer import REPOSITORY_URL, __version__
from enderlitplayer.i18n.translations import LANGUAGE_NAMES
from enderlitplayer.i18n.translator import Translator
from enderlitplayer.ui.assets.artwork import build_icon_image
from enderlitplayer.ui.pages.common import Page
from enderlitplayer.ui.styles.theme import ThemeManager
from enderlitplayer.ui.styles.tokens import Size, Space
from enderlitplayer.ui.widgets.controls import Button, ElidedLabel, SegmentedControl, h_line

SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Space", "sc_play_pause"),
    ("Ctrl+← / Ctrl+→", "sc_prev_next"),
    ("Esc / Backspace", "sc_back"),
    ("Ctrl+F", "sc_search"),
    ("Ctrl+L", "sc_folder"),
    ("F2", "sc_edit"),
    ("Alt+↑ / Alt+↓", "sc_reorder"),
)


class _AppMark(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self._image = build_icon_image(192)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRectF(0, 0, 48, 48), self._image)


class SettingsCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(Space.XL - 4, Space.S, Space.XL - 4, Space.S)
        self.rows.setSpacing(0)

    def add_row(self, label: QLabel, control: QWidget | None = None, hint: QLabel | None = None) -> None:
        if self.rows.count():
            self.rows.addWidget(h_line(self))
        row = QHBoxLayout()
        row.setContentsMargins(0, Space.M + 2, 0, Space.M + 2)
        row.setSpacing(Space.L)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label)
        if hint is not None:
            text.addWidget(hint)
        row.addLayout(text, 1)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.rows.addLayout(row)


class SettingsPage(Page):
    chooseFolderRequested = Signal()
    rescanRequested = Signal()
    themeRequested = Signal(str)
    coverStyleRequested = Signal(str)
    languageRequested = Signal(str)

    def __init__(self, theme: ThemeManager, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(theme, translator, parent)
        self._path = ""
        self.root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("ScrollBody")
        scroll.setWidget(body)
        self.root.addWidget(scroll)
        outer = QHBoxLayout(body)
        outer.setContentsMargins(Size.CONTENT_MARGIN, Space.XL + 4, Size.CONTENT_MARGIN, Space.XXL)
        column_host = QWidget(body)
        column_host.setMaximumWidth(Size.SETTINGS_WIDTH)
        column_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer.addWidget(column_host)
        outer.addStretch(0)
        column = QVBoxLayout(column_host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(Space.S)

        self.title = QLabel(self)
        self.title.setObjectName("PageTitle")
        column.addWidget(self.title)
        column.addSpacing(Space.L)

        self._section_labels: dict[str, QLabel] = {}
        self._row_labels: dict[str, QLabel] = {}

        # Library
        library = self._section(column, "section_library")
        self.folder_value = ElidedLabel("", self)
        self.folder_value.setObjectName("RowValue")
        self.folder_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.library_stats = QLabel(self)
        self.library_stats.setObjectName("HintLabel")
        folder_text = QVBoxLayout()
        folder_text.setSpacing(3)
        folder_label = self._label("music_folder")
        folder_text.addWidget(folder_label)
        folder_text.addWidget(self.folder_value)
        folder_text.addWidget(self.library_stats)
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, Space.M + 2, 0, Space.M + 2)
        folder_row.setSpacing(Space.S)
        folder_row.addLayout(folder_text, 1)
        self.rescan_button = Button("", theme, kind="GhostButton", icon_name="refresh", parent=self)
        self.rescan_button.clicked.connect(self.rescanRequested)
        self.folder_button = Button("", theme, icon_name="folder", parent=self)
        self.folder_button.clicked.connect(self.chooseFolderRequested)
        folder_row.addWidget(self.rescan_button, 0, Qt.AlignmentFlag.AlignVCenter)
        folder_row.addWidget(self.folder_button, 0, Qt.AlignmentFlag.AlignVCenter)
        library.rows.addLayout(folder_row)

        # Appearance
        appearance = self._section(column, "section_appearance")
        self.theme_control = SegmentedControl([("dark", ""), ("light", "")], self)
        self.theme_control.changed.connect(self.themeRequested)
        appearance.add_row(self._label("theme"), self.theme_control)
        self.cover_control = SegmentedControl([("rounded", ""), ("square", "")], self)
        self.cover_control.changed.connect(self.coverStyleRequested)
        appearance.add_row(self._label("cover_style"), self.cover_control)

        # Language
        language = self._section(column, "section_language")
        self.language_control = SegmentedControl(list(LANGUAGE_NAMES.items()), self)
        self.language_control.changed.connect(self.languageRequested)
        language.add_row(self._label("language"), self.language_control)

        # Shortcuts
        shortcuts = self._section(column, "section_shortcuts")
        for keys, label_key in SHORTCUTS:
            shortcuts.add_row(self._label(label_key), self._keycap(keys))
        self._mouse_keycap = self._keycap("")
        shortcuts.add_row(self._label("sc_mouse"), self._mouse_keycap)

        # About
        about = self._section(column, "section_about")
        about_row = QHBoxLayout()
        about_row.setContentsMargins(0, Space.L, 0, Space.L)
        about_row.setSpacing(Space.L)
        about_row.addWidget(_AppMark(self), 0, Qt.AlignmentFlag.AlignTop)
        about_text = QVBoxLayout()
        about_text.setSpacing(3)
        name = QLabel("Enderlit Player", self)
        name.setObjectName("SectionTitle")
        self.version_label = QLabel(self)
        self.version_label.setObjectName("RowValue")
        self.about_description = QLabel(self)
        self.about_description.setObjectName("HintLabel")
        self.about_description.setWordWrap(True)
        self.source_link = QLabel(self)
        self.source_link.setOpenExternalLinks(True)
        self.source_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        about_text.addWidget(name)
        about_text.addWidget(self.version_label)
        about_text.addWidget(self.about_description)
        about_text.addSpacing(Space.XS)
        about_text.addWidget(self.source_link)
        about_row.addLayout(about_text, 1)
        about.rows.addLayout(about_row)

        column.addStretch(1)
        theme.themeChanged.connect(self._update_link)
        self.retranslate()

    def _section(self, column: QVBoxLayout, key: str) -> SettingsCard:
        label = QLabel(self)
        label.setObjectName("SectionTitle")
        self._section_labels[key] = label
        column.addSpacing(Space.M)
        column.addWidget(label)
        column.addSpacing(Space.XS)
        card = SettingsCard(self)
        column.addWidget(card)
        return card

    def _label(self, key: str) -> QLabel:
        label = QLabel(self)
        label.setObjectName("RowLabel")
        label.setWordWrap(True)
        self._row_labels.setdefault(key, label)
        return label

    def _keycap(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("KeyCap")
        return label

    # State ------------------------------------------------------------------------------
    def set_values(self, theme: str, cover_style: str, language: str) -> None:
        self.theme_control.set_value(theme)
        self.cover_control.set_value(cover_style)
        self.language_control.set_value(language)

    def set_library(self, path: str, albums: int, tracks: int, scanning: bool) -> None:
        tr = self.tr_
        self.folder_value.setText(path or tr.t("folder_not_set"))
        if scanning:
            self.library_stats.setText(tr.t("scanning"))
        elif path and (albums or tracks):
            self.library_stats.setText(f"{tr.plural('albums', albums)}  ·  {tr.plural('tracks', tracks)}")
        else:
            self.library_stats.setText("")
        self.library_stats.setVisible(bool(self.library_stats.text()))
        self.rescan_button.setVisible(bool(path))
        self.rescan_button.setEnabled(not scanning)
        self.folder_button.setText(tr.t("change_folder") if path else tr.t("choose_folder"))
        self._path = path

    def _update_link(self) -> None:
        color = self.theme.color("accent").name()
        self.source_link.setText(
            f'{self.tr_.t("about_source")}: <a style="color:{color}; text-decoration:none;" '
            f'href="{REPOSITORY_URL}">GitHub</a>'
        )

    def retranslate(self) -> None:
        tr = self.tr_
        self.title.setText(tr.t("settings_title"))
        for key, label in self._section_labels.items():
            label.setText(tr.t(key))
        for key, label in self._row_labels.items():
            label.setText(tr.t(key))
        self.theme_control.set_labels({"dark": tr.t("theme_dark"), "light": tr.t("theme_light")})
        self.cover_control.set_labels({"rounded": tr.t("cover_rounded"), "square": tr.t("cover_square")})
        self._mouse_keycap.setText(tr.t("mouse_buttons"))
        self.rescan_button.setText(tr.t("rescan"))
        self.version_label.setText(tr.t("about_version", version=__version__))
        self.about_description.setText(tr.t("about_description"))
        path = self._path
        self.folder_button.setText(tr.t("change_folder") if path else tr.t("choose_folder"))
        if not path:
            self.folder_value.setText(tr.t("folder_not_set"))
        self._update_link()
