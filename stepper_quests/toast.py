"""The app's own toast: a frameless always-on-top panel in the bottom-right corner."""

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

MARGIN = 16
SPACING = 8
WIDTH = 340
FADE_IN_MS = 180
FADE_OUT_MS = 450
MAX_WM_SHIFT = 200  # larger jumps are not a panel nudge, so they are ignored

_STYLE = """
QFrame#panel {
    background: #23211d;
    border: 1px solid #3a362e;
    border-left: 4px solid #d8b35a;
    border-radius: 8px;
}
QLabel#title {
    color: #d8b35a;
    font-weight: bold;
    letter-spacing: 1px;
}
QLabel#body {
    color: #e8e4da;
}
"""


class Toast(QWidget):
    clicked = Signal()
    closed = Signal()
    moved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(_STYLE)
        self.setFixedWidth(WIDTH)
        self.setCursor(Qt.PointingHandCursor)

        panel = QFrame(self)
        panel.setObjectName("panel")
        self._title = QLabel(panel)
        self._title.setObjectName("title")
        self._body = QLabel(panel)
        self._body.setObjectName("body")
        self._body.setWordWrap(True)
        inner = QVBoxLayout(panel)
        inner.setContentsMargins(14, 10, 14, 12)
        inner.setSpacing(4)
        inner.addWidget(self._title)
        inner.addWidget(self._body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self._on_click: Callable[[], None] | None = None
        self._closing = False
        self._hold = QTimer(self, singleShot=True)
        self._hold.timeout.connect(self.fade_out)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.finished.connect(self._anim_finished)
        self._after: Callable[[], None] | None = None

    def show_notice(self, title: str, body: str, seconds: float,
                    on_click: Callable[[], None] | None = None) -> None:
        self.set_content(title, body, on_click)
        self.start(seconds)

    def set_content(self, title: str, body: str,
                    on_click: Callable[[], None] | None = None) -> None:
        self._title.setText(title.upper())
        self._body.setText(body)
        self._on_click = on_click
        # Measure after the stylesheet applies; adjustSize() would wrap the
        # body for the narrower size hint.
        self.ensurePolished()
        self.setFixedHeight(self.layout().totalHeightForWidth(WIDTH))

    def start(self, seconds: float) -> None:
        self.setWindowOpacity(0.0)
        self.show()
        self._animate(1.0, FADE_IN_MS)
        self._hold.start(int(seconds * 1000))

    def fade_out(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._hold.stop()
        self._animate(0.0, FADE_OUT_MS, then=self.close)

    def _animate(self, target: float, ms: int, then: Callable[[], None] | None = None) -> None:
        self._anim.stop()
        self._after = then
        self._anim.setDuration(ms)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def _anim_finished(self) -> None:
        if self._after is not None:
            self._after()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            if self._on_click is not None:
                self._on_click()
        self.fade_out()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.moved.emit()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)


class ToastManager:
    """Stacks toasts upward from the corner; the newest sits on top.

    Qt can report the whole screen as available on multi-monitor X11, so
    the panel is invisible to it. The window manager then pushes the lowest
    toast clear of the panel; that corrected edge becomes the new anchor.
    """

    def __init__(self) -> None:
        self._toasts: list[Toast] = []
        self._wm_bottom: int | None = None

    def show_notice(self, title: str, body: str, seconds: float,
                    on_click: Callable[[], None] | None = None) -> Toast:
        toast = Toast()
        toast.closed.connect(lambda: self._remove(toast))
        toast.moved.connect(lambda: self._on_moved(toast))
        toast.set_content(title, body, on_click)
        self._toasts.append(toast)
        self._layout()
        toast.start(seconds)
        return toast

    def close_all(self) -> None:
        for toast in list(self._toasts):
            toast.close()

    def _remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            self._layout()

    def _anchor(self, area) -> int:
        bottom = area.bottom() - MARGIN
        return bottom if self._wm_bottom is None else min(bottom, self._wm_bottom)

    def _on_moved(self, toast: Toast) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None or not self._toasts or toast is not self._toasts[0]:
            return
        target = self._anchor(screen.availableGeometry())
        actual = toast.geometry().bottom()
        if 0 < target - actual <= MAX_WM_SHIFT:
            self._wm_bottom = actual - MARGIN
            self._layout()

    def _layout(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        bottom = self._anchor(area)
        for toast in self._toasts:
            x = area.right() - MARGIN - toast.width() + 1
            y = bottom - toast.height() + 1
            toast.move(x, y)
            bottom = y - SPACING - 1
