
# Seedling Imager Controller

## Overview
Inspired by the SPIRO (Smart Plate Imaging Robot; Ohlsson et al The Plant Journal doi: 10.1111/tpj.16587) project the **Seedling Imager** is a Raspberry Pi 5-based imaging system designed to monitor Arabidopsis seedling growth using a 6-position hexagonal carousel. It provides automated imaging, LED control, and experiment scheduling through a touch-friendly GUI.

---

## Features (v0.05)
- **GUI (PySide6)**:
  - Dark mode interface optimized for Raspberry Pi touchscreens.
  - **Live View** with illumination toggle (Green @ GPIO12, IR @ GPIO13).
  - **Experiment Setup**:
    - Select plates (1–6) in a compact two-row layout with visible checkbox outlines.
    - Choose illumination mode (Green or Infrared) with color-coded toggle (teal for Green, deep red for IR).
    - Configure experiment duration (days) and acquisition frequency (minutes).
  - **End Experiment** button for safe abort.
- **New in v0.05**:
  - **Experiment Runner**:
    - Automates time-lapse imaging cycles:
      - For each plate: illumination ON → 10 s settle → capture (if selected) → illumination OFF → advance.
      - Drift correction applied when wrapping to Plate #1 (reports extra steps, even if zero).
      - Wait begins immediately after Plate 6, then next cycle starts at Plate 1.
    - Signals for GUI:
      - `image_saved_signal(path)` updates preview with the **last captured image**.
      - `settling_started(plate_idx)` / `settling_finished(plate_idx)` enable **optional live preview during settle**.
  - **Preview Behavior**:
    - During experiments, the GUI shows the **last saved image** after each capture.
    - Optional live preview during the 10 s settle period for remote monitoring.
- **Camera Integration**:
  - Picamera2 for Raspberry Pi.
  - Real-time preview and still capture with correct color conversion.
- **Motor Control**:
  - TMC2209 stepper driver via GPIO.
  - Homing routine using hall sensor and optical sensor.
  - Drift correction logic ensures alignment at Plate #1.
- **Illumination Control**:
  - Dual LED channels:
    - Green (520 nm) on GPIO12.
    - Infrared (940 nm) on GPIO13 for dark-grown seedlings.
- **Image Storage**:
  - Images saved under:
    ```
    /home/sybednar/Seedling_Imager/images/experiment_<YYYYMMDD_HHMMSS>/plateN/
    ```
  - Filenames include plate number and timestamp.

---

## Hardware Setup
- Raspberry Pi 5
- TMC2209 stepper driver
- Hall sensor for homing
- Optical sensor (ITR20001) for drift correction
- LED panel with dual illumination (Green + IR)
- 12 MP Raspberry Pi Camera Module (NoIR for IR imaging)

### GPIO Pin Map
| Function        | GPIO Pin |
|-----------------|----------|
| STEP           | 20       |
| DIR            | 16       |
| EN             | 21       |
| Hall Sensor    | 26       |
| Optical Sensor | 19       |
| Green LED      | 12       |
| IR LED         | 13       |

---

## Software Requirements
- Python 3.11+
- PySide6
- Picamera2
- OpenCV
- gpiod

---

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