# ═══════════════════════════════════════════════════════════════════════════════
# SEEDLING IMAGER CONTROLLER — UNIVERSAL VERSION  v0.08
# Auto-scales GUI: 800×480 original display (s=1.0) ↔ 1280×720 Display2 (s=1.6)
# Features: dual 940 nm IR illumination, manual focus (7.589 D), tabbed Camera
# Config, AE stability gate, GT2 belt drive with dynamic bracket homing,
# per-mode camera presets, fixed experiment preview snapshot timing.
# ═══════════════════════════════════════════════════════════════════════════════
 
# main.py
import sys
from PySide6.QtWidgets import QApplication
from gui import SeedlingImagerGUI
 
def start_gui():
    app = QApplication(sys.argv)
    window = SeedlingImagerGUI()
    window.showFullScreen()  # dedicated touchscreen kiosk-style fullscreen (changed from window.show())
    sys.exit(app.exec())
 
if __name__ == "__main__":
    start_gui()