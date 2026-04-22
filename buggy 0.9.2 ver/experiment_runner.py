# experiment_runner.py — acquisition loop with robust full re-homing at cycle boundary
#
# Behavior:
#   • Plates 1..6 are imaged in order.
#   • After plate 6, we DO NOT call advance().
#   • We immediately run a full re-home via motor_control.rehome_full_from_hall(...),
#     which re-measures W (LOW->HIGH) and recenters at the same calibrated point
#     (dynamic bracket + CENTER_BACKOFF) you tuned in motor_control.py.
#   • We then emit Plate #1 and wait for the next cycle.
#
# Public surface (unchanged): signals, logging, CSV schema, LED callbacks, etc.

from PySide6.QtCore import QThread, Signal
from datetime import datetime, timedelta
from pathlib import Path
import time
import json
import csv
import os

import motor_control
import camera
from camera_config import load_settings

# -------- Re-home cadence (edit as you like) --------
REHOME_EVERY_N = 1   # 1 = every cycle; 10 = every 10 cycles; 0/None to disable

# -------- AE/AF settle controls --------
# Extra warm-up ONLY for the very first Plate #1 (cycle 1, plate 1)
FIRST_PLATE_WARMUP_S = 3.0   # set 0.0 to disable

# AE stability gate (run for every plate): wait until AnalogueGain stabilizes
AE_GATE_MAX_WAIT_S   = 3.0   # total timeout per plate
AE_GATE_POLL_S       = 0.10  # poll cadence
AE_GATE_GAIN_TOL     = 0.05  # <5% relative change considered “stable”
AE_GATE_STABLE_READS = 5     # need this many consecutive stable reads


