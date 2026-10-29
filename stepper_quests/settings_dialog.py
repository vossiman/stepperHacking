"""Settings dialog: stride length, idle timeout, frame logging and stepper MAC."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from .settings_model import parse_mac

METRES_HELP = ("Changing this moves your marker on the map, because progress is "
               "recomputed from your lifetime steps.")
IDLE_HELP = "Applies from the next walk."
MAC_HELP = "Takes effect after a restart."
MAC_ERROR = "Enter the MAC as six pairs of hex digits, like 18:7A:93:0B:7C:87."


def _help(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: palette(placeholder-text);")
    return label


class SettingsDialog(QDialog):
    def __init__(self, settings, store, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.store = store
        self.setWindowTitle("Stepper Quests settings")

        self.metres = QDoubleSpinBox()
        self.metres.setRange(0.40, 1.20)
        self.metres.setSingleStep(0.05)
        self.metres.setDecimals(2)
        self.metres.setSuffix(" m")
        self.metres.setValue(settings.metres_per_step)

        self.idle = QSpinBox()
        self.idle.setRange(10, 600)
        self.idle.setSuffix(" s")
        self.idle.setValue(int(settings.idle_timeout))

        self.log_frames = QCheckBox("Keep raw frame and step logs for each walk")
        self.log_frames.setChecked(settings.log_frames)

        self.mac = QLineEdit(settings.stepper_mac)
        self.mac.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.mac_error = _help(MAC_ERROR)
        self.mac_error.setStyleSheet("color: #b3261e;")
        self.mac_error.hide()

        form = QFormLayout()
        form.addRow("Metres per step", self.metres)
        form.addRow("", _help(METRES_HELP))
        form.addRow("Idle timeout", self.idle)
        form.addRow("", _help(IDLE_HELP))
        form.addRow("Frame logging", self.log_frames)
        form.addRow("Stepper MAC", self.mac)
        form.addRow("", _help(MAC_HELP))
        form.addRow("", self.mac_error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setMinimumWidth(520)
        self.adjustSize()

    def accept(self) -> None:
        mac = parse_mac(self.mac.text())
        if mac is None:
            self.mac_error.show()
            self.mac.setFocus()
            return
        values = {
            "metres_per_step": round(self.metres.value(), 2),
            "idle_timeout": self.idle.value(),
            "log_frames": self.log_frames.isChecked(),
            "stepper_mac": mac,
        }
        for key, value in values.items():
            self.store.set_setting(key, value)
            setattr(self.settings, key, value)
        super().accept()
