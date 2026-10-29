"""Route drawing of the active part: a curved road, waypoint dots and a marker."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

BRASS = QColor("#d8b35a")
AHEAD = QColor("#6d675c")
TEXT = QColor("#e8e2d4")
MUTED = QColor("#a39b8a")
MARGIN_X = 28
LABEL_CHARS = 22
SAMPLES = 160


def _elide(name: str) -> str:
    return name if len(name) <= LABEL_CHARS else name[: LABEL_CHARS - 1].rstrip() + "…"


class RouteWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(200)
        self._waypoints = []
        self._labelled: list = []
        self._start = 0.0
        self._end = 1.0
        self._now = 0.0
        self._reached = None
        self._next = None

    def set_part(self, part, position, walkable_now: float,
                 start_miles: float | None = None) -> None:
        """``start_miles`` is where the stretch into the part's first waypoint begins."""
        self._waypoints = [w for c in part.chapters for w in c.waypoints]
        first = self._waypoints[0]
        self._start = first.walkable_miles if start_miles is None else start_miles
        self._end = self._waypoints[-1].walkable_miles
        self._now = min(max(walkable_now, self._start), self._end)
        labelled = {id(c.waypoints[-1]) for c in part.chapters if c.waypoints}
        labelled.add(id(first))
        labelled.add(id(position.reached))
        if position.next is not None:
            labelled.add(id(position.next))
        self._labelled = [w for w in self._waypoints if id(w) in labelled]
        self._reached = position.reached
        self._next = position.next
        self.update()

    # geometry

    def _point(self, t: float) -> QPointF:
        w, h = self.width(), self.height()
        x = MARGIN_X + t * (w - 2 * MARGIN_X)
        y = h / 2 + h * 0.16 * math.sin(t * math.pi * 1.6 + 0.4)
        return QPointF(x, y)

    def _t(self, miles: float) -> float:
        span = self._end - self._start
        return 0.0 if span <= 0 else (miles - self._start) / span

    def _path(self, t0: float, t1: float) -> QPainterPath:
        path = QPainterPath(self._point(t0))
        n = max(2, int(SAMPLES * (t1 - t0)))
        for i in range(1, n + 1):
            path.lineTo(self._point(t0 + (t1 - t0) * i / n))
        return path

    def paintEvent(self, event) -> None:
        if not self._waypoints:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t_now = self._t(self._now)

        ahead = QPen(AHEAD, 3, Qt.DashLine)
        ahead.setCapStyle(Qt.RoundCap)
        p.setPen(ahead)
        p.drawPath(self._path(t_now, 1.0))
        if t_now > 0:
            p.setPen(QPen(BRASS, 4, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(self._path(0.0, t_now))

        p.setPen(Qt.NoPen)
        for w in self._waypoints:
            done = w.walkable_miles <= self._now
            p.setBrush(BRASS if done else AHEAD)
            p.drawEllipse(self._point(self._t(w.walkable_miles)), 2.5, 2.5)

        self._draw_labels(p)

        marker = self._point(t_now)
        p.setPen(QPen(QColor("#1b1a17"), 2))
        p.setBrush(BRASS)
        p.drawEllipse(marker, 8, 8)
        p.setBrush(QColor("#1b1a17"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(marker, 3, 3)
        p.end()

    def _draw_labels(self, p: QPainter) -> None:
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        p.setFont(font)
        metrics = QFontMetrics(font)
        placed: list[QRectF] = []

        def rect_for(w, above: bool) -> QRectF:
            anchor = self._point(self._t(w.walkable_miles))
            text = _elide(w.name)
            width = metrics.horizontalAdvance(text) + 6
            height = metrics.height()
            y = anchor.y() - 16 - height if above else anchor.y() + 16
            x = min(max(anchor.x() - width / 2, 2), self.width() - width - 2)
            return QRectF(x, y, width, height)

        def draw(w, rect: QRectF, above: bool, colour: QColor) -> None:
            anchor = self._point(self._t(w.walkable_miles))
            p.setPen(QPen(AHEAD, 1))
            p.drawLine(anchor, QPointF(anchor.x(), rect.bottom() if above else rect.top()))
            p.setPen(colour)
            p.drawText(rect, Qt.AlignCenter, _elide(w.name))
            placed.append(rect)

        # The reached and next waypoints always get a label, on opposite sides.
        if self._reached is not None:
            draw(self._reached, rect_for(self._reached, True), True, TEXT)
        if self._next is not None:
            draw(self._next, rect_for(self._next, False), False, BRASS)

        above = True
        for w in self._labelled:
            if w is self._reached or w is self._next:
                continue
            for side in (above, not above):
                rect = rect_for(w, side)
                if not any(rect.adjusted(-4, 0, 4, 0).intersects(r) for r in placed):
                    draw(w, rect, side, MUTED)
                    above = not side
                    break