class ExperimentRunner(QThread):
    # ---------- Signals ----------
    status_signal = Signal(str)
    image_saved_signal = Signal(str)
    plate_signal = Signal(int)
    settling_started = Signal(int)
    settling_finished = Signal(int)
    finished_signal = Signal()

    # ---------- Init ----------
    def __init__(
        self,
        selected_plates,
        duration_days,
        frequency_minutes,
        illumination_mode,
        led_control_fn,
        perform_homing: bool = True,
        parent=None
    ):
        super().__init__(parent)

        self.selected_plates = self._normalize_plates(selected_plates)
        self.duration_days = int(duration_days)
        self.frequency_minutes = int(frequency_minutes)
        self.illumination_mode = illumination_mode
        self.led_control_fn = led_control_fn
        self.perform_homing = perform_homing

        self._abort = False
        self.wait_seconds_for_camera = 10
        self.cycle_count = 0

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = Path("/home/sybednar/Seedling_Imager/images").expanduser()
        self.run_dir = root / f"experiment_{ts}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for p in range(1, 7):
            (self.run_dir / f"plate{p}").mkdir(exist_ok=True)

        self.cam_settings = load_settings()

        meta_path = self.run_dir / "metadata.json"
        meta = {
            "timestamp_start": datetime.now().isoformat(timespec="seconds"),
            "illumination_mode": self.illumination_mode,
            "selected_plates": self.selected_plates,
            "frequency_minutes": self.frequency_minutes,
            "duration_days": self.duration_days,
            "camera_settings": self.cam_settings,
            "rehome_every_n": int(REHOME_EVERY_N) if REHOME_EVERY_N else 0,
            "rehome_mode": "full",
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        self.csv_path = self.run_dir / "metadata.csv"
        self.csv_file = None
        self.csv_writer = None

    # ---------- Public controls ----------
    def abort(self):
        self._abort = True

    # ---------- Internals ----------
    def _normalize_plates(self, plate_names):
        idxs = []
        for name in plate_names:
            try:
                idxs.append(int(name.split()[-1]))
            except Exception:
                pass
        return [p for p in idxs if 1 <= p <= 6]

    def _log(self, msg):
        self.status_signal.emit(msg)

    def _sleep_with_abort(self, seconds):
        end = time.time() + seconds
        while time.time() < end and not self._abort:
            time.sleep(0.1)

    def _open_csv(self):
        try:
            self.csv_file = open(self.csv_path, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(
                [
                    "timestamp_iso",
                    "cycle_index",
                    "plate",
                    "illumination",
                    "image_path",
                    "width_px",
                    "height_px",
                    "file_size_bytes",
                    "AeEnable",
                    "ExposureTime_us",
                    "AnalogueGain",
                    "AwbEnable",
                    # settled exposure/gain that we pinned
                    "SettledExposureTime_us",
                    "SettledAnalogueGain",
                    # focus diagnostics (if available from libcamera build)
                    "LensPosition",
                    "AfState",
                    "FocusFoM",
                ]
            )
        except Exception as e:
            self._log(f"CSV open error: {e}")

    def _close_csv(self):
        try:
            if self.csv_file:
                self.csv_file.flush()
                self.csv_file.close()
        except Exception:
            pass

    # ---------- Optional autofocus helpers ----------
    def _wait_for_focus_fom(self, threshold: float = 500.0, timeout_s: float = 3.0, poll_s: float = 0.2):
        best_fom = None
        last_md = {}
        t0 = time.time()
        while (time.time() - t0) < timeout_s and not self._abort:
            md = camera.get_metadata() or {}
            last_md = md
            fom = last_md.get("FocusFoM", None)
            if fom is None:
                return (best_fom, last_md)
            try:
                fom_val = float(fom)
            except Exception:
                fom_val = None
            if fom_val is not None:
                if (best_fom is None) or (fom_val > best_fom):
                    best_fom = fom_val
                if fom_val >= threshold:
                    return (best_fom, last_md)
            time.sleep(poll_s)
        return (best_fom, last_md)

    def _autofocus_with_retry(self, threshold: float = 500.0, timeout_s: float = 3.0, poll_s: float = 0.2):
        best_fom = None
        best_md = {}
        attempts = 0

        def _poll_for_focus():
            nonlocal best_fom, best_md
            t0 = time.time()
            last_md = {}
            while (time.time() - t0) < timeout_s and not self._abort:
                md = camera.get_metadata() or {}
                last_md = md
                fom = md.get("FocusFoM", None)
                if fom is None:
                    if not best_md:
                        best_md = md
                    return (best_fom, best_md, False)
                try:
                    fom_val = float(fom)
                except Exception:
                    fom_val = None
                if fom_val is not None:
                    if (best_fom is None) or (fom_val > best_fom):
                        best_fom = fom_val
                        best_md = md
                    if fom_val >= threshold:
                        return (best_fom, best_md, True)
                time.sleep(poll_s)
            if not best_md and last_md:
                best_md = last_md
            return (best_fom, best_md, False)

        try:
            camera.set_af_mode(1)  # single
        except Exception as e:
            self._log(f"AF mode set warning (ignored): {e}")

        attempts = 1
        try:
            camera.trigger_autofocus()
        except Exception as e:
            self._log(f"AF trigger warning (ignored): {e}")
        best_fom, best_md, ok = _poll_for_focus()
        if ok or self._abort:
            return (best_fom, best_md, attempts)

        attempts = 2
        self._log(f"Plate focus retry: FocusFoM<{threshold} after {timeout_s:.1f}s; retrying autofocus once...")
        try:
            camera.trigger_autofocus()
        except Exception as e:
            self._log(f"AF retry trigger warning (ignored): {e}")
        best_fom, best_md, ok2 = _poll_for_focus()
        return (best_fom, best_md, attempts)

    def _ae_stability_gate(self, max_wait_s=AE_GATE_MAX_WAIT_S, poll_s=AE_GATE_POLL_S,
                           gain_tol=AE_GATE_GAIN_TOL, min_stable_reads=AE_GATE_STABLE_READS):
        """
        Wait until AnalogueGain stabilizes before we pin AE:
          • A sequence of 'min_stable_reads' successive polls where the relative change
            in AnalogueGain is < gain_tol.
          • Breaks early if aborted; times out after max_wait_s.

        Returns: (stable: bool, last_md: dict)
        """
        stable_reads = 0
        last_gain = None
        t0 = time.time()
        last_md = {}
        while (time.time() - t0) < max_wait_s and not self._abort:
            md = camera.get_metadata() or {}
            last_md = md
            g = md.get("AnalogueGain", None)
            if g is None:
                time.sleep(poll_s)
                continue
            g = float(g)
            if last_gain is not None and last_gain > 0:
                rel = abs(g - last_gain) / last_gain
                if rel < gain_tol:
                    stable_reads += 1
                    if stable_reads >= min_stable_reads:
                        return True, last_md
                else:
                    stable_reads = 0
            last_gain = g
            time.sleep(poll_s)
        return False, last_md

    # ---------- Always-on full re-home at cycle boundary ----------
    def _rehome_at_cycle_boundary(self):
        """
        Called once per full cycle (after plate 6, before wait) if enabled.
        Uses motor_control.rehome_full_from_hall(...) to re-measure W and
        re-center at the same calibrated Plate #1 point (dynamic bracket + backoff).
        """
        if not REHOME_EVERY_N or (self.cycle_count % int(REHOME_EVERY_N) != 0):
            return

        try:
            motor_control.driver_enable()
        except Exception:
            pass

        try:
            self._log("Re-home (full) at cycle boundary: seeking Hall...")
            ok = False
            if hasattr(motor_control, "rehome_full_from_hall"):
                ok = motor_control.rehome_full_from_hall(status_callback=self.status_signal.emit)
            else:
                # Fallback to full home() if helper not present
                plate = motor_control.home(status_callback=self.status_signal.emit)
                ok = (plate is not None)

            if ok:
                # Guard: ensure we're at Plate #1 logically and visually
                curr = motor_control.get_current_plate()
                if curr != 1:
                    motor_control.goto_plate(1, status_callback=self.status_signal.emit)
                self.plate_signal.emit(1)
                self._log("Re-home at cycle boundary: OK. Plate #1 aligned.")
            else:
                self._log("Re-home at cycle boundary: FAILED; continuing with last centered position.")

        except Exception as e:
            self._log(f"Re-home at cycle boundary error: {e}")

    # ---------- Thread run ----------
    def run(self):
        if not self.selected_plates:
            self._log("No plates selected; experiment aborted.")
            self.finished_signal.emit()
            return

        # Ensure driver enabled prior to any motion
        motor_control.driver_enable()

        # Initial homing (unless GUI already did homing-with-preview)
        if self.perform_homing:
            plate = motor_control.home(status_callback=self.status_signal.emit)
            if plate is None:
                self._log("Homing failed; experiment aborted.")
                self.finished_signal.emit()
                return

        # Start camera & apply settings for the acquisition phase
        try:
            camera.start_camera()
            active_settings = dict(self.cam_settings)
            if self.illumination_mode == "Infrared":
                active_settings = camera.apply_ir_quant_preset(active_settings)
            camera.apply_settings(active_settings)
        except Exception as e:
            self._log(f"Camera start error: {e}")
            self.finished_signal.emit()
            return

        # --- Global pre-warm once per run (especially important for IR) ---
        try:
            # Turn on the appropriate LED for warm-up so AE converges with actual illumination
            if self.illumination_mode == "Infrared":
                if self.led_control_fn:
                    self.led_control_fn(True, self.illumination_mode)
            # Ensure AE is on during pre-warm
            camera.set_auto_exposure(True)
            self._log("Global pre-warm: letting AE settle for 2.5s before the first cycle...")
            self._sleep_with_abort(2.5)  # adjust 2.0–3.0s if needed
        finally:
            # Turn LED back off before entering the cycle loop; per-plate logic will manage LEDs
            if self.led_control_fn:
                self.led_control_fn(False, self.illumination_mode)

        self._open_csv()
        self._log(
            f"Experiment started: {self.duration_days} day(s), "
            f"every {self.frequency_minutes} min. Illumination: {self.illumination_mode}. "
            f"Re-home: full, every {int(REHOME_EVERY_N) if REHOME_EVERY_N else 0} cycle(s)."
        )

        end_time = datetime.now() + timedelta(days=self.duration_days)

        try:
            while datetime.now() < end_time and not self._abort:
                self.cycle_count += 1

                # Always start a cycle by ensuring we are at Plate #1
                motor_control.goto_plate(1, status_callback=self.status_signal.emit)
                self.plate_signal.emit(1)

                for plate_idx in range(1, 7):
                    if self._abort:
                        break

                    # LED ON for settle/exposure
                    if self.led_control_fn:
                        self.led_control_fn(True, self.illumination_mode)

                    # AE settle
                    camera.set_auto_exposure(True)

                    # Autofocus once per plate (optional; uses metadata FoM if available)
                    try:
                        camera.set_af_mode(1)  # single
                        camera.trigger_autofocus()
                    except Exception as e:
                        self._log(f"AF trigger warning (ignored): {e}")

                    self.settling_started.emit(plate_idx)
                    self._log(f"Plate #{plate_idx}: waiting {self.wait_seconds_for_camera}s...")
                    self._sleep_with_abort(self.wait_seconds_for_camera)
                    self.settling_finished.emit(plate_idx)

                    if self._abort:
                        break

                    # AF + FoM retry; then lock focus
                    best_fom, md_focus, attempts = self._autofocus_with_retry(
                        threshold=500.0, timeout_s=3.0, poll_s=0.2
                    )
                    if best_fom is None:
                        self._log(f"Plate #{plate_idx}: FocusFoM unavailable; locking focus anyway.")
                    else:
                        self._log(
                            f"Plate #{plate_idx}: FocusFoM best={best_fom:.0f} "
                            f"(threshold=500, attempts={attempts}), locking focus."
                        )
                    try:
                        camera.set_af_mode(0)  # lock focus
                    except Exception as e:
                        self._log(f"AF lock warning (ignored): {e}")

                    # --- (A) One-time warm-up ONLY for the first Plate #1 of the run ---
                    if self.cycle_count == 1 and plate_idx == 1 and FIRST_PLATE_WARMUP_S > 0:
                        self._log(f"First Plate #1 warm-up: extra {FIRST_PLATE_WARMUP_S:.1f}s AE settle")
                        self._sleep_with_abort(FIRST_PLATE_WARMUP_S)

                    # --- (B) AE stability gate for every plate before we pin AE ---
                    stable, md_stable = self._ae_stability_gate(
                        max_wait_s=AE_GATE_MAX_WAIT_S,
                        poll_s=AE_GATE_POLL_S,
                        gain_tol=AE_GATE_GAIN_TOL,
                        min_stable_reads=AE_GATE_STABLE_READS
                    )
                    if stable:
                        self._log("AE stability: AnalogueGain stabilized; pinning exposure/gain.")
                    else:
                        self._log("AE stability: not fully stable at timeout; pinning latest values.")

                    # Choose the best metadata available at this point
                    md_pin = md_stable if md_stable else (md_focus if md_focus else camera.get_metadata())

                    # Extract values for CSV logging (keep variable names used later)
                    settled_exp  = md_pin.get("ExposureTime", None)
                    settled_gain = md_pin.get("AnalogueGain", None)
                    lens_pos     = md_pin.get("LensPosition", None)
                    af_state     = md_pin.get("AfState", None)
                    focus_fom    = md_pin.get("FocusFoM", None)

                    # --- Pin AE and set manual controls ---
                    camera.set_auto_exposure(False)
                    if settled_exp is not None and settled_gain is not None:
                        camera.set_manual_exposure_gain(settled_exp, settled_gain)
                    else:
                        # Fallback if metadata missing (rare): leave AE on for this frame
                        self._log("AE pin: missing ExposureTime/AnalogueGain; leaving AE enabled for this capture.")


                    # Give controls one frame to take effect on the still stream (Picamera2 is async)
                    self._sleep_with_abort(0.20)  # 200 ms is usually enough; 100–250 ms fine


                    # Capture (if selected)
                    if plate_idx in self.selected_plates:
                        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        if self.illumination_mode == "Infrared":
                            img_name = f"plate{plate_idx}_{ts_str}_gray.tif"
                            grayscale = True
                        else:
                            img_name = f"plate{plate_idx}_{ts_str}.tif"
                            grayscale = False
                        img_path = str(self.run_dir / f"plate{plate_idx}" / img_name)

                        saved = camera.save_image(img_path, grayscale=grayscale)
                        if saved:
                            width = height = None
                            shape = camera.get_last_saved_shape()
                            if shape:
                                height, width = shape
                            try:
                                file_size = Path(img_path).stat().st_size
                            except Exception:
                                file_size = None

                            md = camera.get_metadata()
                            AeEnable = md.get("AeEnable", None)
                            ExposureTime = md.get("ExposureTime", None)
                            AnalogueGain = md.get("AnalogueGain", None)
                            AwbEnable = md.get("AwbEnable", None)

                            if self.csv_writer:
                                self.csv_writer.writerow(
                                    [
                                        datetime.now().isoformat(timespec="seconds"),
                                        self.cycle_count,
                                        plate_idx,
                                        self.illumination_mode,
                                        img_path,
                                        width,
                                        height,
                                        file_size,
                                        AeEnable,
                                        ExposureTime,
                                        AnalogueGain,
                                        AwbEnable,
                                        settled_exp,
                                        settled_gain,
                                        lens_pos,
                                        af_state,
                                        focus_fom,
                                    ]
                                )
                            self.image_saved_signal.emit(img_path)
                            self._log(f"Saved: {img_path}")
                        else:
                            self._log(f"Capture failed on plate {plate_idx}")
                    else:
                        self._log(f"Plate #{plate_idx}: skipped.")

                    # LED OFF, prep for next plate
                    if self.led_control_fn:
                        self.led_control_fn(False, self.illumination_mode)
                    camera.set_auto_exposure(True)

                    # Step to next plate — BUT NOT after plate 6
                    if plate_idx < 6:
                        motor_control.advance(status_callback=self.status_signal.emit)
                        self.plate_signal.emit(plate_idx + 1)

                # ---- End of a full 1..6 cycle ----
                if not self._abort:
                    # Full re-home at cycle boundary (no advance occurred after plate 6)
                    if REHOME_EVERY_N and (self.cycle_count % int(REHOME_EVERY_N) == 0):
                        self._rehome_at_cycle_boundary()
                    else:
                        # Even if re-home skipped, ensure we present Plate #1 for the next cycle
                        motor_control.goto_plate(1, status_callback=self.status_signal.emit)
                        self.plate_signal.emit(1)

                    self._log(f"Cycle complete. Waiting {self.frequency_minutes} min...")
                    self._sleep_with_abort(self.frequency_minutes * 60)

        finally:
            self._log("Experiment finished." if not self._abort else "Experiment aborted.")
            try:
                camera.apply_settings(self.cam_settings)  # restore baseline
            except Exception:
                pass
            try:
                camera.stop_camera()
            except Exception:
                pass
            if self.led_control_fn:
                self.led_control_fn(False, self.illumination_mode)
            self._close_csv()
            self.finished_signal.emit()