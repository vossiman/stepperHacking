"""Thin overview bar of the whole current part with a you-are-here notch and percent walked."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .journey_model import Span
from .route_widget import AHEAD, BRASS, MUTED

HEIGHT = 28
PAD_X = 12
GAP = 8
TRACK_H = 4
NOTCH_H = 14


class OverviewBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._span = Span(0.0, 1.0, [])
        self._ends = ("", "")
        self._now = 0.0
        self._fraction = 0.0

    def set_overview(self, span: Span, ends: tuple[str, str], now: float, fraction: float) -> None:
        self._span = span
        self._ends = ends
        self._now = now
        self._fraction = min(max(fraction, 0.0), 1.0)
        self.update()

    def percent_text(self) -> str:
        return f"{self._fraction * 100:.1f}%"

    def _x_of(self, miles: float, left: float, right: float) -> float:
        length = self._span.end - self._span.start
        if length <= 0:
            return left
        frac = min(max((miles - self._span.start) / length, 0.0), 1.0)
        return left + frac * (right - left)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
        p.setFont(font)
        metrics = QFontMetrics(font)
        start_name, end_name = (n.upper() for n in self._ends)
        percent = self.percent_text()
        left = PAD_X + metrics.horizontalAdvance(start_name) + GAP
        right = self.width() - PAD_X - metrics.horizontalAdvance(percent) - GAP \
            - metrics.horizontalAdvance(end_name) - GAP
        cy = self.height() / 2
        p.setPen(MUTED)
        p.drawText(QRectF(PAD_X, 0, left, self.height()), Qt.AlignVCenter | Qt.AlignLeft, start_name)
        p.drawText(QRectF(right + GAP, 0, self.width(), self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, end_name)
        p.drawText(QRectF(0, 0, self.width() - PAD_X, self.height()),
                   Qt.AlignVCenter | Qt.AlignRight, percent)
        if right <= left:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(AHEAD)
        p.drawRoundedRect(QRectF(left, cy - TRACK_H / 2, right - left, TRACK_H), 2, 2)
        nx = self._x_of(self._now, left, right)
        p.setBrush(BRASS)
        p.drawRoundedRect(QRectF(left, cy - TRACK_H / 2, nx - left, TRACK_H), 2, 2)
        faint = QColor(MUTED)
        faint.setAlpha(120)
        p.setPen(QPen(faint, 1))
        for w in self._span.waypoints:
            x = self._x_of(w.walkable_miles, left, right)
            p.drawLine(int(x), int(cy - 4), int(x), int(cy + 4))
        p.setPen(QPen(BRASS, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(int(nx), int(cy - NOTCH_H / 2), int(nx), int(cy + NOTCH_H / 2))
