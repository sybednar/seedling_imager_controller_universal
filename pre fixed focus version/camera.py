
# camera.py
from picamera2 import Picamera2
from PySide6.QtGui import QImage
import numpy as np
import cv2
import threading
from pathlib import Path
import json

# Try to import tifffile for TIFF saving (optional but recommended)
try:
    import tifffile as tiff
except ImportError:
    tiff = None  # save_image() will fall back to OpenCV for non-TIFF paths

# =============================================================================
# Settings persistence (camera_settings.json)
# =============================================================================
DEFAULTS = {
    "AeEnable": True,          # Auto Exposure on/off
    "ExposureTime": 20000,     # microseconds (used only when AE is False)
    "AnalogueGain": 1.0,       # sensor analogue gain (ISO-like)
    "AwbEnable": True,         # Auto White Balance on/off
    "Contrast": 1.0,
    "Brightness": 0.0,         # typically -1.0 .. +1.0
    "Saturation": 1.0,
    "Sharpness": 1.0,
    "NoiseReductionMode": 0,   # 0=off (preferred for scientific imaging)
    "HdrEnable": False         # keep HDR off for full-res work
}
SETTINGS_PATH = Path("camera_settings.json")

def load_settings() -> dict:
    """Load camera settings from JSON; fall back to DEFAULTS on error."""
    if SETTINGS_PATH.exists():
        try:
            return {**DEFAULTS, **json.loads(SETTINGS_PATH.read_text())}
        except Exception:
            pass
    return DEFAULTS.copy()

def save_settings(settings: dict) -> bool:
    """Persist camera settings to JSON."""
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        return True
    except Exception:
        return False

# =============================================================================
# IR "Quant" preset helpers (temporary overlay; does NOT persist to JSON)
# =============================================================================
IR_QUANT_PRESET = {
    "Saturation": 0.0,   # reduce false color in IR
    "AwbEnable": False,  # stabilize channel gains
    "NoiseReductionMode": 0,
    "Contrast": 1.10,
    "Sharpness": 1.15,
    "Brightness": 0.0,
    "AeEnable": True,
}

def apply_ir_quant_preset(base: dict | None) -> dict:
    """Return non-persistent settings dict for IR root imaging."""
    s = dict(base) if base else {}
    s.update(IR_QUANT_PRESET)
    return s

def set_manual_exposure_gain(exposure_us: int, gain: float) -> None:
    """Pin exposure and gain after AE settles."""
    try:
        picam.set_controls({
            "AeEnable": False,
            "ExposureTime": int(exposure_us),
            "AnalogueGain": float(gain),
        })
    except Exception as e:
        print(f"set_manual_exposure_gain error: {e}", flush=True)

# --- Live-view boost state (module-level) ---
_liveview_boost_active = False
_liveview_saved_controls = None

def enable_liveview_boost_for_ir(target_gain: float = 8.0, target_exposure_us: int = 20000) -> None:
    """Temporarily brighten the IR live view; clear with disable_liveview_boost()."""
    global _liveview_boost_active, _liveview_saved_controls
    if _liveview_boost_active:
        return
    try:
        md = get_metadata() or {}
        _liveview_saved_controls = {
            "AeEnable": md.get("AeEnable", True),
            "ExposureTime": md.get("ExposureTime", None),
            "AnalogueGain": md.get("AnalogueGain", None),
            "AwbEnable": md.get("AwbEnable", True),
        }
        try:
            set_auto_exposure(True)
        except Exception:
            pass
        controls = {
            "AnalogueGain": float(target_gain),
            "ExposureTime": int(target_exposure_us),
            "AeEnable": True,
            "AwbEnable": False,
        }
        picam.set_controls(controls)
        _liveview_boost_active = True
        print("[camera] Live-view IR boost enabled", flush=True)
    except Exception as e:
        print(f"[camera] liveview boost error: {e}", flush=True)

