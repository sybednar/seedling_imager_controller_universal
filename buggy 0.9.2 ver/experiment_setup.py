
# experiment_setup.py mod 022126
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QGridLayout, QCheckBox, QLineEdit
)
from PySide6.QtCore import Qt
from styles import dark_style
import shutil
from pathlib import Path

ILLUM_GREEN = "Green"
ILLUM_IR = "Infrared"

SEA_FOAM_GREEN = "#26A69A"
DEEP_RED = "#B71C1C"

# ---- constants for storage estimate ----
IMAGES_ROOT = Path("/home/sybednar/Seedling_Imager/images").expanduser()
AVG_IMAGE_MB_GREEN_RGB = 45.0
AVG_IMAGE_MB_IR_GRAY = 10.0


class ExperimentSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experiment Setup")
        self.setStyleSheet(dark_style)
        self.selected_illum = ILLUM_GREEN

        # Geometry-aware sizing so it always fits on 800×480 as well
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        geom = screen.availableGeometry() if screen else None
        if geom:
            # keep within the screen with a small margin
            self.setMinimumWidth(int(min(geom.width() * 0.95, 820)))
            self.setMinimumHeight(int(min(geom.height() * 0.95, 460)))
        else:
            # safe fallbacks if geometry isn't available
            self.setMinimumWidth(580)
            self.setMinimumHeight(420)


        main_layout = QVBoxLayout()

        # Illumination row (unchanged)
        illum_row = QHBoxLayout()
        illum_label = QLabel("Illumination:")
        illum_label.setStyleSheet("font-size: 18px; color: white;")
        self.illum_toggle = QPushButton(self.selected_illum)

        # --- geometry-aware sizing (fits on gen1 800×480 too) ---
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        geom = screen.availableGeometry() if screen else None
        btn_w, btn_h = 160, 48
        if geom and geom.width() <= 800:   # gen1 display
            btn_w, btn_h = 150, 44
        self.illum_toggle.setFixedSize(btn_w, btn_h)
        # ---------------------------------------------------------

        self.apply_illum_style()
        self.illum_toggle.clicked.connect(self.toggle_illum)
        illum_row.addWidget(illum_label)
        illum_row.addStretch()
        illum_row.addWidget(self.illum_toggle)
        main_layout.addLayout(illum_row)


        # Duration (unchanged except signal to recompute estimate)
        duration_layout = QHBoxLayout()
        duration_label = QLabel("Duration (days):")
        duration_label.setStyleSheet("font-size: 18px; color: white;")
        self.duration_value = QLineEdit("1")
        self.duration_value.setAlignment(Qt.AlignCenter)

        # --- geometry-aware sizes for edits and arrow buttons ---
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        geom = screen.availableGeometry() if screen else None
        edit_w, edit_h = 110, 60
        step_w, step_h = 58, 60
        if geom and geom.width() <= 800:   # gen1 display
            edit_w, edit_h = 100, 52
            step_w, step_h = 52, 52
        self.duration_value.setFixedSize(edit_w, edit_h)
        # --------------------------------------------------------

        self.duration_value.setStyleSheet("background-color: white; color: black; font-size: 22px;")
        duration_up = QPushButton("▲"); duration_down = QPushButton("▼")
        for btn in (duration_up, duration_down):
            btn.setFixedSize(step_w, step_h)
            btn.setStyleSheet("background-color: #ccc; font-size: 24px; font-weight: bold;")

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
        freq_label.setStyleSheet("font-size: 18px; color: white;")
        self.freq_value = QLineEdit("1")  # changed to 1 for testing; restore to 30 for production
        self.freq_value.setAlignment(Qt.AlignCenter)

        # --- geometry-aware sizes for edits and arrow buttons ---
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        geom = screen.availableGeometry() if screen else None
        edit_w, edit_h = 110, 60
        step_w, step_h = 58, 60
        if geom and geom.width() <= 800:   # gen1 display
            edit_w, edit_h = 100, 52
            step_w, step_h = 52, 52
        self.freq_value.setFixedSize(edit_w, edit_h)
        # --------------------------------------------------------

        self.freq_value.setStyleSheet("background-color: white; color: black; font-size: 22px;")
        freq_up = QPushButton("▲"); freq_down = QPushButton("▼")
        for btn in (freq_up, freq_down):
            btn.setFixedSize(step_w, step_h)
            btn.setStyleSheet("background-color: #ccc; font-size: 24px; font-weight: bold;")

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
        instruction_label.setStyleSheet("font-size: 18px; color: white;")
        main_layout.addWidget(instruction_label)

        # Two-row plate grid (unchanged except connect signals)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(20); grid_layout.setVerticalSpacing(10)
        self.plate_checkboxes = {}
        for row, names in enumerate([["Plate 1", "Plate 2", "Plate 3"], ["Plate 4", "Plate 5", "Plate 6"]]):
            h = QHBoxLayout(); h.setSpacing(24); h.setAlignment(Qt.AlignCenter)
            for name in names:
                cb = QCheckBox(name)
                cb.setStyleSheet(
                    "QCheckBox { color: white; font-size: 16px; } "
                    "QCheckBox::indicator { width: 22px; height: 22px; } "
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
        self.storage_label.setWordWrap(True)  # NEW: allow multi-line text
        self.storage_label.setStyleSheet("font-size: 15px; color: #CCCCCC;")  # slight reduction helps fit
        main_layout.addWidget(self.storage_label)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Experiment")
        self.exit_button = QPushButton("Exit")
        self.start_button.setStyleSheet("background-color: #43A047; color: white; font-weight: bold; padding: 10px; font-size: 18px;")
        self.exit_button.setStyleSheet("background-color: #E53935; color: white; font-weight: bold; padding: 10px; font-size: 18px;")
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

    # --- existing helpers (illumination & adjust_value) unchanged ---
    def apply_illum_style(self):
        if self.selected_illum == ILLUM_GREEN:
            self.illum_toggle.setStyleSheet(
                f"background-color: {SEA_FOAM_GREEN}; color: white; font-size: 18px; font-weight: bold; border-radius: 8px;"
            )
        else:
            self.illum_toggle.setStyleSheet(
                f"background-color: {DEEP_RED}; color: white; font-size: 18px; font-weight: bold; border-radius: 8px;"
            )

    def toggle_illum(self):
        self.selected_illum = ILLUM_IR if self.selected_illum == ILLUM_GREEN else ILLUM_GREEN
        self.illum_toggle.setText(self.selected_illum)
        self.apply_illum_style()
        self.update_storage_estimate()   # refresh estimate when illumination changes

    def adjust_value(self, line_edit, step, min_val, max_val):
        try:
            current = int(line_edit.text())
        except ValueError:
            current = min_val
        new_val = max(min_val, min(max_val, current + step))
        line_edit.setText(str(new_val))
        # recompute after button presses
        self.update_storage_estimate()

    # ---- NEW: storage estimate computation ----
    def update_storage_estimate(self):
        try:
            duration_days = int(self.duration_value.text())
            frequency_minutes = int(self.freq_value.text())
        except ValueError:
            duration_days = 1
            frequency_minutes = 30

        selected = [name for name, cb in self.plate_checkboxes.items() if cb.isChecked()]
        n_plates = len(selected)

        cycles = int((duration_days * 24 * 60) / max(1, frequency_minutes))
        images = n_plates * cycles      
        # Choose estimated per-image size based on illumination mode
        avg_mb = AVG_IMAGE_MB_IR_GRAY if self.selected_illum == ILLUM_IR else AVG_IMAGE_MB_GREEN_RGB
        est_gb = (images * avg_mb) / 1024.0


        # disk free
        try:
            total, used, free = shutil.disk_usage(IMAGES_ROOT)
            free_gb = free / (1024 ** 3)
        except Exception:
            free_gb = None

        if n_plates == 0:
            msg = "No plates selected — storage estimate unavailable."
            style = "font-size: 16px; color: #CCCCCC;"
        else:
            mode_label = "IR grayscale" if self.selected_illum == ILLUM_IR else "Green RGB"
            msg = f"Estimated storage: ~{est_gb:.1f} GB ({images} images over {cycles} cycles, {mode_label} ~{avg_mb:.0f} MB/img)"

            if free_gb is not None:
                msg += f"  |  Free: {free_gb:.1f} GB"
                style = "font-size: 16px; color: #43A047;" if est_gb <= free_gb else "font-size: 16px; color: #E53935;"
            else:
                style = "font-size: 16px; color: #CCCCCC;"

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