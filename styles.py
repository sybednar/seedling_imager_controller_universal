# styles.py
def dark_style(s: float = 1.0) -> str:
    """
    Return the application stylesheet scaled to screen size.
    s = screen_width / 800  (1.0 on original 800 px display, 1.6 on 1280 px Display2)
    Font and padding sizes scale proportionally; minimum font is 12 px for legibility.
    """
    fs   = max(12, int(11.25 * s))   # body / label / spinbox font
    pad  = max(6,  int(7.5  * s))    # button padding
    r    = max(4,  int(5    * s))    # button border-radius
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
}}
"""