def disable_liveview_boost() -> None:
    """Restore controls saved by enable_liveview_boost_for_ir()."""
    global _liveview_boost_active, _liveview_saved_controls
    if not _liveview_boost_active:
        return
    try:
        if isinstance(_liveview_saved_controls, dict):
            picam.set_controls({
                "AeEnable": bool(_liveview_saved_controls.get("AeEnable", True)),
                "AwbEnable": bool(_liveview_saved_controls.get("AwbEnable", True)),
            })
            prev_exp = _liveview_saved_controls.get("ExposureTime", None)
            prev_gain = _liveview_saved_controls.get("AnalogueGain", None)
            if prev_exp is not None and prev_gain is not None and not _liveview_saved_controls.get("AeEnable", True):
                picam.set_controls({"ExposureTime": int(prev_exp), "AnalogueGain": float(prev_gain)})

        _liveview_boost_active = False
        _liveview_saved_controls = None
        print("[camera] Live-view IR boost disabled (restored controls)", flush=True)
    except Exception as e:
        print(f"[camera] liveview boost restore error: {e}", flush=True)

# =============================================================================
# Picamera2 dual-stream setup
# =============================================================================
picam = Picamera2()
_cam_lock = threading.Lock()

# Full-res still (main) + low-res preview (lores).
# Adjust 'main' size if your sensor reports a different maximum.
preview_and_still_cfg = picam.create_still_configuration(
    main={"size": (4608, 2592), "format": "RGB888"},   # full-resolution for saving
    lores={"size": (1280, 720), "format": "RGB888"}     # 16:9 preview for Live View
)
picam.configure(preview_and_still_cfg)

def apply_settings(settings: dict = None) -> None:
    """
    Apply camera settings to Picamera2. If 'settings' is None, load from JSON.
    Note: ExposureTime is only set when AE is disabled (AeEnable=False).
    """
    if settings is None:
        settings = load_settings()

    ctrl = {
        "AeEnable":          bool(settings.get("AeEnable", True)),
        "AwbEnable":         bool(settings.get("AwbEnable", True)),
        "AnalogueGain":      float(settings.get("AnalogueGain", 1.0)),
        "Contrast":          float(settings.get("Contrast", 1.0)),
        "Brightness":        float(settings.get("Brightness", 0.0)),
        "Saturation":        float(settings.get("Saturation", 1.0)),
        "Sharpness":         float(settings.get("Sharpness", 1.0)),
        "NoiseReductionMode":int(settings.get("NoiseReductionMode", 0)),
    }
    # Apply manual exposure only if AE is off
    if not ctrl["AeEnable"]:
        ctrl["ExposureTime"] = int(settings.get("ExposureTime", 20000))

    try:
        picam.set_controls(ctrl)
    except Exception as e:
        print(f"apply_settings error: {e}", flush=True)

def get_current_settings() -> dict:
    """Return the last saved (or default) settings for UI convenience."""
    return load_settings()

# =============================================================================
# Start/stop camera
# =============================================================================
def start_camera() -> None:
    """Start Picamera2 pipeline (idempotent). Also enable Continuous AF for Live View."""
    try:
        picam.start()
        set_af_mode(2)  # Continuous AF for preview comfort
    except Exception:
        # ignore if already started
        pass

def stop_camera() -> None:
    """Stop Picamera2 pipeline."""
    try:
        picam.stop()
    except Exception:
        pass

# =============================================================================
# Exposure & autofocus helpers
# =============================================================================
def set_auto_exposure(enabled: bool) -> None:
    """Enable/disable auto exposure."""
    try:
        picam.set_controls({"AeEnable": bool(enabled)})
    except Exception as e:
        print(f"set_auto_exposure error: {e}", flush=True)

def set_af_mode(mode: int = 2) -> None:
    """
    Set autofocus mode:
      0 = Manual, 1 = Auto (single), 2 = Continuous.
    """
    try:
        picam.set_controls({"AfMode": int(mode)})
    except Exception as e:
        print(f"set_af_mode error: {e}", flush=True)

