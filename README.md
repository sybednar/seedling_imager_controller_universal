
# Seedling Imager Controller

## Overview
Inspired by the SPIRO (Smart Plate Imaging Robot; Ohlsson et al The Plant Journal doi: 10.1111/tpj.16587) project the **Seedling Imager** is a Raspberry Pi 5-based imaging system designed to monitor Arabidopsis seedling growth using a 6-position hexagonal carousel. It provides automated imaging, LED control, and experiment scheduling through a touch-friendly GUI.

# Seedling Imager Controller — Universal

**v1.0.0** · Raspberry Pi 5 · PySide6 · picamera2 · GT2 belt carousel

A touchscreen controller for automated timelapse imaging of seedling plates using near-infrared (940 nm) transmission and front illumination. A single codebase runs on both supported display configurations without any code changes.

---

## Supported Hardware

| Component | System 1 (original) | System 2 |
|---|---|---|
| Display | Original 800×480 DSI touchscreen | Raspberry Pi Touch Display 2 (1280×720) |
| Scale factor `s` | 1.0 | 1.6 |
| Camera | Raspberry Pi HQ Camera | Raspberry Pi HQ Camera |
| Compute | Raspberry Pi 5 | Raspberry Pi 5 |
| Motor | Stepper + GT2 belt carousel | Stepper + GT2 belt carousel |
| Illumination | Dual 940 nm IR LEDs (front + rear) | Dual 940 nm IR LEDs (front + rear) |
| Optical sensor | Photointerrupter (hall + flag) | Photointerrupter (hall + flag) |

GUI layout, font sizes, button heights, and dialog dimensions all auto-scale via `s = screen_width / 800`. No separate display-specific files are needed.

---

## Key Features (v1.0.0)

### GUI & Display
- Auto-scaling dark theme UI: `s = screen_width / 800` (1.0 at 800 px, 1.6 at 1280 px)
- Fullscreen kiosk mode; all widget dimensions computed as `int(X * s)`
- `dark_style(s)` parameterized stylesheet — font, padding, and border-radius all scale

### Imaging
- Dual 940 nm IR illumination modes: **Front IR**, **Rear IR (transmission)**, **Combined**
- Per-mode camera presets stored in `camera_settings.json` (`FrontIR_*` / `RearIR_*` keys)
- Manual focus locked at 9.045 diopters (~11 cm) via `set_manual_focus()` at camera start
  - PDAF non-functional through 940 nm bandpass filter; manual focus required
- 16-bit grayscale TIFF output (`tifffile`; OpenCV fallback for non-TIFF formats)
- AE stability gate: polls `AnalogueGain` until < 5% relative change over 5 consecutive reads before pinning exposure
- `settling_started` signal emitted **after** AE is pinned and 0.20 s settle — GUI preview snapshot matches saved image exposure
- Live-view IR boost (mode-specific gain/exposure floor) enabled during preview, disabled before capture

### Motor / Carousel
- GT2 belt drive with dynamic bracket homing:
  1. CCW to LOW (leading edge of optical flag)
  2. CCW to HIGH (past leading edge)
  3. CW to LOW (re-validate leading edge)
  4. CW + `mid` µsteps to geometric center
- Optical window `W` measured physically each homing run by counting µsteps CW across the sensor aperture
  - System 1 (post-alignment): W = 23–24 µsteps
  - System 2: W = 20–21 µsteps
  - W is **not** a configurable parameter — it is measured live every homing cycle
- `CENTER_BACKOFF_FRAC = 0.0`: places carousel at exact geometric center regardless of W
  - Formula: `mid = max(1, int(round(W / 2.0 * (1.0 - CENTER_BACKOFF_FRAC))))`
  - Increase slightly (e.g. 0.05) only if consistent leading-edge drift is observed
- Log output includes `frac=` and `W=` on every homing for traceability

### Camera Config Dialog
- Tabbed interface: General settings + IR-specific presets
- Non-blocking "Read Current Position from Camera" button — `_FocusReader(QThread)` worker prevents GUI freeze when Live View is off
- Button disabled during read, re-enabled on completion or error

### Experiment Setup
- Configurable plate selection, frequency (default 30 min), duration, illumination mode
- Disk usage estimate uses `IMAGES_ROOT = Path("/home/sybednar/Seedling_Imager/images")`
- Storage label colour: green (sufficient free space) / red (insufficient)

### File Manager
- Thumbnail grid with per-image metadata overlay
- Scaled thumbnail size: `QSize(int(100 * s), int(100 * s))`

---

## Module Structure

```
seedling_imager_controller/
├── main.py                  # Entry point; launches QApplication fullscreen
├── gui.py                   # Main window; computes s = screen_width / 800
├── styles.py                # dark_style(s) — parameterized stylesheet
├── camera.py                # Picamera2 wrapper; manual focus; TIFF save; AE gate
├── camera_config.py         # Camera Config dialog; _FocusReader QThread
├── motor_control.py         # Stepper driver; dynamic bracket homing; CENTER_BACKOFF_FRAC
├── experiment_runner.py     # Timelapse loop; AE settle; settling_started signal
├── experiment_setup.py      # Setup dialog; plate/frequency/mode/disk usage
├── file_manager.py          # File browser with thumbnail grid
├── camera_settings.json     # Persisted camera presets (FrontIR_*, RearIR_* keys)
├── git_update.sh            # Convenience script for commit + tag + push
└── README.md
```

