#gui.py version 0.9.2 mod 022226
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QDialog, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QGuiApplication, QImage, QPainter, QColor
from styles import dark_style
from experiment_setup import ExperimentSetupDialog, ILLUM_GREEN, ILLUM_IR
from experiment_runner import ExperimentRunner
from camera_config import CameraConfigDialog
from file_manager import FileManagerDialog
import motor_control
import camera

from ui_config import (
    UIConfig,
    compute_scale_for_profile
)


# --- Constants for LED colors/styles ---
SEA_FOAM_GREEN = "#26A69A"  # Green mode button color
DEEP_RED = "#B71C1C"        # Infrared mode button color

# LED GPIO setup (best-effort)
try:
    import gpiod
    from gpiod.line import Value, Direction
    LED_GREEN_PIN = 12
    LED_IR_PIN = 13
    chip = "/dev/gpiochip0"
    led_request = gpiod.request_lines(
        chip,
        consumer="seedling_leds",
        config={
            LED_GREEN_PIN: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
            LED_IR_PIN: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
        }
    )
except Exception as e:
    print(f"LED init failed: {e}", flush=True)
    led_request = None


class SeedlingImagerGUI(QWidget):
    def __init__(self, ui_config=None, screen_rect=None):
        super().__init__()
        self.setWindowTitle("Time_Lapse Seedling Imager")
        self.setStyleSheet(dark_style)

        # Cache the ui_config (may be None on very first run)
        self.ui_config = ui_config

        # Use provided screen_rect if passed from main.py; otherwise query primary screen
        if screen_rect is None:
            screen = QGuiApplication.primaryScreen()
            geom = screen.availableGeometry() if screen else None
        else:
            geom = screen_rect

        if geom:
            self.setGeometry(geom)  # let layouts fill the screen
            # compute_scale_for_profile uses min(width/800, height/480), clamped to >=1
            self.s = compute_scale_for_profile(geom, getattr(self.ui_config, "display_profile", "auto"))
        else:
            # Safe fallback for Touch Display 2 landscape
            self.resize(1280, 720)
            self.s = 1.6

        # Button sizing derived from scale
        button_width  = int(250 * self.s)
        base_btn_h    = 30
        height_scale  = 1.25
        button_height = int(base_btn_h * height_scale * self.s)
      
        self.threads = []
        self.experiment_thread = None
        self.homing_worker = None  # <-- abortable homing worker
        self.active_illum_mode = ILLUM_GREEN

        main_layout = QHBoxLayout()

        # Left: buttons (EXACT-FILL balanced column)
        button_layout = QVBoxLayout()
        button_layout.setSpacing(0)
        button_layout.setContentsMargins(0, 0, 0, 0)
        # NOTE: do NOT set AlignTop when using stretches for exact fill.


        def style_and_size(btn, *, full_width=True):
            """Apply consistent sizing for touchscreen use."""
            if full_width:
                btn.setFixedWidth(button_width)
            btn.setFixedHeight(button_height)
            return btn

        # --- Buttons (same as before, but now height-controlled) ---

        # Live View toggle button (text reflects current state)
        self.live_view_btn = QPushButton("Turn Live View On")
        #self.live_view_btn.setFixedWidth(button_width)
        style_and_size(self.live_view_btn)
        self.live_view_btn.setStyleSheet(
            dark_style + " QPushButton { background-color: #FFD600; color: black; font-weight: bold; }"
        )
        self.live_view_btn.clicked.connect(self.toggle_live_view)
        #button_layout.addWidget(self.live_view_btn)


        self.illum_toggle_btn = QPushButton(f"Illum: {self.active_illum_mode}")
        style_and_size(self.illum_toggle_btn)
        self.apply_main_illum_style()
        self.illum_toggle_btn.clicked.connect(self.toggle_illumination_mode)

        # Home + Advance row (layout preserved)
        ha_layout = QHBoxLayout()
        ha_layout.setSpacing(max(6, int(10 * self.s)))
        ha_layout.setContentsMargins(0, 0, 0, 0)

        self.home_btn = QPushButton("Home")
        self.home_btn.setObjectName("homeBtn")
        self.home_btn.setFixedWidth(button_width // 2 - 5)
        self.home_btn.setFixedHeight(button_height)
        self.home_btn.clicked.connect(self.on_home_clicked)

        self.advance_btn = QPushButton("Advance")
        self.advance_btn.setFixedWidth(button_width // 2 - 5)
        self.advance_btn.setFixedHeight(button_height)
        self.advance_btn.clicked.connect(lambda: self.run_motor_action("advance"))

        ha_layout.addWidget(self.home_btn)
        ha_layout.addWidget(self.advance_btn)

        self.experiment_btn = QPushButton("Experiment Setup")
        style_and_size(self.experiment_btn)
        self.experiment_btn.setStyleSheet(dark_style + " QPushButton { background-color: #8E24AA; color: white; }")
        self.experiment_btn.clicked.connect(self.open_experiment_setup)

        self.end_experiment_btn = QPushButton("End Experiment")
        style_and_size(self.end_experiment_btn)
        self.end_experiment_btn.setStyleSheet(dark_style + " QPushButton { background-color: #E53935; color: white; }")
        self.end_experiment_btn.clicked.connect(self.end_experiment)

        self.camera_config_btn = QPushButton("Camera Config")
        style_and_size(self.camera_config_btn)
        self.camera_config_btn.setStyleSheet(dark_style + " QPushButton { background-color: #546E7A; color: white; }")
        self.camera_config_btn.clicked.connect(self.open_camera_config)

        self.file_manager_btn = QPushButton("File Manager")
        style_and_size(self.file_manager_btn)
        self.file_manager_btn.setStyleSheet(dark_style + " QPushButton { background-color: #455A64; color: white; }")
        self.file_manager_btn.clicked.connect(self.open_file_manager)

        # Fullscreen toggle button (touch-friendly)
        # (Assumes you already added toggle_fullscreen() + update_fullscreen_button_text() methods)
        self.fullscreen_btn = QPushButton("")
        style_and_size(self.fullscreen_btn)
        self.fullscreen_btn.setStyleSheet(
            dark_style + " QPushButton { background-color: #607D8B; color: white; font-weight: bold; }"
        )
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

        # If you ALSO added an "Exit to Desktop" button previously, include it here:
        # self.exit_btn = QPushButton("Exit to Desktop")
        # style_and_size(self.exit_btn)
        # self.exit_btn.setStyleSheet(dark_style + " QPushButton { background-color: #D32F2F; color: white; font-weight: bold; }")
        # self.exit_btn.clicked.connect(self.exit_to_desktop)

        # --- Add groups + stretches (THIS achieves EXACT FILL) ---

        # Optional top stretch to center the whole stack vertically:
        button_layout.addStretch(2)

        # Group 1: View / Illumination
        button_layout.addWidget(self.live_view_btn)
        button_layout.addSpacing(int(6 * self.s))
        button_layout.addWidget(self.illum_toggle_btn)

        button_layout.addStretch(1)

        # Group 2: Motion
        button_layout.addLayout(ha_layout)

        button_layout.addStretch(1)

        # Group 3: Experiment
        button_layout.addWidget(self.experiment_btn)
        button_layout.addSpacing(int(6 * self.s))
        button_layout.addWidget(self.end_experiment_btn)

        button_layout.addStretch(1)

        # Group 4: Management
        button_layout.addWidget(self.camera_config_btn)
        button_layout.addSpacing(int(6 * self.s))
        button_layout.addWidget(self.file_manager_btn)
        button_layout.addSpacing(int(6 * self.s))
        button_layout.addWidget(self.fullscreen_btn)

        # If Exit button exists:
        # button_layout.addSpacing(int(6 * self.s))
        # button_layout.addWidget(self.exit_btn)

        # Optional bottom stretch to balance the top stretch:
        button_layout.addStretch(1)

        # Add the left column to the main layout (keep your stretch setup)
        main_layout.addLayout(button_layout, stretch=0)

        # Ensure the fullscreen button text matches current state
        self.update_fullscreen_button_text()

        # Right: status + camera + log
        right_layout = QVBoxLayout()     
        # Keep the right column tight to reduce drift as the log grows
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("Status: Ready"); self.status_label.setAlignment(Qt.AlignCenter)
        #right_layout.addWidget(self.status_label)

        self.camera_label = QLabel("Camera Preview")
        self.camera_label.setAlignment(Qt.AlignCenter)
        
        # Ensure a min that fits GEN1 (800×480) but grows with scale on GEN2 raspberry pi touchscreen
        self.camera_label.setMinimumSize(int(480 * self.s/1.5), int(270 * self.s/1.5))
        self.camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # --- show the true QLabel bounds (1‑px white frame) ---
        from PySide6.QtWidgets import QFrame
        self.camera_label.setFrameShape(QFrame.Box)
        self.camera_label.setLineWidth(1)
        self.camera_label.setStyleSheet(self.camera_label.styleSheet() + "; border: 1px solid white;")
        # ------------------------------------------------------


        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)

        # Keep right-side stack but give preview more space than log
        right_layout.addWidget(self.status_label, stretch=0)
        right_layout.addWidget(self.camera_label, stretch=3)
        right_layout.addWidget(self.log_panel, stretch=2)

        main_layout.addLayout(right_layout, stretch=1)
        self.setLayout(main_layout)

        self.timer = QTimer(); self.timer.timeout.connect(self.update_camera_frame)
        self.live_view_active = False

        self.update_controls_for_experiment(False)

        # Apply persisted camera settings at startup
        camera.apply_settings()      
        
        # Ensure the Live View button text/style matches the current state at startup
        self._update_live_view_button()
        QTimer.singleShot(200, lambda: self.set_live_view(True))


    # ---------- Illumination ----------
    def apply_main_illum_style(self):
        color = "#26A69A" if self.active_illum_mode == ILLUM_GREEN else "#B71C1C"
        self.illum_toggle_btn.setStyleSheet(
            dark_style + f" QPushButton {{ background-color: {color}; color: white; font-weight: bold; }}"
        )

    def toggle_illumination_mode(self):
        """Switch between Green and Infrared illumination; update button style."""
        self.active_illum_mode = ILLUM_IR if self.active_illum_mode == ILLUM_GREEN else ILLUM_GREEN
        self.illum_toggle_btn.setText(f"Illum: {self.active_illum_mode}")
        self.apply_main_illum_style()
        # If live view is active, apply the new illumination immediately
        if self.live_view_active and led_request:
            from gpiod.line import Value  # import only when needed
            if self.active_illum_mode == ILLUM_GREEN:
                led_request.set_value(LED_GREEN_PIN, Value.ACTIVE)
                led_request.set_value(LED_IR_PIN, Value.INACTIVE)
            else:
                led_request.set_value(LED_GREEN_PIN, Value.INACTIVE)
                led_request.set_value(LED_IR_PIN, Value.ACTIVE)
            
            self.apply_liveview_camera_profile()   
                
        self.update_status(f"Illumination set to {self.active_illum_mode}")

# --- Live-view boost for IR preview (enable for IR, disable for Green) ---
        try:
            if self.active_illum_mode == ILLUM_IR:
                camera.enable_liveview_boost_for_ir(target_gain=8.0, target_exposure_us=20000)
            else:
                camera.disable_liveview_boost()
        except Exception as e:
            print(f"[gui] liveview boost toggle error: {e}", flush=True)

    def apply_liveview_camera_profile(self):
        """
        Apply a temporary camera profile for Live View depending on illumination mode.
        - Infrared: IR Quant preset (grayscale-like, AWB off, conservative sharpness/contrast)
        - Green: baseline persisted settings
        """
        base = camera.get_current_settings()
        if self.active_illum_mode == ILLUM_IR:
            base = camera.apply_ir_quant_preset(base)
        camera.apply_settings(base)

    def _set_centered_pixmap(self, qimage: QImage) -> None:
        """
        Use QLabel's native centering to render qimage:
        - scale to fit while preserving aspect (NO crop)
        - rely on self.camera_label.setAlignment(Qt.AlignCenter) for centering
        """
        if qimage.isNull():
            return

        pix = QPixmap.fromImage(qimage)
        target_size = self.camera_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        scaled = pix.scaled(
            target_size,
            Qt.KeepAspectRatio,         # letterbox (no crop)
            Qt.SmoothTransformation
        )

        # Hand the scaled pixmap to QLabel; alignment is handled by Qt
        self.camera_label.setPixmap(scaled)

        # Diagnostics: log current label geometry & final pixmap size
        try:
            g = self.camera_label.geometry()
            self.log_panel.append(
                f"[label-geom] x={g.x()} y={g.y()} w={g.width()} h={g.height()} | "
                f"pixmap={scaled.width()}x{scaled.height()}"
            )
        except Exception:
            pass


    # ---------- Home/Stop logic (manual use via Home button) ----------
    def on_home_clicked(self):
        """Toggle behavior: start homing or request stop."""
        if self.homing_worker is None or not self.homing_worker.isRunning():
            self.start_homing()
        else:
            self.stop_homing()

    def start_homing(self):
        # Ensure driver is enabled before motion (EN low = enabled per wiring)
        motor_control.driver_enable()  # enable driver  [1](https://uwprod-my.sharepoint.com/personal/sybednar_wisc_edu/Documents/Microsoft%20Copilot%20Chat%20Files/git_update.sh.txt)

        # Update UI to STOP state (direct, per-widget style to override app-wide blue)
        self.home_btn.setText("STOP")
        self.home_btn.setStyleSheet("background-color: #E53935; color: white; font-weight: bold;")
        # Disable potentially conflicting controls during homing (keep Home enabled for STOP)
        self.advance_btn.setEnabled(False)
        self.experiment_btn.setEnabled(False)
        self.illum_toggle_btn.setEnabled(False)
        self.camera_config_btn.setEnabled(False)

        # Launch worker
        self.homing_worker = HomingWorker()
        self.homing_worker.status_signal.connect(self.update_status)
        self.homing_worker.finished_with_result.connect(self.on_homing_finished)
        self.homing_worker.start()
        self.update_status("Homing started...")

    def stop_homing(self):
        # Immediate hardware e-stop: cut coil current now (EN high = disabled)
        motor_control.driver_disable()  # disable driver  [1](https://uwprod-my.sharepoint.com/personal/sybednar_wisc_edu/Documents/Microsoft%20Copilot%20Chat%20Files/git_update.sh.txt)
        if self.homing_worker and self.homing_worker.isRunning():
            self.homing_worker.request_stop()
            self.update_status("Emergency stop requested... (driver disabled)")

    def on_homing_finished(self, plate_or_none):
        # Restore UI to normal state
        self.home_btn.setText("Home")
        self.home_btn.setStyleSheet("")  # clear per-widget override; fallback to app-wide blue
        self.advance_btn.setEnabled(True)
        self.experiment_btn.setEnabled(True)
        self.illum_toggle_btn.setEnabled(True)
        self.camera_config_btn.setEnabled(True)

        self.homing_worker = None

        if plate_or_none is None:
            # Leave driver disabled after emergency stop for safety.
            self.update_status("Homing aborted or failed. Driver remains DISABLED.")
        else:
            # Keep driver enabled after normal completion (holding torque).
            self.update_status("Homing finished. Driver remains ENABLED.")

    # ---------- Homing-with-preview right before starting an experiment ----------
    def open_experiment_setup(self):
        if self.live_view_active:
            self.toggle_live_view()
        dialog = ExperimentSetupDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # Run homing with preview first, then launch the runner
            self.start_experiment_with_homing_preview(
                plates=dialog.selected_plates,
                days=dialog.duration_days,
                freq=dialog.frequency_minutes,
                illum=dialog.selected_illum
            )

    def start_experiment_with_homing_preview(self, plates, days, freq, illum):
        """
        1) Turn on Live View so the user SEES homing.
        2) Perform homing via HomingWorker (STOP/E-stop available through Home button).
        3) On success: stop Live View and start ExperimentRunner(skip homing).
        """
        # Remember chosen illumination and show it in preview
        self.active_illum_mode = illum
        self.apply_main_illum_style()

        # Turn on Live View (sets LEDs for the chosen mode)
        if not self.live_view_active:
            self.toggle_live_view()
        self.update_status("Starting homing (with preview)... Press STOP to abort if needed.")

        # Ensure driver enabled, set Home button to STOP style, and disable other controls
        motor_control.driver_enable()  # enable driver  [1](https://uwprod-my.sharepoint.com/personal/sybednar_wisc_edu/Documents/Microsoft%20Copilot%20Chat%20Files/git_update.sh.txt)
        self.home_btn.setText("STOP")
        self.home_btn.setStyleSheet("background-color: #E53935; color: white; font-weight: bold;")
        self.advance_btn.setEnabled(False)
        self.experiment_btn.setEnabled(False)
        self.illum_toggle_btn.setEnabled(False)
        self.camera_config_btn.setEnabled(False)

        # Launch a dedicated homing worker
        self.homing_worker = HomingWorker()
        self.homing_worker.status_signal.connect(self.update_status)
        # When homing completes, continue to experiment or abort
        self.homing_worker.finished_with_result.connect(
            lambda plate_or_none: self._on_preview_homing_done(
                plate_or_none, plates, days, freq, illum
            )
        )
        self.homing_worker.start()

    def _on_preview_homing_done(self, plate_or_none, plates, days, freq, illum):
        # Restore Home button and re-enable the controls disabled for the preview-homing step
        self.home_btn.setText("Home")
        self.home_btn.setStyleSheet("")
        self.advance_btn.setEnabled(True)
        self.experiment_btn.setEnabled(True)
        self.illum_toggle_btn.setEnabled(True)
        self.camera_config_btn.setEnabled(True)

        self.homing_worker = None

        if plate_or_none is None:
            # Homing aborted/failed — stop preview and keep driver disabled (safety).
            if self.live_view_active:
                self.toggle_live_view()
            self.update_status("Experiment start aborted: homing failed or was stopped. Driver remains DISABLED.")
            return

        # Homing succeeded: stop preview before starting the experiment run
        if self.live_view_active:
            self.toggle_live_view()

        # Start the standard experiment loop, but SKIP homing (we just did it with preview)
        self.start_experiment(plates, days, freq, illum, skip_initial_homing=True)

    # ---------- Experiment orchestration ----------
    def start_experiment(self, plates, days, freq, illum, skip_initial_homing=False):
        if self.experiment_thread and self.experiment_thread.isRunning():
            self.update_status("Experiment already running."); return
        # Ensure Live View is off during the experiment
        if self.live_view_active:
            self.toggle_live_view()

        # Create the runner, passing perform_homing flag inverse of skip_initial_homing
        self.experiment_thread = ExperimentRunner(
            plates, days, freq, illum,
            self.set_led,
            perform_homing=(not skip_initial_homing)
        )
        self.experiment_thread.status_signal.connect(self.update_status)
        self.experiment_thread.image_saved_signal.connect(lambda p: self.log_panel.append(f"Image saved: {p}"))
        self.experiment_thread.plate_signal.connect(lambda idx: self.status_label.setText(f"Plate #{idx}"))
        self.experiment_thread.settling_started.connect(self.show_experiment_snapshot)
        self.experiment_thread.finished_signal.connect(self.on_experiment_finished)
        self.update_controls_for_experiment(True)
        self.experiment_thread.start()

    def end_experiment(self):
        # Stop any GUI preview timer to avoid capture/stop races
        try:
            self.timer.stop()
        except Exception:
            pass

        if self.experiment_thread and self.experiment_thread.isRunning():
            self.experiment_thread.abort()
            self.experiment_thread.wait(5000)  # wait up to 5 s
            self.update_status("Experiment ended by user.")
        else:
            self.update_status("No experiment running.")

        # Be explicit about camera state here
        try:
            camera.disable_liveview_boost()
        except Exception:
            pass
        try:
            camera.stop_camera()
        except Exception:
            pass

        self.update_controls_for_experiment(False)

    def on_experiment_finished(self):
        self.update_controls_for_experiment(False)
        self.update_status("Experiment finished.")

    def update_controls_for_experiment(self, running: bool):
        """Enable/disable controls while an experiment is running."""
        # Live View and motion/Config controls should be disabled during a run
        self.live_view_btn.setEnabled(not running)
        self.home_btn.setEnabled(not running)
        self.advance_btn.setEnabled(not running)
        self.experiment_btn.setEnabled(not running)
        self.illum_toggle_btn.setEnabled(not running)
        self.camera_config_btn.setEnabled(not running)
        # Only the "End Experiment" button is enabled during a run
        self.end_experiment_btn.setEnabled(running)

        # Lock/unlock preview width to prevent horizontal drift
        if running:
            self._lock_preview_width()
        else:
            self._unlock_preview_width()


    # ---------- Camera / LEDs / File manager ----------
    def update_status(self, text):
        self.status_label.setText(text)
        self.log_panel.append(text)


    def apply_liveview_camera_profile(self):
            """
            Apply a temporary camera profile for Live View based on illumination mode.

            - If illumination is Infrared: apply IR quant preset (Saturation=0, AWB off, etc.)
            - If illumination is Green: apply baseline persisted settings

            This does NOT modify camera_settings.json; it only sets active controls.
            """
            try:
                base = camera.get_current_settings()  # persisted settings from JSON
                if self.active_illum_mode == ILLUM_IR:
                    base = camera.apply_ir_quant_preset(base)  # temporary overlay
                camera.apply_settings(base)
            except Exception as e:
                print(f"apply_liveview_camera_profile error: {e}", flush=True)

    def _lock_preview_width(self):
        """Lock the preview label width during a run to prevent horizontal drift."""
        try:
            if getattr(self, "_preview_locked", False):
                return
            w = self.camera_label.width()
            if w > 0:
                self._preview_locked = True
                self._preview_lock_w = w
                self.camera_label.setMinimumWidth(w)
                self.camera_label.setMaximumWidth(w)
        except Exception:
            pass

    def _unlock_preview_width(self):
        """Release the preview label width lock after the run finishes."""
        try:
            if not getattr(self, "_preview_locked", False):
                return
            self._preview_locked = False
            self._preview_lock_w = None
            # Reset to defaults
            self.camera_label.setMinimumWidth(0)
            self.camera_label.setMaximumWidth(16777215)  # Qt default max
        except Exception:
            pass

    def run_motor_action(self, action: str):
        """
        Start a motor action (currently only 'advance') in a background thread.
        Keeps a reference to the thread so it isn't garbage-collected.
        """
        # Don't allow advance during homing or experiment runs
        if self.experiment_thread and self.experiment_thread.isRunning():
            self.update_status("Motor action blocked: experiment is running.")
            return
        if self.homing_worker and self.homing_worker.isRunning():
            self.update_status("Motor action blocked: homing is running.")
            return

        # Disable the advance button while the action runs to prevent double-clicks
        if action == "advance":
            self.advance_btn.setEnabled(False)

        worker = MotorWorker(action)
        worker.status_signal.connect(self.update_status)

        # Re-enable controls when done and drop the reference
        def _cleanup():
            if action == "advance":
                self.advance_btn.setEnabled(True)
            try:
                self.threads.remove(worker)
            except ValueError:
                pass

        worker.finished.connect(_cleanup)

        # Keep reference alive
        self.threads.append(worker)
        worker.start()


    def _update_live_view_button(self):
        """Update Live View button text + style to reflect current state."""
        if self.live_view_active:
            self.live_view_btn.setText("Turn Live View Off")
            self.live_view_btn.setStyleSheet(
                dark_style + " QPushButton { background-color: #43A047; color: white; font-weight: bold; }"
            )
        else:
            self.live_view_btn.setText("Turn Live View On")
            self.live_view_btn.setStyleSheet(
                dark_style + " QPushButton { background-color: #FFD600; color: black; font-weight: bold; }"
            )

    def set_live_view(self, enable: bool):
        """
        Explicitly enable/disable Live View (idempotent).
        """
        # No-op if already in desired state
        if enable and self.live_view_active:
            return
        if (not enable) and (not self.live_view_active):
            return

        if enable:
            camera.start_camera()
            
            # NEW: force centered full-sensor ROI so preview/still share the same FOV
            try:
                camera.force_centered_scaler_crop()
            except Exception as e:
                print(f"[gui] ScalerCrop force failed (non-fatal): {e}", flush=True)

            # Re-apply settings after pipeline starts (more reliable)
            # NEW: Apply IR quant preset automatically when illumination is Infrared
            self.apply_liveview_camera_profile()
            
                # --- If Live View is IR, brighten the preview with a temporary boost ---
            if self.active_illum_mode == ILLUM_IR:
                try:
                    camera.enable_liveview_boost_for_ir(target_gain=8.0, target_exposure_us=20000)
                except Exception as e:
                    print(f"[gui] enable IR liveview boost error: {e}", flush=True)
            else:
                # Ensure no leftover boost if we re-enter Live View in Green
                try:
                    camera.disable_liveview_boost()
                except Exception:
                    pass
            
            camera.set_af_mode(2)  # Continuous AF for preview

            self.timer.start(100)
            self.live_view_active = True
            self._update_live_view_button()

            # Turn ON selected illumination
            if led_request:
                from gpiod.line import Value
                if self.active_illum_mode == ILLUM_GREEN:
                    led_request.set_value(LED_GREEN_PIN, Value.ACTIVE)
                    led_request.set_value(LED_IR_PIN, Value.INACTIVE)
                else:
                    led_request.set_value(LED_GREEN_PIN, Value.INACTIVE)
                    led_request.set_value(LED_IR_PIN, Value.ACTIVE)

            self.update_status(f"Live View started. {self.active_illum_mode} LED ON.")

        else:
            self.timer.stop()               
            # --- Always clear any preview boost when leaving Live View ---
            try:
                camera.disable_liveview_boost()
            except Exception:
                pass
            
            camera.stop_camera()
            self.live_view_active = False
            self._update_live_view_button()

            # Turn OFF both LEDs
            if led_request:
                from gpiod.line import Value
                led_request.set_value(LED_GREEN_PIN, Value.INACTIVE)
                led_request.set_value(LED_IR_PIN, Value.INACTIVE)

            self.update_status("Live View stopped.")

    def toggle_live_view(self):
        """UI button handler: toggle live view on/off."""
        self.set_live_view(not self.live_view_active)

    def show_experiment_snapshot(self, plate_idx: int):
        """
        During an experiment, show a single low-res snapshot (lores) near the start
        of each plate's settling window so the user can see carousel progress.
        We defer ~700 ms so residual motion and AE have begun to settle.
        """
        # If live view is active, snapshots are redundant (live view shows continuously)
        if self.live_view_active:
            return

        # Defer the actual grab slightly; improves both alignment and brightness
        QTimer.singleShot(1500, lambda: self._grab_deferred_snapshot(plate_idx))


    def _grab_deferred_snapshot(self, plate_idx: int):
        """
        Helper that actually grabs the deferred monitor snapshot.
        Applies a temporary IR preview boost (gain/exposure) for visibility and
        restores the previous state immediately after.
        """
        boosted = False

        # IR-only temporary brightening for monitor visibility (no effect on saved stills)
        if self.active_illum_mode == ILLUM_IR:
            try:
                camera.enable_liveview_boost_for_ir(
                    target_gain=8.0,
                    target_exposure_us=20000
                )
                boosted = True
            except Exception:
                pass

        # Use lores (the same stream as Live View) so composition matches Live View exactly
        _ = camera.get_frame()           # warm-up throwaway
        frame = camera.get_frame()       # actual snapshot frame


        # Always restore any temporary boost
        if boosted:
            try:
                camera.disable_liveview_boost()
            except Exception:
                pass

        if frame.isNull():
            return




        # --- DIAGNOSTIC: log snapshot source & size (LORES) ---
        try:
            w = frame.width(); h = frame.height()
            self.log_panel.append(f"[snapshot] source=LORES size={w}x{h}")
        except Exception:
            pass

        # NEW: paint-centered, letterboxed rendering (no crop, guaranteed centering)
        self._set_centered_pixmap(frame)
        self.status_label.setText(f"Plate #{plate_idx} (snapshot)")

    def update_camera_frame(self):
        
        if not self.live_view_active:
            return

        frame = camera.get_frame()
        if frame.isNull():
            return
        # Paint-centered, letterboxed rendering (no crop, guaranteed centering)
        self._set_centered_pixmap(frame)

    def open_camera_config(self):
        if self.live_view_active:
            self.toggle_live_view()  # Stop live preview while changing settings
        dialog = CameraConfigDialog(current_settings=camera.get_current_settings(), parent=self)
        if dialog.exec() == QDialog.Accepted:
            # Dialog saves settings to JSON internally
            camera.apply_settings(dialog.settings)
            self.update_status("Camera settings applied.")
            # Optionally restart Live View so user can see effect immediately
            # self.toggle_live_view()  # Uncomment if desired

    def set_led(self, on: bool, mode: str):
        """LED control helper passed to ExperimentRunner."""
        if not led_request:
            return
        from gpiod.line import Value
        if mode == ILLUM_GREEN:
            led_request.set_value(LED_GREEN_PIN, Value.ACTIVE if on else Value.INACTIVE)
            led_request.set_value(LED_IR_PIN, Value.INACTIVE)
        else:
            led_request.set_value(LED_GREEN_PIN, Value.INACTIVE)
            led_request.set_value(LED_IR_PIN, Value.ACTIVE if on else Value.INACTIVE)

    def open_file_manager(self):
        # Stop Live View to avoid racing the camera while user manages files (optional)
        if self.live_view_active:
            self.toggle_live_view()
        dlg = FileManagerDialog(self)
        dlg.showMaximized()   # maximize for usability on Touch Display 2
        dlg.exec()

    def update_fullscreen_button_text(self):
        """Update the on-screen toggle button text based on window state."""
        if hasattr(self, "fullscreen_btn") and self.fullscreen_btn:
            self.fullscreen_btn.setText("Exit Full Screen" if self.isFullScreen() else "Full Screen")

    def set_fullscreen(self, enabled: bool):
        """Enter/exit fullscreen (kiosk) mode."""
        if enabled:
            self.showFullScreen()
        else:
            self.showNormal()
            # Optional: if you prefer exiting fullscreen -> maximized instead of normal:
            # self.showMaximized()

        self.update_fullscreen_button_text()

    def toggle_fullscreen(self):
        """Toggle fullscreen state."""
        self.set_fullscreen(not self.isFullScreen())

    def keyPressEvent(self, event):
        """Keyboard fallbacks for testing/maintenance."""
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.set_fullscreen(False)
            event.accept()
            return
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Graceful shutdown
        if self.experiment_thread and self.experiment_thread.isRunning():
            self.experiment_thread.abort()
            self.experiment_thread.wait()
        if self.homing_worker and self.homing_worker.isRunning():
            self.stop_homing()
            self.homing_worker.wait()
        if self.live_view_active:
            self.toggle_live_view()
        event.accept()


# Abortable homing worker
class HomingWorker(QThread):
    status_signal = Signal(str)
    finished_with_result = Signal(object)  # plate index (int) on success, or None

    def __init__(self):
        super().__init__()
        self._abort = False

    def request_stop(self):
        self._abort = True

    def _should_abort(self):
        return self._abort

    def run(self):
        try:
            plate = motor_control.home(
                status_callback=self.status_signal.emit,
                should_abort=self._should_abort
            )
            if plate is not None:
                self.status_signal.emit(f"Homing finished. Plate #{plate}")
            else:
                self.status_signal.emit("Homing stopped.")
            self.finished_with_result.emit(plate)
        except Exception as e:
            self.status_signal.emit(f"Error: {e}")
            self.finished_with_result.emit(None)


# MotorWorker class (kept for 'advance' only, with driver enable)
class MotorWorker(QThread):
    status_signal = Signal(str)

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        try:
            if self.action == "advance":
                self.status_signal.emit("Advancing to next plate...")
                motor_control.driver_enable()  # ensure enabled before motion
                motor_control.advance(status_callback=self.status_signal.emit)
            elif self.action == "home":
                # Not used anymore (replaced by HomingWorker), kept for compatibility
                motor_control.driver_enable()
                plate = motor_control.home(status_callback=self.status_signal.emit)
                if plate is not None:
                    self.status_signal.emit(f"Homing finished. Plate #{plate}")
                else:
                    self.status_signal.emit("Homing failed")
        except Exception as e:
            self.status_signal.emit(f"Error: {e}")