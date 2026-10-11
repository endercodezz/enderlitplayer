"""Application stylesheet generated from design tokens."""

from __future__ import annotations

from enderlitplayer.ui.styles.tokens import Palette, Radius, Size, Space, Type


def css(value: str) -> str:
    """Convert token colors to QSS syntax (QSS alpha is 0-255, tokens use 0-1)."""
    value = value.strip()
    if value.startswith("rgba"):
        parts = [p.strip() for p in value[value.index("(") + 1 : value.index(")")].split(",")]
        alpha = round(float(parts[3]) * 255)
        return f"rgba({parts[0]}, {parts[1]}, {parts[2]}, {alpha})"
    return value


def build_stylesheet(p: Palette) -> str:
    c = {name: css(getattr(p, name)) for name in p.__dataclass_fields__ if name != "name"}
    return f"""
* {{
    font-family: {Type.FAMILY};
    font-size: {Type.BODY}px;
    color: {c["text"]};
    outline: none;
}}
QMainWindow, #AppRoot, #ContentHost, #PageRoot {{
    background: {c["window"]};
}}
QWidget#Transparent, QScrollArea, QScrollArea > QWidget > QWidget#ScrollBody {{
    background: transparent;
    border: none;
}}
QToolTip {{
    background: {c["elevated"]};
    color: {c["text"]};
    border: 1px solid {c["border_strong"]};
    border-radius: {Radius.S}px;
    padding: 5px 8px;
    font-size: {Type.SMALL}px;
}}

/* Sidebar ------------------------------------------------------------------ */
#Sidebar {{
    background: {c["sidebar"]};
    border-right: 1px solid {c["border"]};
}}
#BrandLabel {{
    font-family: {Type.FAMILY_DISPLAY};
    font-size: {Type.TITLE}px;
    font-weight: 700;
}}
#NavSection {{
    color: {c["text_tertiary"]};
    font-size: {Type.CAPTION}px;
    font-weight: 600;
    letter-spacing: 0.6px;
    padding: 0 {Space.M}px;
}}
QPushButton#NavButton {{
    background: transparent;
    border: none;
    border-radius: {Radius.M}px;
    color: {c["text_secondary"]};
    font-size: {Type.BODY}px;
    font-weight: 500;
    text-align: left;
    padding: 0 {Space.M}px;
    min-height: {Size.NAV_ITEM}px;
    max-height: {Size.NAV_ITEM}px;
}}
QPushButton#NavButton:hover {{
    background: {c["hover"]};
    color: {c["text"]};
}}
QPushButton#NavButton:checked {{
    background: {c["selected"]};
    color: {c["text"]};
    font-weight: 600;
}}
QPushButton#NavButton[compact="true"] {{
    text-align: center;
    padding: 0;
}}
#SidebarStatus {{
    color: {c["text_tertiary"]};
    font-size: {Type.SMALL}px;
    padding: 0 {Space.M}px;
}}

/* Player bar --------------------------------------------------------------- */
#PlayerBar {{
    background: {c["surface"]};
    border-top: 1px solid {c["border"]};
}}
#NowTitle {{
    font-size: {Type.BODY}px;
    font-weight: 600;
}}
#NowArtist, #TimeLabel {{
    color: {c["text_secondary"]};
    font-size: {Type.SMALL}px;
}}
#TimeLabel {{
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
}}

/* Buttons ------------------------------------------------------------------ */
QPushButton {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {Size.BUTTON_HEIGHT // 2 - 1}px;
    padding: 0 {Space.L}px;
    min-height: {Size.BUTTON_HEIGHT - 2}px;
    max-height: {Size.BUTTON_HEIGHT - 2}px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {c["elevated"]};
    border-color: {c["border_strong"]};
}}
QPushButton:pressed {{
    background: {c["pressed"]};
}}
QPushButton:disabled {{
    color: {c["text_tertiary"]};
    background: transparent;
}}
QPushButton:checked {{
    background: {c["accent_soft"]};
    border-color: {c["accent"]};
    color: {c["accent"]};
}}
QPushButton#PrimaryButton {{
    background: {c["accent"]};
    border: 1px solid {c["accent"]};
    color: {c["on_accent"]};
    padding: 0 {Space.XL - 2}px;
}}
QPushButton#PrimaryButton:hover {{
    background: {c["accent_hover"]};
    border-color: {c["accent_hover"]};
}}
QPushButton#PrimaryButton:pressed {{
    background: {c["accent_pressed"]};
    border-color: {c["accent_pressed"]};
}}
QPushButton#PrimaryButton:disabled {{
    background: {c["surface_alt"]};
    border-color: {c["border"]};
    color: {c["text_tertiary"]};
}}
QPushButton#GhostButton {{
    background: transparent;
    border: 1px solid transparent;
    color: {c["text_secondary"]};
    padding: 0 {Space.M}px;
}}
QPushButton#GhostButton:hover {{
    background: {c["hover"]};
    color: {c["text"]};
}}
QPushButton#DangerButton {{
    background: {c["danger"]};
    border: 1px solid {c["danger"]};
    color: #ffffff;
}}
QPushButton#LinkButton {{
    background: transparent;
    border: none;
    color: {c["text_secondary"]};
    padding: 0 {Space.XS}px;
    min-height: 28px;
    font-weight: 500;
    text-align: left;
}}
QPushButton#LinkButton:hover {{
    color: {c["text"]};
}}
QToolButton#IconButton {{
    background: transparent;
    border: none;
    border-radius: {Radius.M}px;
    padding: 0;
}}
QToolButton#IconButton:hover {{
    background: {c["hover"]};
}}
QToolButton#IconButton:pressed {{
    background: {c["pressed"]};
}}
QToolButton#IconButton:checked {{
    background: {c["accent_soft"]};
}}
QToolButton#IconButton::menu-indicator {{
    image: none;
    width: 0;
}}
QToolButton#TransportButton {{
    background: transparent;
    border: none;
    border-radius: {Size.TRANSPORT_BUTTON // 2}px;
}}
QToolButton#TransportButton:hover {{
    background: {c["hover"]};
}}
QToolButton#TransportButton:disabled {{
    background: transparent;
}}
QToolButton#PlayButton {{
    background: {c["text"]};
    border: none;
    border-radius: {Size.PLAY_BUTTON // 2}px;
}}
QToolButton#PlayButton:hover {{
    background: {c["accent"]};
}}
QToolButton#PlayButton:disabled {{
    background: {c["surface_alt"]};
}}

/* Segmented control -------------------------------------------------------- */
#Segmented {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {Radius.M + 2}px;
}}
QPushButton#SegmentButton {{
    background: transparent;
    border: none;
    border-radius: {Radius.M - 1}px;
    color: {c["text_secondary"]};
    min-height: 28px;
    padding: 0 {Space.M + 2}px;
    font-weight: 600;
}}
QPushButton#SegmentButton:hover {{
    color: {c["text"]};
}}
QPushButton#SegmentButton:checked {{
    background: {c["elevated"]};
    color: {c["text"]};
    border: 1px solid {c["border_strong"]};
}}

/* Inputs ------------------------------------------------------------------- */
QLineEdit {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {Radius.M}px;
    padding: 0 {Space.M}px;
    min-height: {Size.INPUT_HEIGHT - 2}px;
    selection-background-color: {c["accent"]};
    selection-color: {c["on_accent"]};
}}
QLineEdit:hover {{
    border-color: {c["border_strong"]};
}}
QLineEdit:focus {{
    border-color: {c["accent"]};
}}
QLineEdit#SearchField {{
    border-radius: {Size.INPUT_HEIGHT // 2}px;
    padding-left: {Space.XS}px;
    background: {c["surface_alt"]};
}}
QLineEdit[invalid="true"] {{
    border-color: {c["danger"]};
}}

/* Typography --------------------------------------------------------------- */
#PageTitle {{
    font-family: {Type.FAMILY_DISPLAY};
    font-size: {Type.HEADING}px;
    font-weight: 700;
}}
#PageMeta, #DetailMeta {{
    color: {c["text_secondary"]};
    font-size: {Type.BODY}px;
}}
#DetailTitle {{
    font-family: {Type.FAMILY_DISPLAY};
    font-size: {Type.DISPLAY}px;
    font-weight: 700;
}}
#KindLabel {{
    color: {c["text_secondary"]};
    font-size: {Type.CAPTION}px;
    font-weight: 700;
    letter-spacing: 1px;
}}
#DetailHint, #HintLabel {{
    color: {c["text_tertiary"]};
    font-size: {Type.SMALL}px;
}}
#EmptyTitle {{
    font-family: {Type.FAMILY_DISPLAY};
    font-size: {Type.TITLE + 2}px;
    font-weight: 700;
}}
#EmptyBody {{
    color: {c["text_secondary"]};
    font-size: {Type.BODY}px;
}}
#SectionTitle {{
    font-size: {Type.BODY_LARGE}px;
    font-weight: 700;
}}
#FieldLabel {{
    color: {c["text_secondary"]};
    font-size: {Type.SMALL}px;
    font-weight: 600;
}}
#RowLabel {{
    font-size: {Type.BODY}px;
}}
#RowValue {{
    color: {c["text_secondary"]};
    font-size: {Type.BODY}px;
}}
#KeyCap {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border_strong"]};
    border-radius: {Radius.S}px;
    color: {c["text_secondary"]};
    font-size: {Type.SMALL}px;
    font-weight: 600;
    padding: 2px 8px;
}}
#ErrorLabel {{
    color: {c["danger"]};
    font-size: {Type.SMALL}px;
}}
#TrackHeader QLabel {{
    color: {c["text_tertiary"]};
    font-size: {Type.CAPTION}px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
#TrackHeader {{
    border-bottom: 1px solid {c["border"]};
}}
QLabel a {{
    color: {c["accent"]};
}}

/* Containers --------------------------------------------------------------- */
#SettingsCard {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {Radius.L}px;
}}
#CardDivider {{
    background: {c["border"]};
    max-height: 1px;
    min-height: 1px;
}}
QDialog#Dialog {{
    background: {c["surface"]};
}}
#Toast {{
    background: {c["elevated"]};
    border: 1px solid {c["border_strong"]};
    border-radius: {Radius.M}px;
}}
#ToastLabel {{
    font-size: {Type.SMALL + 1}px;
}}

/* Item views --------------------------------------------------------------- */
QListView#TrackList, QListView#AlbumGrid {{
    background: transparent;
    border: none;
}}
QListWidget#PickList {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {Radius.M}px;
    padding: {Space.XS}px;
}}
QListWidget#PickList::item {{
    min-height: 34px;
    padding: 0 {Space.S}px;
    border-radius: {Radius.S}px;
}}
QListWidget#PickList::item:hover {{
    background: {c["hover"]};
}}
QListWidget#PickList::item:selected {{
    background: {c["selected"]};
    color: {c["text"]};
}}
QListWidget#PickList::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {c["border_strong"]};
    background: {c["surface"]};
}}
QListWidget#PickList::indicator:checked {{
    background: {c["accent"]};
    border-color: {c["accent"]};
}}
QListWidget#PickList::indicator:disabled {{
    background: {c["surface_alt"]};
    border-color: {c["border"]};
}}
QListWidget#PickList::indicator:checked:disabled {{
    background: {c["accent_soft"]};
    border-color: {c["accent_soft"]};
}}

/* Scrollbars --------------------------------------------------------------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c["border_strong"]};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c["text_tertiary"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c["border_strong"]};
    border-radius: 3px;
    min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    border: none;
    width: 0;
    height: 0;
}}

/* Menus -------------------------------------------------------------------- */
QMenu {{
    background: {c["elevated"]};
    border: 1px solid {c["border_strong"]};
    border-radius: {Radius.M}px;
    padding: {Space.XS}px;
}}
QMenu::item {{
    padding: 7px {Space.XL}px 7px {Space.M}px;
    border-radius: {Radius.S}px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {c["hover"]};
}}
QMenu::item:disabled {{
    color: {c["text_tertiary"]};
}}
QMenu::separator {{
    height: 1px;
    background: {c["border"]};
    margin: {Space.XS}px {Space.S}px;
}}
QMenu::icon {{
    padding-left: {Space.S}px;
}}

/* Progress ----------------------------------------------------------------- */
QProgressBar#ScanBar {{
    background: transparent;
    border: none;
    max-height: 2px;
    min-height: 2px;
}}
QProgressBar#ScanBar::chunk {{
    background: {c["accent"]};
}}
"""
