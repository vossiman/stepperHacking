"""Close-up of the road ahead: a curved road, road markers, waypoints and a walking hobbit."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .journey_model import Span

BRASS = QColor("#d8b35a")
AHEAD = QColor("#6d675c")
TEXT = QColor("#e8e2d4")
MUTED = QColor("#a39b8a")
INK = QColor("#1b1a17")
MARGIN_X = 28
LABEL_CHARS = 22
SAMPLES = 160
TICK_PX = 6
LABEL_ABOVE_PX = 34
LABEL_BELOW_PX = 16
WALK_FRAME_MS = 125
PHASE_STEP = 2 * math.pi / 8
SWING_DEG = 18.0
ROCK_DEG = 4.0


def _elide(name: str) -> str:
    return name if len(name) <= LABEL_CHARS else name[: LABEL_CHARS - 1].rstrip() + "…"


class RouteWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(200)
        self._waypoints = []
        self._markers: list[float] = []
        self._start = 0.0
        self._end = 1.0
        self._now = 0.0
        self._reached = None
        self._next = None
        self._steps_to_next: str | None = None
        self._labelled_names: list[str] = []
        self._walking = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(WALK_FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def set_span(self, span: Span, position, now: float, markers: list[float],
                 steps_to_next: str | None) -> None:
        self._waypoints = list(span.waypoints)
        self._start, self._end = span.start, span.end
        self._now = min(max(now, self._start), self._end)
        self._markers = [m for m in markers if self._start <= m <= self._end]
        self._reached = position.reached
        self._next = position.next
        self._steps_to_next = steps_to_next
        self.update()

    def labelled_names(self) -> list[str]:
        return list(self._labelled_names)

    # animation

    def set_walking(self, walking: bool) -> None:
        self._walking = walking
        if not walking:
            self._phase = 0.0
            self.update()
        self._sync_timer()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync_timer()

    def _sync_timer(self) -> None:
        if self._walking and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + PHASE_STEP) % (2 * math.pi)
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

    def _normal(self, t: float) -> QPointF:
        a, b = self._point(t - 0.002), self._point(t + 0.002)
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy) or 1.0
        return QPointF(-dy / length, dx / length)

    # painting

    def paintEvent(self, event) -> None:
        self._labelled_names = []
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

        for m in self._markers:
            t = self._t(m)
            centre, n = self._point(t), self._normal(t)
            half = TICK_PX / 2
            p.setPen(QPen(BRASS if m <= self._now else MUTED, 1.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(centre.x() - n.x() * half, centre.y() - n.y() * half),
                       QPointF(centre.x() + n.x() * half, centre.y() + n.y() * half))

        p.setPen(Qt.NoPen)
        for w in self._waypoints:
            p.setBrush(BRASS if w.walkable_miles <= self._now else AHEAD)
            p.drawEllipse(self._point(self._t(w.walkable_miles)), 3, 3)

        self._draw_labels(p)
        self._draw_figure(p, self._point(t_now))
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
            y = anchor.y() - LABEL_ABOVE_PX - height if above else anchor.y() + LABEL_BELOW_PX
            x = min(max(anchor.x() - width / 2, 2), self.width() - width - 2)
            return QRectF(x, y, width, height)

        def draw(w, rect: QRectF, above: bool, colour: QColor) -> None:
            anchor = self._point(self._t(w.walkable_miles))
            p.setPen(QPen(AHEAD, 1))
            p.drawLine(anchor, QPointF(anchor.x(), rect.bottom() if above else rect.top()))
            p.setPen(colour)
            p.drawText(rect, Qt.AlignCenter, _elide(w.name))
            placed.append(rect)
            self._labelled_names.append(w.name)

        # The reached and next waypoints always get a label, on opposite sides.
        if self._reached is not None:
            draw(self._reached, rect_for(self._reached, True), True, TEXT)
        if self._next is not None:
            rect = rect_for(self._next, False)
            draw(self._next, rect, False, BRASS)
            if self._steps_to_next:
                width = metrics.horizontalAdvance(self._steps_to_next) + 6
                x = min(max(rect.center().x() - width / 2, 2), self.width() - width - 2)
                sub = QRectF(x, rect.bottom(), width, metrics.height())
                p.setPen(MUTED)
                p.drawText(sub, Qt.AlignCenter, self._steps_to_next)
                placed.append(sub)

        above = True
        for w in self._waypoints:
            if w is self._reached or w is self._next:
                continue
            for side in (above, not above):
                rect = rect_for(w, side)
                if not any(rect.adjusted(-4, 0, 4, 0).intersects(r) for r in placed):
                    draw(w, rect, side, MUTED)
                    above = not side
                    break

    def _draw_figure(self, p: QPainter, feet: QPointF) -> None:
        boat = self._next is not None and self._next.mode == "boat"
        swing = math.sin(self._phase)
        p.save()
        p.translate(feet)
        outline = QPen(INK, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

        if boat:
            p.rotate(ROCK_DEG * swing)
            hull = QPainterPath()
            hull.moveTo(-15, -4)
            hull.lineTo(15, -4)
            hull.quadTo(12, 4, 0, 4)
            hull.quadTo(-12, 4, -15, -4)
            p.setPen(outline)
            p.setBrush(AHEAD)
            p.drawPath(hull)
            p.translate(0, -4)
        else:
            leg_angle = math.radians(SWING_DEG * swing)
            hip = QPointF(0, -8)
            for sign in (1, -1):
                foot = QPointF(hip.x() + 8 * math.sin(sign * leg_angle),
                               hip.y() + 8 * math.cos(leg_angle))
                p.setPen(QPen(INK, 4.5, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(hip, foot)
                p.setPen(QPen(BRASS, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(hip, foot)

        stick_angle = math.radians(SWING_DEG * swing)
        hand = QPointF(5, -15)
        tip = QPointF(hand.x() + 15 * math.sin(stick_angle) + 3, hand.y() + 15 * math.cos(stick_angle))
        top = QPointF(hand.x() - 4 * math.sin(stick_angle), hand.y() - 4 * math.cos(stick_angle))
        p.setPen(QPen(INK, 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(top, tip)
        p.setPen(QPen(BRASS, 1.8, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(top, tip)

        p.setPen(outline)
        p.setBrush(BRASS)
        cloak = QPolygonF([QPointF(-3.5, -19), QPointF(3.5, -19), QPointF(6, -7), QPointF(-6, -7)])
        path = QPainterPath()
        path.addPolygon(cloak)
        path.closeSubpath()
        p.drawPath(_rounded(path))
        p.drawEllipse(QPointF(0, -22.5), 4, 4)
        p.restore()


def _rounded(path: QPainterPath) -> QPainterPath:
    # Stroke-and-union gives the trapezoid soft corners without hand-built arcs.
    stroker = QPainterPathStroker()
    stroker.setWidth(2)
    stroker.setJoinStyle(Qt.RoundJoin)
    return path.united(stroker.createStroke(path)).simplified()
