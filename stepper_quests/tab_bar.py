"""A flat text tab bar with a brass underline on the selected tab."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

STYLE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #8f8878;
    padding: 8px 14px;
    font-size: 11pt;
}
QPushButton[selected="true"] {
    color: #e8e2d4;
    border-bottom: 2px solid #d8b35a;
}
"""


class TabBar(QWidget):
    changed = Signal(str)

    def __init__(self, names: list[str], parent=None):
        super().__init__(parent)
        self._current = ""
        self._buttons: dict[str, QPushButton] = {}
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for name in names:
            button = QPushButton(name)
            button.setFlat(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("selected", False)
            button.clicked.connect(lambda _=False, n=name: self.select(n))
            layout.addWidget(button)
            self._buttons[name] = button
        layout.addStretch(1)

    def current(self) -> str:
        return self._current

    def select(self, name: str) -> None:
        if name not in self._buttons:
            return
        self._current = name
        for key, button in self._buttons.items():
            button.setProperty("selected", key == name)
            button.style().unpolish(button)
            button.style().polish(button)
        self.changed.emit(name)