---

## Dependencies

```
python3-picamera2
python3-pyside6
python3-numpy
python3-opencv   (cv2)
tifffile         (pip install tifffile — recommended for 16-bit TIFF output)
RPi.GPIO or gpiozero  (stepper/LED GPIO)
```

Install tifffile if not present:

```bash
pip install tifffile --break-system-packages
```

---

## Setup

### Clone to Raspberry Pi

```bash
cd /home/sybednar/Seedling_Imager
git clone https://github.com/sybednar/seedling_imager_controller_universal.git seedling_imager_controller
cd seedling_imager_controller
```

### Run manually

```bash
cd /home/sybednar/Seedling_Imager/seedling_imager_controller
python3 main.py
```

### Autostart

The controller is configured to start fullscreen at login via a `.desktop` launcher or systemd user service. See the existing autostart configuration on each Pi.

---

## Calibration Notes

### Manual Focus
- System 1: `LensPosition = 9.045` diopters (~11 cm working distance)
- System 2: measure and update `ManualFocusPosition` in `camera_settings.json`
- PDAF is non-functional through the 940 nm bandpass filter on both systems

### Optical Window W
W is measured automatically on every homing cycle — no manual configuration needed.

| System | Typical W | mid |
|---|---|---|
| System 1 (post pulley/tension alignment) | 23–24 µsteps | 12 |
| System 2 | 20–21 µsteps | 10–11 |

If W falls back toward 12 on System 1, check pulley alignment and belt tension — a clean flag traverse should give W ≥ 20.

### CENTER_BACKOFF_FRAC
At the top of `motor_control.py`. Default `0.0` places the carousel at exact geometric window center. Only increase if consistent leading-edge drift is observed in registration analysis.

---

## Version History

### v1.0.0 — 2026-04-22 — Universal release

**Architecture**
- Single codebase runs on both 800×480 and 1280×720 displays without modification
- `s = screen_width / 800` computed once in `gui.py`; every pixel dimension expressed as `int(X * s)`
- `dark_style(s)` replaces fixed stylesheet string; font, padding, border-radius all scale with `s`

**Motor / centering fix**
- `CENTER_BACKOFF_FRAC = 0.0` replaces fixed `CENTER_BACKOFF = 5`
- Fixes System 1 centering error: with W=12 the old formula gave `mid=1` (leading edge) instead of `mid=6` (center)
- After pulley realignment: W=23–24, mid=12; registration RMS improved ~79% (6.7 px → 1.4 px mean)

**Imaging**
- AE stability gate: waits for AnalogueGain < 5% relative change × 5 consecutive reads before pinning exposure
- `settling_started` signal timing fixed: now emitted after AE pin + 0.20 s settle, not before — preview snapshot matches saved image exposure
- Non-blocking Read Focus button: `_FocusReader(QThread)` prevents GUI freeze when Live View is off

**Bug fixes**
- `IMAGES_ROOT` constant added to `experiment_setup.py` (was causing silent disk estimate failure)
- Experiment frequency default restored to 30 minutes
- `apply_main_illum_style` scope fix: `s = self._s` added inside method body
- `experiment_setup.py` line 235: orphaned `else` clause fixed (comment had been inserted between `if` body and `else`)
- `gui.py`: `setStyleSheet(dark_style(s))` moved to after `s` is computed (was causing `UnboundLocalError`)

**All v0.06 Display2 features carried forward**
- Dual 940 nm IR illumination (front + rear), per-mode camera presets
- Tabbed Camera Config dialog, File Manager with thumbnails, CSV metadata
- GT2 belt drive, autostart and desktop launcher

### v0.06 — Display2-specific release
Dual-stream camera, TIFF output, autofocus, File Manager with thumbnails, CSV metadata, Camera Config dialog, autostart and desktop launcher, GT2 belt drive initial implementation, per-mode IR presets.

---

## Registration Performance (System 1, v1.0.0)

Rear IR transmission, 8 cycles, plates 1 and 2:

| Metric | v0.06 baseline | v1.0.0 |
|---|---|---|
| Mean RMS | 6.7 px | 1.4 px |
| Mean \|dx\| | 6.5 px | 1.3 px |
| dx bias | +6.5 px (systematic) | −0.4 px (eliminated) |
| Cycles at 0 px shift | 0 of 4 | 9 of 14 (64%) |
| Max \|dx\| | 10 px | 6 px |

Residual jitter (2–6 px) is intrinsic GT2 belt backlash and stepper microstepping nonlinearity. Software registration using ArUco or QR fiducial markers on plate backs can correct remaining shift to sub-pixel if required for quantitative analysis.

---

## License

MIT — see `LICENSE` file.

## Installation
```bash
# Clone repository
cd ~
git clone git@github.com:sybednar/Seedling-imager-.git
cd Seedling-imager-/seedling_imager_controller

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install PySide6 opencv-python picamera2 gpiod