#main.py version 0.9.2

import sys, json
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication
from gui import SeedlingImagerGUI

# new small helper module (see below)
from ui_config import load_ui_config, save_ui_config, detect_display_profile, compute_scale_for_profile, UIConfig

def start_gui():
    app = QApplication(sys.argv)

    cfg = load_ui_config()
    screen = QGuiApplication.primaryScreen()
    rect = screen.availableGeometry() if screen else None

    # Decide profile if auto
    if rect and cfg.display_profile == "auto":
        cfg.display_profile = detect_display_profile(rect)
        save_ui_config(cfg)  # persist first-run detection

    window = SeedlingImagerGUI(ui_config=cfg, screen_rect=rect)
    if cfg.fullscreen:
        window.showFullScreen()
    else:
        window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    start_gui()