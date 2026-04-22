# experiment_setup.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QGridLayout, QCheckBox, QLineEdit
)
from PySide6.QtCore import Qt
from styles import dark_style
import shutil
from pathlib import Path
 
ILLUM_FRONT_IR   = "Front IR"      # reflectance, GPIO13
ILLUM_REAR_IR    = "Rear IR"       # transmission, GPIO12
ILLUM_COMBINED   = "Combined IR"   # both panels, GPIO12 + GPIO13
 
IMAGES_ROOT = Path("/home/sybednar/Seedling_Imager/images")  # for disk-usage estimate
 
 
# Color map for the toggle button:
ILLUM_COLORS = {
    ILLUM_FRONT_IR:  "#B71C1C",   # deep red
    ILLUM_REAR_IR:   "#1565C0",   # deep blue (distinct)
    ILLUM_COMBINED:  "#6A1B9A",   # purple = front+rear
}
 
# Storage estimates (all IR grayscale now)
AVG_IMAGE_MB_IR_GRAY = 10.0
AVG_IMAGE_MB_FRONT_IR  = 10.0
AVG_IMAGE_MB_REAR_IR   = 10.0
AVG_IMAGE_MB_COMBINED  = 10.0   # same file size; two captures per plate if sequential
 
 
class ExperimentSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # --- Universal screen scaling ---
        try:
            from PySide6.QtGui import QGuiApplication
            _scr = QGuiApplication.primaryScreen()
            _geom = _scr.availableGeometry() if _scr else None
            s = (_geom.width() / 800.0) if _geom else 1.0
        except Exception:
            s = 1.0
        s = max(1.0, s)
        self.setWindowTitle("Experiment Setup")
        self.setMinimumWidth(int(544 * s))   # 870 px on Display2 (1.6×)
        self.setMinimumHeight(int(325 * s))  # 520 px on Display2
        self.setStyleSheet(dark_style(s))
 
        self.selected_illum = ILLUM_FRONT_IR
 
        main_layout = QVBoxLayout()
 
        # Illumination row (unchanged)
        illum_row = QHBoxLayout()
        illum_label = QLabel("Illumination:")
        illum_label.setStyleSheet(f"font-size: {max(12, int(11.25 * s))}px; color: white;")
        self.illum_toggle = QPushButton(self.selected_illum)
        self.illum_toggle.setFixedSize(int(100 * s), int(30 * s))
        self.apply_illum_style()
        self.illum_toggle.clicked.connect(self.toggle_illum)
        illum_row.addWidget(illum_label)
        illum_row.addStretch()
        illum_row.addWidget(self.illum_toggle)
        main_layout.addLayout(illum_row)
 
        # Duration (unchanged except signal to recompute estimate)
        duration_layout = QHBoxLayout()
        duration_label = QLabel("Duration (days):")
        duration_label.setStyleSheet(f"font-size: {max(12, int(11.25 * s))}px; color: white;")
        self.duration_value = QLineEdit("1")
        self.duration_value.setAlignment(Qt.AlignCenter)
        self.duration_value.setFixedSize(int(69 * s), int(38 * s))
        self.duration_value.setStyleSheet(f"background-color: white; color: black; font-size: {max(12, int(14 * s))}px;")
        duration_up = QPushButton("▲"); duration_down = QPushButton("▼")
        for btn in (duration_up, duration_down):
            btn.setFixedSize(int(36 * s), int(38 * s))
            btn.setStyleSheet(f"background-color: #ccc; font-size: {max(12, int(15 * s))}px; font-weight: bold;")
        duration_up.clicked.connect(lambda: self.adjust_value(self.duration_value, 1, 1, 7))
        duration_down.clicked.connect(lambda: self.adjust_value(self.duration_value, -1, 1, 7))
        # Recompute when value is edited manually
        self.duration_value.textChanged.connect(self.update_storage_estimate)
        duration_layout.addWidget(duration_label)
        duration_layout.addStretch()
        duration_layout.addWidget(duration_up)
        duration_layout.addWidget(self.duration_value)
        duration_layout.addWidget(duration_down)
        main_layout.addLayout(duration_layout)
 
        # Frequency
        freq_layout = QHBoxLayout()
        freq_label = QLabel("Acquisition Frequency (minutes):")
        freq_label.setStyleSheet(f"font-size: {max(12, int(11.25 * s))}px; color: white;")
        self.freq_value = QLineEdit("30")   # 30 min default for experiments
        self.freq_value.setAlignment(Qt.AlignCenter)
        self.freq_value.setFixedSize(int(69 * s), int(38 * s))
        self.freq_value.setStyleSheet(f"background-color: white; color: black; font-size: {max(12, int(14 * s))}px;")
        freq_up = QPushButton("▲"); freq_down = QPushButton("▼")
        for btn in (freq_up, freq_down):
            btn.setFixedSize(int(36 * s), int(38 * s))
            btn.setStyleSheet(f"background-color: #ccc; font-size: {max(12, int(15 * s))}px; font-weight: bold;")
        freq_up.clicked.connect(lambda: self.adjust_value(self.freq_value, 30, 1, 360))
        freq_down.clicked.connect(lambda: self.adjust_value(self.freq_value, -30, 1, 360))
        # Recompute when value is edited manually
        self.freq_value.textChanged.connect(self.update_storage_estimate)
        freq_layout.addWidget(freq_label)
        freq_layout.addStretch()
        freq_layout.addWidget(freq_up)
        freq_layout.addWidget(self.freq_value)
        freq_layout.addWidget(freq_down)
        main_layout.addLayout(freq_layout)
 
        # Instruction
        instruction_label = QLabel("Select plates for experiment:")
        instruction_label.setAlignment(Qt.AlignCenter)
        instruction_label.setStyleSheet(f"font-size: {max(12, int(11.25 * s))}px; color: white;")
        main_layout.addWidget(instruction_label)
 
        # Two-row plate grid (unchanged except connect signals)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(20); grid_layout.setVerticalSpacing(10)
        self.plate_checkboxes = {}
        for row, names in enumerate([["Plate 1", "Plate 2", "Plate 3"], ["Plate 4", "Plate 5", "Plate 6"]]):
            h = QHBoxLayout(); h.setSpacing(24); h.setAlignment(Qt.AlignCenter)
            for name in names:
                cb = QCheckBox(name)
                _cbfs  = max(10, int(10 * s))
                _cbind = max(14, int(14 * s))
                cb.setStyleSheet(
                    f"QCheckBox {{ color: white; font-size: {_cbfs}px; }} "
                    f"QCheckBox::indicator {{ width: {_cbind}px; height: {_cbind}px; }} "
                    "QCheckBox::indicator:unchecked { border: 2px solid #BBBBBB; background: #222222; } "
                    "QCheckBox::indicator:checked { border: 2px solid #1E88E5; background: #1E88E5; } "
                )
                cb.toggled.connect(self.update_storage_estimate)  # <-- recompute when plate selection changes
                self.plate_checkboxes[name] = cb
                h.addWidget(cb)
            main_layout.addLayout(h)
 
        # ---- storage estimate label ----
        self.storage_label = QLabel("")
        self.storage_label.setAlignment(Qt.AlignCenter)
        self.storage_label.setWordWrap(True)
        self.storage_label.setStyleSheet(f"font-size: {max(9, int(9.4 * s))}px; color: #CCCCCC;")
        main_layout.addWidget(self.storage_label)
 
        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Experiment")
        self.exit_button = QPushButton("Exit")
        _bfs = max(12, int(11.25 * s))
        _bpad = max(5, int(6.25 * s))
        self.start_button.setStyleSheet(f"background-color: #43A047; color: white; font-weight: bold; padding: {_bpad}px; font-size: {_bfs}px;")
        self.exit_button.setStyleSheet(f"background-color: #E53935; color: white; font-weight: bold; padding: {_bpad}px; font-size: {_bfs}px;")
        self.start_button.clicked.connect(self.validate_and_start)
        self.exit_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.exit_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
 
        self.setLayout(main_layout)
 
        # Initial compute
        self.update_storage_estimate()
 
    # ---  helpers (illumination & adjust_value) ---
    def toggle_illum(self):
        order = [ILLUM_FRONT_IR, ILLUM_REAR_IR, ILLUM_COMBINED]
        idx = order.index(self.selected_illum)
        self.selected_illum = order[(idx + 1) % len(order)]
        self.illum_toggle.setText(self.selected_illum)
        self.apply_illum_style()
        self.update_storage_estimate()
 
    def apply_illum_style(self):
        color = ILLUM_COLORS.get(self.selected_illum, "#B71C1C")
        # font-size inherited from dark_style(s); override colour only here
        self.illum_toggle.setStyleSheet(
            f"background-color: {color}; color: white; font-weight: bold; border-radius: 4px;"
        )
 
    def adjust_value(self, line_edit, step, min_val, max_val):
        try:
            current = int(line_edit.text())
        except ValueError:
            current = min_val
        new_val = max(min_val, min(max_val, current + step))
        line_edit.setText(str(new_val))
        # recompute after button presses
        self.update_storage_estimate()
 
    # ---- storage estimate computation ----
    def update_storage_estimate(self):
            try:
                duration_days      = int(self.duration_value.text())
                frequency_minutes  = int(self.freq_value.text())
            except ValueError:
                duration_days, frequency_minutes = 1, 30
 
            selected = [name for name, cb in self.plate_checkboxes.items() if cb.isChecked()]
            n_plates = len(selected)
 
            cycles    = int((duration_days * 24 * 60) / max(1, frequency_minutes))
            images    = n_plates * cycles
 
            # All modes are IR grayscale — use a single per-image size estimate
            avg_mb    = AVG_IMAGE_MB_IR_GRAY
            est_gb    = (images * avg_mb) / 1024.0
 
            mode_label = {
                ILLUM_FRONT_IR:  "front IR gray",
                ILLUM_REAR_IR:   "rear IR gray",
                ILLUM_COMBINED:  "combined IR gray",
            }.get(self.selected_illum, "IR gray")
 
            try:
                total, used, free = shutil.disk_usage(IMAGES_ROOT)
                free_gb = free / (1024 ** 3)
            except Exception:
                free_gb = None
 
            if n_plates == 0:
                msg   = "No plates selected — storage estimate unavailable."
                style = "color: #CCCCCC;"
            else:
                msg = (
                    f"Estimated storage: ~{est_gb:.1f} GB "
                    f"({images} images over {cycles} cycles, {mode_label} ~{avg_mb:.0f} MB/img)"
                )
                if free_gb is not None:
                    msg += f"  |  Free: {free_gb:.1f} GB"
                    style = "color: #43A047;" if est_gb <= free_gb else "color: #E53935;"
                else:
                    style = "color: #CCCCCC;"
 
            self.storage_label.setText(msg)
            self.storage_label.setStyleSheet(style)
 
    def validate_and_start(self):
        selected = [name for name, cb in self.plate_checkboxes.items() if cb.isChecked()]
        if not selected:
            QMessageBox.warning(self, "Validation Error", "Please select at least one plate before starting the experiment.")
            return
        self.selected_plates = selected
        self.duration_days = int(self.duration_value.text())
        self.frequency_minutes = int(self.freq_value.text())
        self.accept()