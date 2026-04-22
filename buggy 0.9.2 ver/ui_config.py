# ui_config.py
from dataclasses import dataclass, asdict
from pathlib import Path
import json
from PySide6.QtCore import QRect

@dataclass
class UIConfig:
    display_profile: str = "auto"  # "auto" | "gen1_800x480" | "gen2_1280x720"
    fullscreen: bool = True

CFG_PATH = Path("ui_config.json")

def load_ui_config() -> UIConfig:
    if CFG_PATH.exists():
        try:
            data = json.loads(CFG_PATH.read_text())
            return UIConfig(**{**UIConfig().__dict__, **data})
        except Exception:
            pass
    return UIConfig()

def save_ui_config(cfg: UIConfig):
    CFG_PATH.write_text(json.dumps(asdict(cfg), indent=2))

def detect_display_profile(rect: QRect) -> str:
    w, h = rect.width(), rect.height()
    wh = tuple(sorted((w, h)))
    if wh == (480, 800):
        return "gen1_800x480"
    if wh == (720, 1280):
        return "gen2_1280x720"
    return "gen2_1280x720" if max(wh) >= 1000 else "gen1_800x480"

def compute_scale_for_profile(rect: QRect, profile: str) -> float:
    BASE_W, BASE_H = 800, 480
    s = min(rect.width()/BASE_W, rect.height()/BASE_H)
    return max(1.0, s)