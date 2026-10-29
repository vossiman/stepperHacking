"""A compact strip of bars, one per value, with optional labels underneath."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

BRASS = QColor("#d8b35a")
DIM = QColor("#5f5a50")
MUTED = QColor("#8f8878")
GAP = 3
BASELINE = 2
HEIGHT_PLAIN = 56
HEIGHT_LABELLED = 72
LABEL_BAND = 16


class BarsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._values: list[float] = []
        self._labels: list[str] | None = None
        self._highlight_last = True
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(HEIGHT_PLAIN)

    def set_values(self, values: list[float], labels: list[str] | None = None,
                   highlight_last: bool = True) -> None:
        self._values = list(values)
        self._labels = list(labels) if labels else None
        self._highlight_last = highlight_last
        self.setFixedHeight(HEIGHT_LABELLED if self._labels else HEIGHT_PLAIN)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        count = len(self._values)
        if count == 0:
            return
        label_band = LABEL_BAND if self._labels else 0
        chart_h = self.height() - label_band
        bar_w = (self.width() - GAP * (count - 1)) / count
        peak = max(self._values)
        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        painter.setPen(Qt.NoPen)
        for i, value in enumerate(self._values):
            x = i * (bar_w + GAP)
            last = self._highlight_last and i == count - 1
            if value > 0 and peak > 0:
                h = max(float(BASELINE), chart_h * value / peak)
            else:
                h = float(BASELINE)
            colour = BRASS if last else DIM
            painter.setBrush(colour)
            painter.drawRoundedRect(QRectF(x, chart_h - h, bar_w, h), 1.5, 1.5)
            if self._labels and i < len(self._labels):
                painter.setPen(MUTED)
                painter.drawText(
                    QRectF(x, chart_h + 2, bar_w, metrics.height()),
                    Qt.AlignHCenter | Qt.AlignTop, self._labels[i])
                painter.setPen(Qt.NoPen)
