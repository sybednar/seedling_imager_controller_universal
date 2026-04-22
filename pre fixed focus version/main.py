# main.py
import sys
from PySide6.QtWidgets import QApplication
from gui import SeedlingImagerGUI

def start_gui():
    app = QApplication(sys.argv)
    window = SeedlingImagerGUI()
    window.showFullScreen()  # kiosk-style fullscreen
    sys.exit(app.exec())

if __name__ == "__main__":
    start_gui()