def trigger_autofocus() -> None:
    """
    Trigger a single autofocus cycle (useful during settle when AfMode=1).
    """
    try:
        picam.set_controls({"AfTrigger": 1})  # start AF cycle
    except Exception as e:
        print(f"trigger_autofocus error: {e}", flush=True)

# =============================================================================
# Internal conversion utilities
# =============================================================================
def _to_rgb(arr: np.ndarray) -> np.ndarray:
    """
    Normalize any returned frame to RGB (HxWx3, uint8).
    Although we requested RGB888, guard against BGRA/BGR inputs.
    """
    if arr.ndim == 3:
        h, w, c = arr.shape
        if c == 4:
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
        elif c == 3:
            # If already RGB this becomes a no-op; if BGR it flips channels.
            return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        else:
            return arr[:, :, :3].copy()
    # Grayscale to RGB
    return cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)

# =============================================================================
# Live View (lores stream → QImage for GUI)
# =============================================================================
def get_frame() -> QImage:
    """
    Return a QImage (RGB888) for the preview label using the lores stream.
    """
    try:
        with _cam_lock:
            arr = picam.capture_array("lores")  # 640x360; fast preview
    except Exception as e:
        print(f"get_frame error: {e}", flush=True)
        return QImage()

    rgb = _to_rgb(arr)
    h, w = rgb.shape[:2]
    rgb_c = np.ascontiguousarray(rgb)
    bytes_per_line = w * 3
    qimg = QImage(rgb_c.data, w, h, bytes_per_line, QImage.Format_RGB888)
    return qimg.copy()  # detach from numpy buffer

# =============================================================================
# Saving full-res frames (main stream)
# =============================================================================
_last_saved_shape: tuple[int, int] | None = None  # (height, width) of last saved image

def save_image(path: str, grayscale: bool = False) -> bool:
    """Capture full-res frame; optionally save single-channel grayscale (IR)."""
    try:
        global _last_saved_shape
        with _cam_lock:
            arr = picam.capture_array("main")
        rgb = _to_rgb(arr)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        ext = Path(path).suffix.lower()

        if grayscale:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape[:2]
            _last_saved_shape = (h, w)
            if ext in (".tif", ".tiff") and tiff is not None:
                tiff.imwrite(path, gray, photometric="minisblack", compression="zlib")
                return True
            return cv2.imwrite(path, gray)

        h, w = rgb.shape[:2]
        _last_saved_shape = (h, w)
        if ext in (".tif", ".tiff") and tiff is not None:
            tiff.imwrite(path, rgb, photometric="rgb", compression="zlib")
            return True
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return cv2.imwrite(path, bgr)
    except Exception as e:
        print(f"save_image error: {e}", flush=True)
        return False


# =============================================================================
# Capture metadata (for CSV logging)
# =============================================================================
def get_metadata() -> dict:
    """
    Return a dictionary of useful capture metadata from Picamera2.
    Keys may include (depending on pipeline):
      - 'AeEnable', 'ExposureTime' (µs), 'AnalogueGain', 'AwbEnable'
    """
    out = {}
    try:
        with _cam_lock:
            md = picam.capture_metadata()  # Picamera2 metadata dict
        # Normalize common fields (add more here if you need them)
        out["AeEnable"]      = md.get("AeEnable", None)
        out["ExposureTime"]  = md.get("ExposureTime", None)   # microseconds
        out["AnalogueGain"]  = md.get("AnalogueGain", None)
        out["AwbEnable"]     = md.get("AwbEnable", None)
        out["LensPosition"] = md.get("LensPosition", None)
        out["AfState"] = md.get("AfState", None)
        out["FocusFoM"] = md.get("FocusFoM", None)
     
    except Exception as e:
        print(f"get_metadata error: {e}", flush=True)
    return out

def get_last_saved_shape() -> tuple[int, int] | None:
    """Return (height, width) of the last saved full-res image, or None."""
    return _last_saved_shape
