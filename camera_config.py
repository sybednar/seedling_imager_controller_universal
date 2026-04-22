# camera_config.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QCheckBox, QDoubleSpinBox, QSpinBox, QFrame,
    QTabWidget, QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
import json
from pathlib import Path
import camera   # needed for "Read from Camera" button
 
DEFAULTS = {
    "AeEnable":            True,
    "ExposureTime":        20000,
    "AnalogueGain":        1.0,
    "AwbEnable":           True,
    "Contrast":            1.0,
    "Brightness":          0.0,
    "Saturation":          1.0,
    "Sharpness":           1.0,
    "NoiseReductionMode":  0,
    "HdrEnable":           False,
    "ManualFocusEnable":   False,
    "ManualFocusPosition": 7.589,
 
    # Front IR (reflectance) overrides
    "FrontIR_Saturation":  0.0,
    "FrontIR_AwbEnable":   False,
    "FrontIR_Contrast":    1.10,
    "FrontIR_Sharpness":   1.15,
    "FrontIR_Brightness":  0.0,
    "FrontIR_AeEnable":    True,
    "FrontIR_ExposureTime": 20000,
    "FrontIR_Gain":        1.0,
 
    # Rear IR (transmission) overrides
    "RearIR_Saturation":   0.0,
    "RearIR_AwbEnable":    False,
    "RearIR_Contrast":     1.5,
    "RearIR_Sharpness":    1.4,
    "RearIR_Brightness":  -0.05,
    "RearIR_AeEnable":     False,
    "RearIR_ExposureTime": 9000,
    "RearIR_Gain":         1.0,
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
 
 
# ---------------------------------------------------------------------------
# Helper: build a compact QFormLayout inside a plain QWidget (one tab page)
# ---------------------------------------------------------------------------
def _tab_page() -> tuple[QWidget, QFormLayout]:
    w = QWidget()
    fl = QFormLayout(w)
    fl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    fl.setHorizontalSpacing(10)
    fl.setVerticalSpacing(6)
    fl.setContentsMargins(12, 10, 12, 10)
    return w, fl
 
 
def _screen_scale() -> float:
    """Return the GUI scale factor (1.0 on 800 px display, 1.6 on 1280 px Display2)."""
    try:
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        geom = scr.availableGeometry() if scr else None
        s = (geom.width() / 800.0) if geom else 1.0
    except Exception:
        s = 1.0
    return max(1.0, s)
 
 
class CameraConfigDialog(QDialog):
    def __init__(self, current_settings=None, parent=None):
        super().__init__(parent)
        s = _screen_scale()
        self.setWindowTitle("Camera Configuration")
        self.setMinimumWidth(int(325 * s))
        # Cap dialog height to 92 % of screen so it always fits
        try:
            from PySide6.QtGui import QGuiApplication
            scr = QGuiApplication.primaryScreen()
            if scr:
                self.setMaximumHeight(int(scr.availableGeometry().height() * 0.92))
        except Exception:
            pass
        self.settings = load_settings() if current_settings is None else {**DEFAULTS, **current_settings}
 
        main = QVBoxLayout(self)
        main.setSpacing(6)
        main.setContentsMargins(8, 8, 8, 8)
 
        tabs = QTabWidget()
        main.addWidget(tabs, stretch=1)
 
        # ------------------------------------------------------------------ #
        # Tab 1 – General                                                      #
        # ------------------------------------------------------------------ #
        gen_w, gen = _tab_page()
 
        self.ae_chk = QCheckBox("Enable Auto Exposure")
        self.ae_chk.setChecked(bool(self.settings["AeEnable"]))
        gen.addRow(QLabel("Auto Exposure (AE):"), self.ae_chk)
 
        self.exp_spin = QSpinBox()
        self.exp_spin.setRange(100, 200000)
        self.exp_spin.setValue(int(self.settings["ExposureTime"]))
        gen.addRow(QLabel("Exposure Time (µs):"), self.exp_spin)
 
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(1.0, 16.0); self.gain_spin.setSingleStep(0.1)
        self.gain_spin.setValue(float(self.settings["AnalogueGain"]))
        gen.addRow(QLabel("Analogue Gain:"), self.gain_spin)
 
        self.awb_chk = QCheckBox("Enable Auto White Balance")
        self.awb_chk.setChecked(bool(self.settings["AwbEnable"]))
        gen.addRow(QLabel("AWB:"), self.awb_chk)
 
        self.contrast_spin = QDoubleSpinBox()
        self.contrast_spin.setRange(0.5, 2.0); self.contrast_spin.setSingleStep(0.1)
        self.contrast_spin.setValue(float(self.settings["Contrast"]))
        gen.addRow(QLabel("Contrast:"), self.contrast_spin)
 
        self.brightness_spin = QDoubleSpinBox()
        self.brightness_spin.setRange(-1.0, 1.0); self.brightness_spin.setSingleStep(0.1)
        self.brightness_spin.setValue(float(self.settings["Brightness"]))
        gen.addRow(QLabel("Brightness:"), self.brightness_spin)
 
        self.saturation_spin = QDoubleSpinBox()
        self.saturation_spin.setRange(0.0, 2.0); self.saturation_spin.setSingleStep(0.1)
        self.saturation_spin.setValue(float(self.settings["Saturation"]))
        gen.addRow(QLabel("Saturation:"), self.saturation_spin)
 
        self.sharpness_spin = QDoubleSpinBox()
        self.sharpness_spin.setRange(0.0, 2.0); self.sharpness_spin.setSingleStep(0.1)
        self.sharpness_spin.setValue(float(self.settings["Sharpness"]))
        gen.addRow(QLabel("Sharpness:"), self.sharpness_spin)
 
        self.nr_spin = QSpinBox()
        self.nr_spin.setRange(0, 3)
        self.nr_spin.setValue(int(self.settings["NoiseReductionMode"]))
        gen.addRow(QLabel("Noise Reduction Mode:"), self.nr_spin)
 
        self.hdr_chk = QCheckBox("Enable HDR (3MP only)")
        self.hdr_chk.setChecked(bool(self.settings["HdrEnable"]))
        gen.addRow(QLabel("HDR:"), self.hdr_chk)
 
        tabs.addTab(gen_w, "General")
 
        # ------------------------------------------------------------------ #
        # Tab 2 – Focus                                                        #
        # ------------------------------------------------------------------ #
        foc_w, foc = _tab_page()
 
        self.manual_focus_chk = QCheckBox(
            "Use manual focus  (required with 940 nm bandpass filter)"
        )
        self.manual_focus_chk.setChecked(bool(self.settings["ManualFocusEnable"]))
        foc.addRow(QLabel("Manual Focus:"), self.manual_focus_chk)
 
        self.focus_pos_spin = QDoubleSpinBox()
        self.focus_pos_spin.setRange(0.0, 20.0)
        self.focus_pos_spin.setSingleStep(0.1); self.focus_pos_spin.setDecimals(3)
        self.focus_pos_spin.setValue(float(self.settings["ManualFocusPosition"]))
        self.focus_pos_spin.setToolTip(
            "Lens position in diopters (1 / focus distance in metres).\n"
            "0.0 = infinity.  Typical petri plate at 13 cm ≈ 7.589 diopters.\n"
            "Use 'Read from Camera' after auto-focusing in Live View."
        )
        foc.addRow(QLabel("Lens Position (diopters):"), self.focus_pos_spin)
 
        self.focus_pos_spin.setEnabled(self.manual_focus_chk.isChecked())
        self.manual_focus_chk.toggled.connect(self.focus_pos_spin.setEnabled)
 
        self.read_focus_btn = QPushButton("Read Current Position from Camera")
        self.read_focus_btn.setToolTip(
            "Turn on Live View and let auto-focus settle on the petri plate,\n"
            "then press this button to capture the current LensPosition value.\n"
            "Works best with the bandpass filter temporarily removed."
        )
        self.read_focus_btn.clicked.connect(self.on_read_focus)
        foc.addRow(QLabel(""), self.read_focus_btn)
 
        self.focus_hint_lbl = QLabel(
            "LensPosition 7.589 D ≈ 13 cm  |  0.0 D = infinity\n"
            "PDAF does not work through the 940 nm bandpass filter;\n"
            "manual focus must be enabled for captured images to be sharp."
        )
        _hint_fs = max(9, int(8 * s))
        self.focus_hint_lbl.setStyleSheet(f"color: #90A4AE; font-size: {_hint_fs}px;")
        foc.addRow(QLabel(""), self.focus_hint_lbl)
 
        self.focus_status_lbl = QLabel("")
        self.focus_status_lbl.setStyleSheet(f"color: #FFD600; font-size: {_hint_fs}px;")
        foc.addRow(QLabel(""), self.focus_status_lbl)
 
        tabs.addTab(foc_w, "Focus")
 
        # ------------------------------------------------------------------ #
        # Tab 3 – Front IR (Reflectance)                                       #
        # ------------------------------------------------------------------ #
        fir_w, fir = _tab_page()
 
        self.fir_ae_chk = QCheckBox("AE on")
        self.fir_ae_chk.setChecked(bool(self.settings.get("FrontIR_AeEnable", True)))
        fir.addRow(QLabel("AE:"), self.fir_ae_chk)
 
        self.fir_exp = QSpinBox(); self.fir_exp.setRange(100, 200000)
        self.fir_exp.setValue(int(self.settings.get("FrontIR_ExposureTime", 20000)))
        fir.addRow(QLabel("Exposure (µs):"), self.fir_exp)
 
        self.fir_contrast = QDoubleSpinBox()
        self.fir_contrast.setRange(0.5, 2.0); self.fir_contrast.setSingleStep(0.05)
        self.fir_contrast.setValue(float(self.settings.get("FrontIR_Contrast", 1.10)))
        fir.addRow(QLabel("Contrast:"), self.fir_contrast)
 
        self.fir_sharpness = QDoubleSpinBox()
        self.fir_sharpness.setRange(0.0, 2.0); self.fir_sharpness.setSingleStep(0.05)
        self.fir_sharpness.setValue(float(self.settings.get("FrontIR_Sharpness", 1.15)))
        fir.addRow(QLabel("Sharpness:"), self.fir_sharpness)
 
        self.fir_brightness = QDoubleSpinBox()
        self.fir_brightness.setRange(-1.0, 1.0); self.fir_brightness.setSingleStep(0.05)
        self.fir_brightness.setValue(float(self.settings.get("FrontIR_Brightness", 0.0)))
        fir.addRow(QLabel("Brightness:"), self.fir_brightness)
 
        note_fir = QLabel(
            "Applied automatically during Front IR (reflectance)\n"
            "image capture and live view."
        )
        note_fir.setStyleSheet(f"color: #90A4AE; font-size: {max(9, int(8 * s))}px;")
        fir.addRow(QLabel(""), note_fir)
 
        tabs.addTab(fir_w, "Front IR")
 
        # ------------------------------------------------------------------ #
        # Tab 4 – Rear IR (Transmission)                                       #
        # ------------------------------------------------------------------ #
        rir_w, rir = _tab_page()
 
        self.rir_ae_chk = QCheckBox("AE on")
        self.rir_ae_chk.setChecked(bool(self.settings.get("RearIR_AeEnable", False)))
        rir.addRow(QLabel("AE:"), self.rir_ae_chk)
 
        self.rir_exp = QSpinBox(); self.rir_exp.setRange(100, 200000)
        self.rir_exp.setValue(int(self.settings.get("RearIR_ExposureTime", 9000)))
        rir.addRow(QLabel("Exposure (µs):"), self.rir_exp)
 
        self.rir_gain = QDoubleSpinBox()
        self.rir_gain.setRange(1.0, 16.0); self.rir_gain.setSingleStep(0.1)
        self.rir_gain.setValue(float(self.settings.get("RearIR_Gain", 1.0)))
        rir.addRow(QLabel("Gain:"), self.rir_gain)
 
        self.rir_contrast = QDoubleSpinBox()
        self.rir_contrast.setRange(0.5, 2.0); self.rir_contrast.setSingleStep(0.05)
        self.rir_contrast.setValue(float(self.settings.get("RearIR_Contrast", 1.5)))
        rir.addRow(QLabel("Contrast:"), self.rir_contrast)
 
        self.rir_sharpness = QDoubleSpinBox()
        self.rir_sharpness.setRange(0.0, 2.0); self.rir_sharpness.setSingleStep(0.05)
        self.rir_sharpness.setValue(float(self.settings.get("RearIR_Sharpness", 1.4)))
        rir.addRow(QLabel("Sharpness:"), self.rir_sharpness)
 
        self.rir_brightness = QDoubleSpinBox()
        self.rir_brightness.setRange(-1.0, 1.0); self.rir_brightness.setSingleStep(0.05)
        self.rir_brightness.setValue(float(self.settings.get("RearIR_Brightness", -0.05)))
        rir.addRow(QLabel("Brightness:"), self.rir_brightness)
 
        note_rir = QLabel(
            "AE is off by default to prevent exposure drift\n"
            "as seedlings grow over the experiment.\n"
            "Applied during Rear IR and Combined IR captures."
        )
        note_rir.setStyleSheet(f"color: #90A4AE; font-size: {max(9, int(8 * s))}px;")
        rir.addRow(QLabel(""), note_rir)
 
        tabs.addTab(rir_w, "Rear IR")
 
        # ------------------------------------------------------------------ #
        # Apply / Close buttons (always visible below the tabs)               #
        # ------------------------------------------------------------------ #
        btns = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.close_btn = QPushButton("Close")
        btns.addWidget(self.apply_btn)
        btns.addStretch()
        btns.addWidget(self.close_btn)
        main.addLayout(btns)
 
        self.apply_btn.clicked.connect(self.on_apply)
        self.close_btn.clicked.connect(self.accept)
 
    # ---------------------------------------------------------------------- #
    # Read current lens position from the running camera pipeline             #
    # ---------------------------------------------------------------------- #
    def on_read_focus(self):
        """
        Read LensPosition from the running camera pipeline.
        Runs in a background thread so the dialog never freezes — even if the
        camera is slow or not started (Live View off).
        """
        # Prevent double-clicks while the read is in flight
        self.read_focus_btn.setEnabled(False)
        self.focus_status_lbl.setText("Reading lens position…")
        self.focus_status_lbl.setStyleSheet("color: #FFD600; font-size: 13px;")
 
        class _FocusReader(QThread):
            done = Signal(object)   # emits metadata dict, or {"_error": msg}
            def run(self):
                try:
                    md = camera.get_metadata()
                    self.done.emit(md)
                except Exception as e:
                    self.done.emit({"_error": str(e)})
 
        reader = _FocusReader(self)
        self._focus_reader = reader   # keep reference alive
 
        def _on_done(md):
            self.read_focus_btn.setEnabled(True)
            if "_error" in md:
                self.focus_status_lbl.setText(f"Error reading metadata: {md['_error']}")
                self.focus_status_lbl.setStyleSheet("color: #E53935; font-size: 13px;")
                return
            pos = md.get("LensPosition", None)
            if pos is not None and float(pos) > 0.0:
                self.focus_pos_spin.setValue(float(pos))
                self.focus_status_lbl.setText(
                    f"Captured: {float(pos):.3f} D  "
                    f"(≈ {1.0 / float(pos) * 100:.0f} cm).  "
                    "Check 'Manual Focus' and press Apply."
                )
                self.focus_status_lbl.setStyleSheet("color: #43A047; font-size: 13px;")
            elif pos == 0.0:
                self.focus_status_lbl.setText(
                    "LensPosition is 0.0 — camera not focused yet.  "
                    "Enable Live View and let AF settle first."
                )
                self.focus_status_lbl.setStyleSheet("color: #E53935; font-size: 13px;")
            else:
                self.focus_status_lbl.setText(
                    "No LensPosition data — turn on Live View first."
                )
                self.focus_status_lbl.setStyleSheet("color: #E53935; font-size: 13px;")
 
        reader.done.connect(_on_done)
        reader.start()
 
    # ---------------------------------------------------------------------- #
    # Collect all widget values into a flat dict                              #
    # ---------------------------------------------------------------------- #
    def collect(self) -> dict:
        return {
            "AeEnable":            bool(self.ae_chk.isChecked()),
            "ExposureTime":        int(self.exp_spin.value()),
            "AnalogueGain":        float(self.gain_spin.value()),
            "AwbEnable":           bool(self.awb_chk.isChecked()),
            "Contrast":            float(self.contrast_spin.value()),
            "Brightness":          float(self.brightness_spin.value()),
            "Saturation":          float(self.saturation_spin.value()),
            "Sharpness":           float(self.sharpness_spin.value()),
            "NoiseReductionMode":  int(self.nr_spin.value()),
            "HdrEnable":           bool(self.hdr_chk.isChecked()),
            "ManualFocusEnable":   bool(self.manual_focus_chk.isChecked()),
            "ManualFocusPosition": float(self.focus_pos_spin.value()),
            # Front IR overrides
            "FrontIR_AeEnable":    bool(self.fir_ae_chk.isChecked()),
            "FrontIR_ExposureTime": int(self.fir_exp.value()),
            "FrontIR_Contrast":    float(self.fir_contrast.value()),
            "FrontIR_Sharpness":   float(self.fir_sharpness.value()),
            "FrontIR_Brightness":  float(self.fir_brightness.value()),
            # Rear IR overrides
            "RearIR_AeEnable":     bool(self.rir_ae_chk.isChecked()),
            "RearIR_ExposureTime": int(self.rir_exp.value()),
            "RearIR_Gain":         float(self.rir_gain.value()),
            "RearIR_Contrast":     float(self.rir_contrast.value()),
            "RearIR_Sharpness":    float(self.rir_sharpness.value()),
            "RearIR_Brightness":   float(self.rir_brightness.value()),
        }
 
    # ---------------------------------------------------------------------- #
    # Apply: save to disk, push to camera, apply manual focus if enabled      #
    # ---------------------------------------------------------------------- #
    def on_apply(self):
        self.settings = self.collect()
        save_settings(self.settings)
        if self.settings["ManualFocusEnable"]:
            try:
                camera.set_manual_focus(self.settings["ManualFocusPosition"])
            except Exception:
                pass
        # Dialog stays open so the user can see the effect and fine-tune.