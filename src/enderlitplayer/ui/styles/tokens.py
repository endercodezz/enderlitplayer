"""Design tokens: colors, spacing, radii, typography and component sizes.

Every visual constant used by widgets, delegates and the stylesheet lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

ACCENT = "#1db954"


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    sidebar: str
    surface: str
    surface_alt: str
    elevated: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_tertiary: str
    accent: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    accent_soft: str
    danger: str
    hover: str
    pressed: str
    selected: str
    scrim: str
    placeholder: str
    placeholder_glyph: str
    shadow: str


DARK = Palette(
    name="dark",
    window="#121316",
    sidebar="#0d0e10",
    surface="#18191d",
    surface_alt="#1f2125",
    elevated="#24262b",
    border="#25272c",
    border_strong="#33363c",
    text="#eceef1",
    text_secondary="#a2a7af",
    text_tertiary="#6e737b",
    accent=ACCENT,
    accent_hover="#25c862",
    accent_pressed="#18a249",
    on_accent="#06140b",
    accent_soft="rgba(29, 185, 84, 0.14)",
    danger="#f0605d",
    hover="rgba(255, 255, 255, 0.05)",
    pressed="rgba(255, 255, 255, 0.09)",
    selected="rgba(255, 255, 255, 0.08)",
    scrim="rgba(0, 0, 0, 0.55)",
    placeholder="#22252a",
    placeholder_glyph="#4a4e56",
    shadow="rgba(0, 0, 0, 0.45)",
)

LIGHT = Palette(
    name="light",
    window="#f6f7f9",
    sidebar="#eef0f3",
    surface="#ffffff",
    surface_alt="#f1f3f6",
    elevated="#ffffff",
    border="#e1e4e9",
    border_strong="#cfd4db",
    text="#15171a",
    text_secondary="#5a606a",
    text_tertiary="#8b919a",
    accent="#17a24a",
    accent_hover="#149140",
    accent_pressed="#117f38",
    on_accent="#ffffff",
    accent_soft="rgba(23, 162, 74, 0.12)",
    danger="#d93a37",
    hover="rgba(0, 0, 0, 0.04)",
    pressed="rgba(0, 0, 0, 0.08)",
    selected="rgba(0, 0, 0, 0.06)",
    scrim="rgba(15, 17, 20, 0.35)",
    placeholder="#e6e9ed",
    placeholder_glyph="#a9afb8",
    shadow="rgba(15, 17, 20, 0.18)",
)

PALETTES = {"dark": DARK, "light": LIGHT}


class Space:
    XXS = 2
    XS = 4
    S = 8
    M = 12
    L = 16
    XL = 24
    XXL = 32
    XXXL = 48


class Radius:
    S = 6
    M = 8
    L = 12
    XL = 16
    PILL = 999


class Type:
    FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
    FAMILY_DISPLAY = '"Segoe UI Variable Display", "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
    CAPTION = 11
    SMALL = 12
    BODY = 13
    BODY_LARGE = 14
    TITLE = 16
    HEADING = 26
    DISPLAY = 34


class Size:
    SIDEBAR = 228
    SIDEBAR_COMPACT = 68
    SIDEBAR_COMPACT_BELOW = 1060
    NAV_ITEM = 38
    PLAYER_BAR = 84
    PLAYER_COVER = 56
    PLAY_BUTTON = 40
    TRANSPORT_BUTTON = 34
    ICON = 18
    ICON_SMALL = 16
    INPUT_HEIGHT = 36
    BUTTON_HEIGHT = 36
    CARD_MIN = 164
    CARD_MAX = 228
    CARD_TEXT = 52
    CARD_GAP = 20
    ROW_HEIGHT = 52
    ROW_COVER = 0
    DETAIL_COVER_MIN = 152
    DETAIL_COVER_MAX = 232
    CONTENT_MARGIN = 32
    SEARCH_WIDTH = 260
    VOLUME_WIDTH = 120
    SETTINGS_WIDTH = 760


def cover_radius(style: str, size: float) -> float:
    """Corner radius for artwork of ``size`` px under the chosen cover style."""
    if style == "square":
        return 2.0
    return max(4.0, min(12.0, size * 0.045))
