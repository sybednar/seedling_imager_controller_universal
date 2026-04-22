#gui.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QDialog
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from styles import dark_style
from experiment_setup import ExperimentSetupDialog, ILLUM_GREEN, ILLUM_IR
from experiment_runner import ExperimentRunner
from camera_config import CameraConfigDialog
from file_manager import FileManagerDialog
import motor_control
import camera

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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Time_Lapse Seedling Imager")
        self.setFixedSize(800, 480)
        self.setStyleSheet(dark_style)

        self.threads = []
        self.experiment_thread = None
        self.homing_worker = None  # <-- abortable homing worker
        self.active_illum_mode = ILLUM_GREEN

        main_layout = QHBoxLayout()

        # Left: buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(15)
        button_layout.setAlignment(Qt.AlignTop)
        button_width = 250

        # Live View toggle button (text reflects current state)
        self.live_view_btn = QPushButton("Turn Live View On")
        self.live_view_btn.setFixedWidth(button_width)
        self.live_view_btn.setStyleSheet(dark_style + " QPushButton { background-color: #FFD600; color: black; font-weight: bold; }")
        self.live_view_btn.clicked.connect(self.toggle_live_view)
        button_layout.addWidget(self.live_view_btn)

        self.illum_toggle_btn = QPushButton(f"Illum: {self.active_illum_mode}")
        self.illum_toggle_btn.setFixedWidth(button_width)
        self.apply_main_illum_style()
        self.illum_toggle_btn.clicked.connect(self.toggle_illumination_mode)
        button_layout.addWidget(self.illum_toggle_btn)

        ha_layout = QHBoxLayout()
        self.home_btn = QPushButton("Home");    self.home_btn.setFixedWidth(button_width // 2 - 5)
        self.home_btn.setObjectName("homeBtn")  # precise styling when in STOP state
        self.advance_btn = QPushButton("Advance"); self.advance_btn.setFixedWidth(button_width // 2 - 5)
        ha_layout.addWidget(self.home_btn); ha_layout.addWidget(self.advance_btn)

        # Stateful home/stop behavior
        self.home_btn.clicked.connect(self.on_home_clicked)
        # Keep MotorWorker for "advance" only
        self.advance_btn.clicked.connect(lambda: self.run_motor_action("advance"))
        button_layout.addLayout(ha_layout)

        self.experiment_btn = QPushButton("Experiment Setup")
        self.experiment_btn.setFixedWidth(button_width)
        self.experiment_btn.setStyleSheet(dark_style + " QPushButton { background-color: #8E24AA; color: white; }")
        self.experiment_btn.clicked.connect(self.open_experiment_setup)
        button_layout.addWidget(self.experiment_btn)

        self.end_experiment_btn = QPushButton("End Experiment")
        self.end_experiment_btn.setFixedWidth(button_width)
        self.end_experiment_btn.setStyleSheet(dark_style + " QPushButton { background-color: #E53935; color: white; }")
        self.end_experiment_btn.clicked.connect(self.end_experiment)
        button_layout.addWidget(self.end_experiment_btn)

        # Camera Config button
        self.camera_config_btn = QPushButton("Camera Config")
        self.camera_config_btn.setFixedWidth(button_width)
        self.camera_config_btn.setStyleSheet(dark_style + " QPushButton { background-color: #546E7A; color: white; }")
        self.camera_config_btn.clicked.connect(self.open_camera_config)
        button_layout.addWidget(self.camera_config_btn)

        self.file_manager_btn = QPushButton("File Manager")
        self.file_manager_btn.setFixedWidth(button_width)
        self.file_manager_btn.setStyleSheet(
            dark_style + " QPushButton { background-color: #455A64; color: white; }"
        )
        self.file_manager_btn.clicked.connect(self.open_file_manager)
        button_layout.addWidget(self.file_manager_btn)

        # --- Exit to Desktop (backdoor exit) ---
        self.exit_btn = QPushButton("Exit to Desktop")
        self.exit_btn.setFixedWidth(button_width)
        self.exit_btn.setStyleSheet(
            dark_style + " QPushButton { background-color: #D32F2F; color: white; font-weight: bold; }"
        )
        self.exit_btn.clicked.connect(self.close)  # will trigger closeEvent and quit the app
        button_layout.addWidget(self.exit_btn)

        main_layout.addLayout(button_layout)

        # Right: status + camera + log
        right_layout = QVBoxLayout()
        self.status_label = QLabel("Status: Ready"); self.status_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.status_label)

        self.camera_label = QLabel("Camera Preview"); self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setFixedSize(512, 288)
        right_layout.addWidget(self.camera_label, alignment=Qt.AlignRight)

        self.log_panel = QTextEdit(); self.log_panel.setReadOnly(True)
        right_layout.addWidget(self.log_panel)

        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        self.timer = QTimer(); self.timer.timeout.connect(self.update_camera_frame)
        self.live_view_active = False

        self.update_controls_for_experiment(False)

        # Apply persisted camera settings at startup
        camera.apply_settings()   
        
        # Keep button state consistent at startup
        self._update_live_view_button()

        # Auto-start Live View shortly after the window shows.
        # singleShot avoids starting the camera before Qt's event loop is running.
        QTimer.singleShot(200, lambda: self.set_live_view(True))


    # ---------- Illumination ----------
    def apply_main_illum_style(self):
        color = "#26A69A" if self.active_illum_mode == ILLUM_GREEN else "#B71C1C"
        self.illum_toggle_btn.setStyleSheet(
            dark_style + f" QPushButton {{ background-color: {color}; color: white; font-weight: bold; }}"
        )

    def apply_liveview_camera_profile(self):
        """Temporary camera profile based on illumination (IR quant vs baseline)."""
        base = camera.get_current_settings()
        if self.active_illum_mode == ILLUM_IR:
            base = camera.apply_ir_quant_preset(base)
        camera.apply_settings(base)

    def toggle_illumination_mode(self):
        """Switch between Green and Infrared illumination; update button style."""
        self.active_illum_mode = ILLUM_IR if self.active_illum_mode == ILLUM_GREEN else ILLUM_GREEN
        self.illum_toggle_btn.setText(f"Illum: {self.active_illum_mode}")
        self.apply_main_illum_style()
        # If live view is active, apply the new illumination immediately
        if self.live_view_active and led_request:
            from gpiod.line import Value
            if self.active_illum_mode == ILLUM_GREEN:
                led_request.set_value(LED_GREEN_PIN, Value.ACTIVE)
                led_request.set_value(LED_IR_PIN, Value.INACTIVE)
            else:
                led_request.set_value(LED_GREEN_PIN, Value.INACTIVE)
                led_request.set_value(LED_IR_PIN, Value.ACTIVE)
        # Apply camera profile + toggle IR live-view boost
        try:
            self.apply_liveview_camera_profile()
            if self.active_illum_mode == ILLUM_IR:
                camera.enable_liveview_boost_for_ir(target_gain=8.0, target_exposure_us=20000)
            else:
                camera.disable_liveview_boost()
        except Exception as e:
            print(f"[gui] liveview boost toggle error: {e}", flush=True)
        self.update_status(f"Illumination set to {self.active_illum_mode}")

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
            plates, days, freq, illum, self.set_led, perform_homing=(not skip_initial_homing)
        )
        self.experiment_thread.status_signal.connect(self.update_status)
        self.experiment_thread.image_saved_signal.connect(lambda p: self.log_panel.append(f"Image saved: {p}"))
        self.experiment_thread.plate_signal.connect(lambda idx: self.status_label.setText(f"Plate #{idx}"))
        self.experiment_thread.settling_started.connect(
            lambda plate: QTimer.singleShot(1000, lambda: self.show_experiment_snapshot(plate))
        )
        self.experiment_thread.finished_signal.connect(self.on_experiment_finished)
        self.update_controls_for_experiment(True)
        self.experiment_thread.start()

    def end_experiment(self):
        if self.experiment_thread and self.experiment_thread.isRunning():
            self.experiment_thread.abort(); self.experiment_thread.wait()
            self.update_status("Experiment ended by user.")
        else:
            self.update_status("No experiment running.")
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

    # ---------- Camera / LEDs / File manager ----------
    def update_status(self, text):
        self.status_label.setText(text)
        self.log_panel.append(text)

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
        if enable and self.live_view_active:
            return
        if (not enable) and (not self.live_view_active):
            return
        if enable:
            camera.start_camera()
            # Apply IR quant preset automatically for IR; baseline for Green
            self.apply_liveview_camera_profile()
            # Brighten IR preview with a temporary boost
            if self.active_illum_mode == ILLUM_IR:
                try:
                    camera.enable_liveview_boost_for_ir(target_gain=8.0, target_exposure_us=20000)
                except Exception as e:
                    print(f"[gui] enable IR liveview boost error: {e}", flush=True)
            else:
                try:
                    camera.disable_liveview_boost()
                except Exception:
                    pass
            camera.set_af_mode(2)  # Continuous AF for preview
            self.timer.start(100)
            self.live_view_active = True
            self._update_live_view_button()
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
            # Always clear any preview boost when leaving Live View
            try:
                camera.disable_liveview_boost()
            except Exception:
                pass
            camera.stop_camera()
            self.live_view_active = False
            self._update_live_view_button()
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
        During an experiment, show a single low-res snapshot (lores) at the start
        of each plate's settling window so users can see the carousel cycling.
        """
        # If live view is active, snapshots are redundant (and Live View is usually off during runs)
        if self.live_view_active:
            return

        frame = camera.get_frame()
        if frame.isNull():
            return

        pixmap = QPixmap.fromImage(frame)

        # Fill the preview widget area; crop overflow (center-crop) while preserving aspect ratio
        scaled = pixmap.scaled(
            self.camera_label.size(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        self.camera_label.setPixmap(scaled)

        # Optional: make it explicit what the user is seeing
        self.status_label.setText(f"Plate #{plate_idx} (snapshot)")

    def update_camera_frame(self):
        frame = camera.get_frame()
        if frame.isNull():
            return
        pixmap = QPixmap.fromImage(frame)
        scaled = pixmap.scaled(
            self.camera_label.size(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        self.camera_label.setPixmap(scaled)

    def open_camera_config(self):
        # Remember whether Live View was running
        was_live = bool(self.live_view_active)

        # For safety, stop live preview before opening the dialog (reduces driver contention)
        if self.live_view_active:
            self.toggle_live_view()

        # Launch dialog (modal)
        dialog = CameraConfigDialog(current_settings=camera.get_current_settings(), parent=self)
        if dialog.exec() == QDialog.Accepted:
            # Apply settings asynchronously so the GUI thread never blocks
            self.setCursor(Qt.WaitCursor)
            self.update_status("Applying camera settings...")
            worker = SettingsApplier(dialog.settings, preview_was_active=was_live)
            worker.done.connect(lambda ok, msg: self._on_settings_applied(ok, msg, was_live, worker))
            # Keep a reference so GC doesn't collect it early
            if not hasattr(self, "_settings_workers"):
                self._settings_workers = []
            self._settings_workers.append(worker)
            worker.start()
        else:
            # If user cancelled and preview was previously on, return to the prior state
            if was_live and not self.live_view_active:
                self.toggle_live_view()


    def _on_settings_applied(self, ok: bool, msg: str, was_live: bool, worker: QThread):
        # Restore cursor
        self.unsetCursor()
        # Drop the worker reference
        try:
            self._settings_workers.remove(worker)
        except Exception:
            pass
        # Report to user
        self.update_status(msg)

        # If the preview was previously active, turn it back on so the user sees the effect
        if was_live and not self.live_view_active:
            self.toggle_live_view()

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
        dlg.showMaximized()        
        dlg.exec()

    def keyPressEvent(self, event):
        # Backdoor exit: ESC closes the app
        if event.key() == Qt.Key_Escape:
            self.close()
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

# ---- SettingsApplier: apply camera settings off the GUI thread ----
class SettingsApplier(QThread):
    done = Signal(bool, str)  # (success, message)

    def __init__(self, settings: dict, preview_was_active: bool):
        super().__init__()
        self.settings = dict(settings) if settings else {}
        self.preview_was_active = bool(preview_was_active)

    def run(self):
        try:
            # Ensure a running pipeline before setting controls; many controls are safer then
            camera.start_camera()
            camera.apply_settings(self.settings)
            ok = True
            msg = "Camera settings applied."
        except Exception as e:
            ok = False
            msg = f"Camera settings error: {e}"
        finally:
            # If Live View was not previously active, stop again so we leave state as we found it
            if not self.preview_was_active:
                try:
                    camera.stop_camera()
                except Exception:
                    pass
        self.done.emit(ok, msg)