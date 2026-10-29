"""Footprint tray icons: grey outlines idle, brass filled stepping, dashed reconnecting."""

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

STATES = ("idle", "stepping", "reconnecting")
SIZES = (22, 48)

GREY = "#9a9a9a"
BRASS = "#d8b35a"

_FEET = """\
<g transform="rotate(-12 7 15.5)">
<ellipse cx="7" cy="15.5" rx="2.9" ry="5"/>
<circle fill="{toe}" stroke="none" cx="5.1" cy="8.6" r="1.05"/>
<circle fill="{toe}" stroke="none" cx="7.2" cy="8.0" r="0.95"/>
<circle fill="{toe}" stroke="none" cx="9.1" cy="8.7" r="0.85"/>
</g>
<g transform="rotate(12 17 10.5)">
<ellipse cx="17" cy="10.5" rx="2.9" ry="5"/>
<circle fill="{toe}" stroke="none" cx="14.9" cy="3.7" r="0.85"/>
<circle fill="{toe}" stroke="none" cx="16.8" cy="3.0" r="0.95"/>
<circle fill="{toe}" stroke="none" cx="18.9" cy="3.6" r="1.05"/>
</g>"""

_STYLES = {
    "idle": f'fill="none" stroke="{GREY}" stroke-width="1.3"',
    "stepping": f'fill="{BRASS}" stroke="{BRASS}" stroke-width="0.6"',
    "reconnecting": f'fill="none" stroke="{GREY}" stroke-width="1.3" stroke-dasharray="1.8 1.4"',
}


_TOES = {"idle": GREY, "stepping": BRASS, "reconnecting": GREY}


def svg(state: str) -> str:
    style = _STYLES[state]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        f"<g {style}>{_FEET.format(toe=_TOES[state])}</g></svg>"
    )


def make_icon(state: str) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg(state).encode("utf-8")))
    icon = QIcon()
    for size in SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def write_app_icon(path: Path) -> None:
    Path(path).write_text(svg("stepping"), encoding="utf-8")
