
# camera_config.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QCheckBox, QDoubleSpinBox, QSpinBox
)
from PySide6.QtCore import Qt
import json
from pathlib import Path

DEFAULTS = {
    "AeEnable": True,          # Auto Exposure on/off
    "ExposureTime": 20000,     # µs, used only if AE is disabled
    "AnalogueGain": 1.0,       # base sensitivity
    "AwbEnable": True,         # Auto White Balance on/off
    "Contrast": 1.0,
    "Brightness": 0.0,         # -1.0..+1.0
    "Saturation": 1.0,
    "Sharpness": 1.0,
    "NoiseReductionMode": 0,   # 0=off (prefer raw-ish data)
    "HdrEnable": False         # keep HDR off for full-res work
}

SETTINGS_PATH = Path("camera_settings.json")

def load_settings():
    if SETTINGS_PATH.exists():
        try:
            return {**DEFAULTS, **json.loads(SETTINGS_PATH.read_text())}
        except Exception:
            pass
    return DEFAULTS.copy()

def save_settings(settings: dict):
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        return True
    except Exception:
        return False

class CameraConfigDialog(QDialog):
    def __init__(self, current_settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera Configuration")
        self.setMinimumWidth(480)
        self.settings = load_settings() if current_settings is None else {**DEFAULTS, **current_settings}

        main = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        # AE / Exposure
        self.ae_chk = QCheckBox("Enable Auto Exposure")
        self.ae_chk.setChecked(bool(self.settings["AeEnable"]))
        form.addRow(QLabel("Auto Exposure (AE):"), self.ae_chk)

        self.exp_spin = QSpinBox()
        self.exp_spin.setRange(100, 200000)  # 0.1ms .. 200ms
        self.exp_spin.setValue(int(self.settings["ExposureTime"]))
        form.addRow(QLabel("Exposure Time (µs):"), self.exp_spin)

        # Gain
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(1.0, 8.0)
        self.gain_spin.setSingleStep(0.1)
        self.gain_spin.setValue(float(self.settings["AnalogueGain"]))
        form.addRow(QLabel("Analogue Gain (ISO):"), self.gain_spin)

        # AWB
        self.awb_chk = QCheckBox("Enable Auto White Balance")
        self.awb_chk.setChecked(bool(self.settings["AwbEnable"]))
        form.addRow(QLabel("AWB:"), self.awb_chk)

        # Tone controls
        self.contrast_spin = QDoubleSpinBox(); self.contrast_spin.setRange(0.5, 2.0); self.contrast_spin.setSingleStep(0.1)
        self.contrast_spin.setValue(float(self.settings["Contrast"]))
        form.addRow(QLabel("Contrast:"), self.contrast_spin)

        self.brightness_spin = QDoubleSpinBox(); self.brightness_spin.setRange(-1.0, 1.0); self.brightness_spin.setSingleStep(0.1)
        self.brightness_spin.setValue(float(self.settings["Brightness"]))
        form.addRow(QLabel("Brightness:"), self.brightness_spin)

        self.saturation_spin = QDoubleSpinBox(); self.saturation_spin.setRange(0.0, 2.0); self.saturation_spin.setSingleStep(0.1)
        self.saturation_spin.setValue(float(self.settings["Saturation"]))
        form.addRow(QLabel("Saturation:"), self.saturation_spin)

        self.sharpness_spin = QDoubleSpinBox(); self.sharpness_spin.setRange(0.0, 2.0); self.sharpness_spin.setSingleStep(0.1)
        self.sharpness_spin.setValue(float(self.settings["Sharpness"]))
        form.addRow(QLabel("Sharpness:"), self.sharpness_spin)

        # NR / HDR
        self.nr_spin = QSpinBox(); self.nr_spin.setRange(0, 3); self.nr_spin.setValue(int(self.settings["NoiseReductionMode"]))
        form.addRow(QLabel("Noise Reduction Mode:"), self.nr_spin)

        self.hdr_chk = QCheckBox("Enable HDR (3MP only)"); self.hdr_chk.setChecked(bool(self.settings["HdrEnable"]))
        form.addRow(QLabel("HDR:"), self.hdr_chk)

        main.addLayout(form)

        # Buttons
        btns = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.close_btn = QPushButton("Close")
        btns.addWidget(self.apply_btn); btns.addStretch(); btns.addWidget(self.close_btn)
        main.addLayout(btns)

        # Events
        self.apply_btn.clicked.connect(self.on_apply)
        self.close_btn.clicked.connect(self.accept)

    def collect(self) -> dict:
        s = {
            "AeEnable": bool(self.ae_chk.isChecked()),
            "ExposureTime": int(self.exp_spin.value()),
            "AnalogueGain": float(self.gain_spin.value()),
            "AwbEnable": bool(self.awb_chk.isChecked()),
            "Contrast": float(self.contrast_spin.value()),
            "Brightness": float(self.brightness_spin.value()),
            "Saturation": float(self.saturation_spin.value()),
            "Sharpness": float(self.sharpness_spin.value()),
            "NoiseReductionMode": int(self.nr_spin.value()),
            "HdrEnable": bool(self.hdr_chk.isChecked())
        }
        return s

    def on_apply(self):
        self.settings = self.collect()
        ok = save_settings(self.settings)
        # Dialog stays open; caller can apply to camera right away.
