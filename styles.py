# styles.py
import os as _os

# ---------------------------------------------------------------------------
# Tiny SVG arrow icons written alongside this module on first import.
# Qt6 QSS requires an explicit image: url(...) in ::up-arrow / ::down-arrow
# whenever any stylesheet rule touches QSpinBox — otherwise the arrows vanish.
# QDoubleSpinBox is intentionally left OUT of the stylesheet so Qt continues
# to render it with its native platform arrows (no SVG files needed for it).
# ---------------------------------------------------------------------------
_DIR           = _os.path.dirname(_os.path.abspath(__file__))
_UP_SVG_PATH   = _os.path.join(_DIR, "_spinbox_arrow_up.svg")
_DOWN_SVG_PATH = _os.path.join(_DIR, "_spinbox_arrow_down.svg")

def _write_arrow_svgs() -> None:
    _UP   = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'><path d='M0 6 L5 0 L10 6Z' fill='#BBBBBB'/></svg>"
    _DOWN = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'><path d='M0 0 L5 6 L10 0Z' fill='#BBBBBB'/></svg>"
    for path, content in [(_UP_SVG_PATH, _UP), (_DOWN_SVG_PATH, _DOWN)]:
        try:
            with open(path, 'w') as _f:
                _f.write(content)
        except Exception:
            pass

_write_arrow_svgs()


def dark_style(s: float = 1.0) -> str:
    """
    Return the application stylesheet scaled to screen size.
    s = screen_width / 800  (1.0 on original 800 px display, 1.6 on 1280 px Display2)
    Font and padding sizes scale proportionally; minimum font is 12 px for legibility.
    """
    fs    = max(12, int(11.25 * s))   # body / label / spinbox font
    pad   = max(6,  int(7.5  * s))    # button padding
    r     = max(4,  int(5    * s))    # button border-radius
    btn_w = max(18, int(22   * s))    # QSpinBox up/down button width (px)
    aw    = max(6,  int(8    * s))    # arrow image width  (px)
    ah    = max(4,  int(5    * s))    # arrow image height (px)

    # Qt QSS requires forward slashes even on Windows
    up_url   = _UP_SVG_PATH.replace('\\', '/')
    down_url = _DOWN_SVG_PATH.replace('\\', '/')

    return f"""
QWidget {{
    background-color: #121212;
    color: #FFFFFF;
    font-size: {fs}px;
}}

QPushButton {{
    background-color: #1E88E5;
    color: #FFFFFF;
    border-radius: {r}px;
    padding: {pad}px;
    font-size: {fs}px;
}}

QPushButton:hover {{
    background-color: #1565C0;
}}

QLabel {{
    font-size: {fs}px;
}}

QSpinBox {{
    background-color: #1E1E1E;
    color: #FFFFFF;
    border: 1px solid #333333;
    font-size: {fs}px;
    padding-right: {btn_w + 2}px;
}}

QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: {btn_w}px;
    background-color: #2C2C2C;
    border-left: 1px solid #444444;
    border-bottom: 1px solid #333333;
}}

QSpinBox::up-button:hover {{
    background-color: #3E3E3E;
}}

QSpinBox::up-button:pressed {{
    background-color: #141414;
}}

QSpinBox::up-arrow {{
    image: url({up_url});
    width: {aw}px;
    height: {ah}px;
}}

QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: {btn_w}px;
    background-color: #2C2C2C;
    border-left: 1px solid #444444;
    border-top: 1px solid #333333;
}}

QSpinBox::down-button:hover {{
    background-color: #3E3E3E;
}}

QSpinBox::down-button:pressed {{
    background-color: #141414;
}}

QSpinBox::down-arrow {{
    image: url({down_url});
    width: {aw}px;
    height: {ah}px;
}}
"""