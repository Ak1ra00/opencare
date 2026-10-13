"""Original line icons drawn as inline SVG and rasterised to themed QIcons.

All paths are stroked with ``currentColor`` so a single definition serves light and dark.
Add new icons to ICONS as a 24x24 viewBox SVG inner body (paths only).
"""
from __future__ import annotations

import functools

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from opencare.ui import theme

_S = 'stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"'

ICONS: dict[str, str] = {
    "home": f'<path {_S} d="M4 11l8-6 8 6M6 10v9h12v-9"/>',
    "broom": f'<path {_S} d="M14 3l4 4-6 6-4-4zM8 9l-4 8 8-4M11 13l-3 3"/>',
    "rocket": f'<path {_S} d="M5 15c-1 2-1 4-1 4s2 0 4-1m-1-3c1-5 4-8 9-10 1 4-1 8-6 10l-3-1zm5-5a1.5 1.5 0 100 0"/>',
    "power": f'<path {_S} d="M12 4v7M7 7a7 7 0 109.9 0"/>',
    "shield": f'<path {_S} d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
    "shield_check": f'<path {_S} d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6zM9 11.5l2 2 4-4"/>',
    "wrench": f'<path {_S} d="M15 7a4 4 0 01-5 5l-5 5 2 2 5-5a4 4 0 005-5l-2 2-2-.5-.5-2z"/>',
    "history": f'<path {_S} d="M4 12a8 8 0 108-8 8 8 0 00-6 2.7M4 4v3h3M12 8v4l3 2"/>',
    "settings": f'<path {_S} d="M12 9a3 3 0 100 6 3 3 0 000-6z"/><path {_S} d="M12 3l1.3 2.2 2.5-.4.5 2.5 2.2 1.3-1 2.3 1 2.3-2.2 1.3-.5 2.5-2.5-.4L12 21l-1.3-2.2-2.5.4-.5-2.5L5.5 15l1-2.3-1-2.3 2.2-1.3.5-2.5 2.5.4z"/>',
    "sparkle": f'<path {_S} d="M12 4l1.6 4.4L18 10l-4.4 1.6L12 16l-1.6-4.4L6 10l4.4-1.6zM18 4v3M19.5 5.5h-3"/>',
    "lock": f'<rect {_S} x="5" y="10" width="14" height="10" rx="2"/><path {_S} d="M8 10V7a4 4 0 018 0v3"/>',
    "trash": f'<path {_S} d="M5 7h14M10 7V5h4v2M6 7l1 12h10l1-12M10 10v6M14 10v6"/>',
    "file": f'<path {_S} d="M7 3h7l4 4v14H7zM14 3v4h4"/>',
    "folder": f'<path {_S} d="M4 7h5l2 2h9v10H4z"/>',
    "link": f'<path {_S} d="M9 15l6-6M8 11l-2 2a3 3 0 004 4l2-2M16 13l2-2a3 3 0 00-4-4l-2 2"/>',
    "database": f'<path {_S} d="M12 3c4 0 7 1 7 2.5S16 8 12 8 5 7 5 5.5 8 3 12 3zM5 5.5v13C5 20 8 21 12 21s7-1 7-2.5v-13M5 12c0 1.5 3 2.5 7 2.5s7-1 7-2.5"/>',
    "gauge": f'<path {_S} d="M4 14a8 8 0 1116 0M12 14l4-3"/><circle cx="12" cy="14" r="1.3" fill="currentColor" stroke="none"/>',
    "cpu": f'<rect {_S} x="7" y="7" width="10" height="10" rx="1.5"/><path {_S} d="M10 3v2M14 3v2M10 19v2M14 19v2M3 10h2M3 14h2M19 10h2M19 14h2"/>',
    "memory": f'<rect {_S} x="3" y="8" width="18" height="9" rx="1.5"/><path {_S} d="M7 17v2M12 17v2M17 17v2M7 11v3M12 11v3M17 11v3"/>',
    "disk": f'<circle {_S} cx="12" cy="12" r="8"/><circle {_S} cx="12" cy="12" r="2.5"/><path {_S} d="M12 4v3"/>',
    "startup": f'<path {_S} d="M12 4v10M8 8l4-4 4 4M5 15v4h14v-4"/>',
    "check": f'<path {_S} d="M5 12l4 4 10-10"/>',
    "check_circle": f'<circle {_S} cx="12" cy="12" r="8"/><path {_S} d="M8.5 12l2.5 2.5 4.5-5"/>',
    "alert": f'<path {_S} d="M12 4l9 15H3zM12 10v4M12 17v.5"/>',
    "warning_tri": f'<path {_S} d="M12 4l9 15H3zM12 10v4M12 17v.5"/>',
    "info": f'<circle {_S} cx="12" cy="12" r="8"/><path {_S} d="M12 11v5M12 8v.5"/>',
    "close": f'<path {_S} d="M6 6l12 12M18 6L6 18"/>',
    "minimize": f'<path {_S} d="M5 12h14"/>',
    "chevron_right": f'<path {_S} d="M9 6l6 6-6 6"/>',
    "chevron_down": f'<path {_S} d="M6 9l6 6 6-6"/>',
    "search": f'<circle {_S} cx="11" cy="11" r="6"/><path {_S} d="M20 20l-4-4"/>',
    "refresh": f'<path {_S} d="M4 12a8 8 0 0113.7-5.6L20 8M20 4v4h-4M20 12a8 8 0 01-13.7 5.6L4 16M4 20v-4h4"/>',
    "undo": f'<path {_S} d="M9 7L4 12l5 5M4 12h11a5 5 0 015 5v1"/>',
    "clock": f'<circle {_S} cx="12" cy="12" r="8"/><path {_S} d="M12 8v4l3 2"/>',
    "eye": f'<path {_S} d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle {_S} cx="12" cy="12" r="2.5"/>',
    "browser": f'<rect {_S} x="4" y="5" width="16" height="14" rx="2"/><path {_S} d="M4 9h16M7 7h.5M9.5 7h.5"/>',
    "list": f'<path {_S} d="M8 6h12M8 12h12M8 18h12M4 6h.5M4 12h.5M4 18h.5"/>',
    "shutdown": f'<circle {_S} cx="12" cy="12" r="8"/><path {_S} d="M12 8v4"/>',
    "star": f'<path {_S} d="M12 4l2.3 4.7 5.2.8-3.8 3.6.9 5.1L12 16l-4.6 2.4.9-5.1L4.5 9.5l5.2-.8z"/>',
    "plus": f'<path {_S} d="M12 5v14M5 12h14"/>',
    "dots": f'<circle cx="6" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
    "duplicate": f'<rect {_S} x="8" y="8" width="11" height="11" rx="2"/><path {_S} d="M5 15V5h10"/>',
    "net": f'<circle {_S} cx="12" cy="12" r="8"/><path {_S} d="M4 12h16M12 4c2.5 2.5 2.5 13 0 16M12 4c-2.5 2.5-2.5 13 0 16"/>',
}


def svg(name: str, color: str | None = None) -> str:
    body = ICONS.get(name, ICONS["sparkle"])
    col = color or theme.hex_color("text")
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" color="{col}">{body}</svg>'


@functools.lru_cache(maxsize=512)
def _pixmap(name: str, color: str, px: int, dpr_x100: int) -> QPixmap:
    dpr = dpr_x100 / 100
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode("utf-8")))
    pm = QPixmap(int(px * dpr), int(px * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    return pm


def pixmap(name: str, color: str | None = None, size: int = 20, dpr: float = 1.0) -> QPixmap:
    return _pixmap(name, color or theme.hex_color("text"), size, int(dpr * 100))


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color, size))


def colored_icon(name: str, token: str, size: int = 20) -> QIcon:
    return icon(name, theme.hex_color(token), size)
