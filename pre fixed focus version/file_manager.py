
# file_manager.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QTextEdit, QFileDialog, QMessageBox, QTabWidget,
    QWidget, QScrollArea, QGridLayout, QFrame, QToolBar, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QImage

from pathlib import Path
import json
import shutil
import zipfile
import os
import csv
import numpy as np

# Optional imports (handled gracefully)
try:
    import tifffile as tiff
except Exception:
    tiff = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import cv2
except Exception:
    cv2 = None

IMAGES_ROOT = Path("/home/sybednar/Seedling_Imager/images").expanduser()
IMG_EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}

# ---------- small utilities ----------

def human_size(bytes_val: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_val)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0

def folder_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except Exception:
                pass
    return total

def list_images(path: Path) -> list[Path]:
    imgs = []
    for root, _, files in os.walk(path):
        for f in files:
            if Path(f).suffix.lower() in IMG_EXTS:
                imgs.append(Path(root) / f)
    return sorted(imgs, key=lambda p: p.stat().st_mtime, reverse=True)  # newest first

# ---------- robust thumbnail loader ----------

def _to_rgb8(arr: np.ndarray) -> np.ndarray:
    """
    Convert an ndarray to 8-bit RGB:
      - grayscale -> stack to RGB
      - RGBA -> drop alpha
      - 16-bit -> downscale to 8-bit by shifting/right dividing
    """
    if arr.ndim == 2:
        # grayscale → RGB
        g = arr
        # to 8-bit
        if g.dtype == np.uint16:
            g8 = (g >> 8).astype(np.uint8)
        else:
            g8 = g.astype(np.uint8)
        rgb = np.stack([g8, g8, g8], axis=-1)
        return rgb

    if arr.ndim == 3:
        # If it's multi-page, pick first page/frame
        if arr.shape[0] > 4 and arr.shape[-1] not in (3, 4):  # e.g., (frames, H, W)
            arr = arr[0]

        h, w, c = arr.shape
        if c == 4:
            arr = arr[:, :, :3]  # drop alpha

        # 16-bit → 8-bit
        if arr.dtype == np.uint16:
            arr8 = (arr >> 8).astype(np.uint8)
        else:
            arr8 = arr.astype(np.uint8)

        return arr8

    # Fallback: try flatten to 3-ch
    arr = np.squeeze(arr)
    if arr.ndim == 2:
        return _to_rgb8(arr)
    elif arr.ndim == 3:
        return _to_rgb8(arr)
    else:
        # give up
        return None

def safe_pixmap_from_path(p: Path, thumb_size: QSize) -> QPixmap | None:
    """
    Try to create a QPixmap thumbnail from file path:
      1) QPixmap loader
      2) tifffile → numpy → QImage → QPixmap
      3) Pillow (PIL) → QImage → QPixmap
      4) OpenCV → QImage → QPixmap
    Returns a scaled QPixmap or None if all methods fail.
    """
    # 1) Qt's native loader
    pix = QPixmap(str(p))
    if not pix.isNull():
        return pix.scaled(thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # 2) tifffile (best for scientific TIFF variants)
    if tiff is not None:
        try:
            arr = tiff.imread(str(p))
            rgb8 = _to_rgb8(arr)
            if rgb8 is not None:
                h, w = rgb8.shape[:2]
                qimg = QImage(rgb8.data, w, h, w * 3, QImage.Format_RGB888)
                qp = QPixmap.fromImage(qimg)
                if not qp.isNull():
                    return qp.scaled(thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            pass

    # 3) Pillow
    if Image is not None:
        try:
            im = Image.open(str(p))
            im = im.convert("RGB")
            rgb8 = np.array(im)
            h, w = rgb8.shape[:2]
            qimg = QImage(rgb8.data, w, h, w * 3, QImage.Format_RGB888)
            qp = QPixmap.fromImage(qimg)
            if not qp.isNull():
                return qp.scaled(thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            pass

    # 4) OpenCV
    if cv2 is not None:
        try:
            bgr = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if bgr is not None:
                # normalize to 8-bit RGB
                if bgr.ndim == 2:
                    bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
                elif bgr.shape[-1] == 4:
                    bgr = bgr[:, :, :3]
                rgb8 = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                h, w = rgb8.shape[:2]
                qimg = QImage(rgb8.data, w, h, w * 3, QImage.Format_RGB888)
                qp = QPixmap.fromImage(qimg)
                if not qp.isNull():
                    return qp.scaled(thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            pass

    return None

# ---------- main dialog ----------

class FileManagerDialog(QDialog):
    """
    File manager for Seedling Imager experiments.
    - Toolbar (Refresh/Open/Archive/Export/Delete/Open CSV + Plate filter)
    - Details tab (metadata.json, size, image count)
    - Thumbnails tab (click opens full image via system viewer; robust TIFF fallback)
    - CSV tab (renders metadata.csv as a sortable table)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Manager")
        self.setMinimumWidth(900)
        self.setMinimumHeight(560)

        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        # Disk usage header
        self.disk_label = QLabel(self.disk_usage_text())
        self.disk_label.setAlignment(Qt.AlignLeft)
        main.addWidget(self.disk_label)

        # ---- Toolbar ----
        tb = QToolBar(); tb.setMovable(False)

        act_refresh = QAction("Refresh", self); act_refresh.setShortcut(QKeySequence("Ctrl+R"))
        act_refresh.triggered.connect(self.populate); tb.addAction(act_refresh)

        act_open = QAction("Open Folder", self); act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self.open_folder); tb.addAction(act_open)

        act_archive = QAction("Archive (ZIP)", self); act_archive.setShortcut(QKeySequence("Ctrl+Z"))
        act_archive.triggered.connect(self.archive_selected); tb.addAction(act_archive)

        act_export = QAction("Export to…", self); act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self.export_selected); tb.addAction(act_export)

        act_delete = QAction("Delete", self); act_delete.setShortcut(QKeySequence.Delete)
        act_delete.triggered.connect(self.delete_selected); tb.addAction(act_delete)

        act_open_csv = QAction("Open CSV", self); act_open_csv.setShortcut(QKeySequence("Ctrl+M"))
        act_open_csv.triggered.connect(self.open_csv_external); tb.addAction(act_open_csv)

        tb.addSeparator()
        tb.addWidget(QLabel("Filter: "))
        self.plate_filter = QComboBox()
        self.plate_filter.addItems(["All plates", "plate1", "plate2", "plate3", "plate4", "plate5", "plate6"])
        self.plate_filter.currentIndexChanged.connect(self.on_selection_changed)
        tb.addWidget(self.plate_filter)

        main.addWidget(tb)

        # ---- Middle: experiment list + tabs ----
        mid = QHBoxLayout(); mid.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        mid.addWidget(self.list_widget, stretch=1)

        self.tabs = QTabWidget()
        # Details tab
        details_wrap = QWidget()
        dlay = QVBoxLayout(details_wrap); dlay.setContentsMargins(4, 4, 4, 4)
        self.details_text = QTextEdit(); self.details_text.setReadOnly(True)
        dlay.addWidget(self.details_text)
        self.tabs.addTab(details_wrap, "Details")

        # Thumbnails tab
        self.thumb_scroll = QScrollArea(); self.thumb_scroll.setWidgetResizable(True)
        self.thumb_container = QWidget()
        self.thumb_grid = QGridLayout(self.thumb_container)
        self.thumb_grid.setContentsMargins(8, 8, 8, 8); self.thumb_grid.setSpacing(8)
        self.thumb_scroll.setWidget(self.thumb_container)
        self.tabs.addTab(self.thumb_scroll, "Thumbnails")

        # CSV tab
        csv_wrap = QWidget()
        csv_layout = QVBoxLayout(csv_wrap); csv_layout.setContentsMargins(4, 4, 4, 4)
        self.csv_table = QTableWidget()
        self.csv_table.setAlternatingRowColors(True)
        self.csv_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.csv_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.csv_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.csv_table.setSortingEnabled(True)
        csv_layout.addWidget(self.csv_table)
        self.tabs.addTab(csv_wrap, "CSV")

        mid.addWidget(self.tabs, stretch=2)
        main.addLayout(mid)

        # Bottom buttons (optional duplicates)
        btns = QHBoxLayout(); btns.setSpacing(8)
        self.refresh_btn = QPushButton("Refresh"); self.refresh_btn.clicked.connect(self.populate)
        self.open_btn = QPushButton("Open Folder"); self.open_btn.clicked.connect(self.open_folder)
        self.archive_btn = QPushButton("Archive (ZIP)"); self.archive_btn.clicked.connect(self.archive_selected)
        self.export_btn = QPushButton("Export to…"); self.export_btn.clicked.connect(self.export_selected)
        self.delete_btn = QPushButton("Delete"); self.delete_btn.clicked.connect(self.delete_selected)
        self.close_btn = QPushButton("Close"); self.close_btn.clicked.connect(self.accept)
        for b in (self.refresh_btn, self.open_btn, self.archive_btn, self.export_btn, self.delete_btn):
            btns.addWidget(b)
        btns.addStretch(); btns.addWidget(self.close_btn)
        main.addLayout(btns)

        # Initial populate
        self.populate()

    # ---- data & UI helpers ----

    def disk_usage_text(self) -> str:
        try:
            total, used, free = shutil.disk_usage(IMAGES_ROOT)
            return (f"Images root: {IMAGES_ROOT}  |  Total: {human_size(total)}  Used: {human_size(used)}  Free: {human_size(free)}")
        except Exception:
            return f"Images root: {IMAGES_ROOT} (disk usage unavailable)"

    def experiments(self) -> list[Path]:
        IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
        exps = [p for p in IMAGES_ROOT.iterdir() if p.is_dir() and p.name.startswith("experiment_")]
        return sorted(exps, key=lambda x: x.stat().st_mtime, reverse=True)

    def populate(self):
        self.list_widget.clear()
        for exp in self.experiments():
            item = QListWidgetItem(exp.name); item.setData(Qt.UserRole, str(exp))
            self.list_widget.addItem(item)
        self.disk_label.setText(self.disk_usage_text())
        self.details_text.clear()
        self.clear_thumbnails()
        self.clear_csv()

    def selected_experiment_path(self) -> Path | None:
        items = self.list_widget.selectedItems()
        return Path(items[0].data(Qt.UserRole)) if items else None

    # ---- selection change: details + thumbnails + CSV ----

    def on_selection_changed(self):
        exp_path = self.selected_experiment_path()
        if not exp_path:
            self.details_text.clear(); self.clear_thumbnails(); self.clear_csv()
            return

        images_all = list_images(exp_path)
        size_bytes = folder_size(exp_path)
        meta = exp_path / "metadata.json"

        lines = [
            f"Experiment folder: {exp_path}",
            f"Size: {human_size(size_bytes)}",
            f"Image files: {len(images_all)}"
        ]
        if meta.exists():
            try:
                j = json.loads(meta.read_text())
                lines.append("\nmetadata.json:")
                lines.append(json.dumps(j, indent=2))
            except Exception as e:
                lines.append(f"\nmetadata.json read error: {e}")
        else:
            lines.append("\nmetadata.json not found.")

        csv_path = exp_path / "metadata.csv"
        if csv_path.exists():
            lines.append(f"\nmetadata.csv found ({csv_path.name}). Use the 'CSV' tab or 'Open CSV' to view.")

        self.details_text.setPlainText("\n".join(lines))

        # Plate filter for thumbnails
        filter_text = self.plate_filter.currentText()
        if filter_text == "All plates":
            images = images_all
        else:
            images = [p for p in images_all if p.parent.name.lower() == filter_text.lower()]

        self.render_thumbnails(images[:200])  # recent 200 thumbs
        self.render_csv(exp_path)

    # ---- thumbnails ----

    def clear_thumbnails(self):
        while self.thumb_grid.count():
            item = self.thumb_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def render_thumbnails(self, image_paths: list[Path]):
        self.clear_thumbnails()
        if not image_paths:
            lbl = QLabel("No images match the current filter.")
            lbl.setAlignment(Qt.AlignCenter)
            self.thumb_grid.addWidget(lbl, 0, 0)
            return

        cols = 4
        thumb_size = QSize(160, 160)
        row = 0
        col = 0

        for p in image_paths:
            frame = QFrame(); frame.setFrameShape(QFrame.StyledPanel)
            v = QVBoxLayout(frame); v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)

            qp = safe_pixmap_from_path(p, thumb_size)
            if qp is None:
                imlbl = QLabel("(preview unavailable)")
                imlbl.setAlignment(Qt.AlignCenter)
                v.addWidget(imlbl)
            else:
                imlbl = QLabel()
                imlbl.setPixmap(qp)
                imlbl.setAlignment(Qt.AlignCenter)
                imlbl.setToolTip(str(p))
                # click-to-open
                imlbl.mousePressEvent = lambda e, fp=str(p): self.open_image(fp)
                v.addWidget(imlbl)

            cap = QLabel(p.parent.name + "/" + p.name)
            cap.setWordWrap(True); cap.setAlignment(Qt.AlignCenter)
            v.addWidget(cap)

            self.thumb_grid.addWidget(frame, row, col)
            col += 1
            if col >= cols:
                col = 0; row += 1

    def open_image(self, filepath: str):
        try:
            os.system(f'xdg-open "{filepath}" >/dev/null 2>&1 &')
        except Exception as e:
            QMessageBox.warning(self, "Open Image", f"Failed to open image:\n{e}")

    # ---- CSV tab ----

    def clear_csv(self):
        self.csv_table.clear()
        self.csv_table.setRowCount(0)
        self.csv_table.setColumnCount(0)

    def render_csv(self, exp_path: Path):
        csv_path = exp_path / "metadata.csv"
        self.clear_csv()

        if not csv_path.exists():
            self.csv_table.setColumnCount(1)
            self.csv_table.setRowCount(1)
            self.csv_table.setHorizontalHeaderLabels(["metadata.csv"])
            self.csv_table.setItem(0, 0, QTableWidgetItem("No metadata.csv found in this experiment."))
            self.csv_table.resizeColumnsToContents()
            return

        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            self.csv_table.setColumnCount(1)
            self.csv_table.setRowCount(1)
            self.csv_table.setHorizontalHeaderLabels(["metadata.csv"])
            self.csv_table.setItem(0, 0, QTableWidgetItem(f"Failed to read CSV: {e}"))
            self.csv_table.resizeColumnsToContents()
            return

        if not rows:
            self.csv_table.setColumnCount(1)
            self.csv_table.setRowCount(1)
            self.csv_table.setHorizontalHeaderLabels(["metadata.csv"])
            self.csv_table.setItem(0, 0, QTableWidgetItem("CSV is empty."))
            self.csv_table.resizeColumnsToContents()
            return

        header = rows[0]
        data_rows = rows[1:]

        self.csv_table.setColumnCount(len(header))
        self.csv_table.setHorizontalHeaderLabels(header)
        self.csv_table.setRowCount(len(data_rows))
        for r, row in enumerate(data_rows):
            for c, cell in enumerate(row):
                self.csv_table.setItem(r, c, QTableWidgetItem(cell))
        self.csv_table.resizeColumnsToContents()

    def open_csv_external(self):
        exp_path = self.selected_experiment_path()
        if not exp_path:
            QMessageBox.information(self, "Open CSV", "Please select an experiment.")
            return
        csv_path = exp_path / "metadata.csv"
        if not csv_path.exists():
            QMessageBox.information(self, "Open CSV", "metadata.csv not found in selected experiment.")
            return
        try:
            os.system(f'xdg-open "{csv_path}" >/dev/null 2>&1 &')
        except Exception as e:
            QMessageBox.warning(self, "Open CSV", f"Failed to open CSV:\n{e}")

    # ---- actions ----

    def open_folder(self):
        exp_path = self.selected_experiment_path()
        if not exp_path:
            QMessageBox.information(self, "Open Folder", "Please select an experiment.")
            return
        try:
            os.system(f'xdg-open "{exp_path}" >/dev/null 2>&1 &')
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Failed to open folder:\n{e}")

    def archive_selected(self):
        exp_path = self.selected_experiment_path()
        if not exp_path:
            QMessageBox.information(self, "Archive (ZIP)", "Please select an experiment.")
            return
        archive_name = exp_path.parent / f"{exp_path.name}.zip"
        dest, _ = QFileDialog.getSaveFileName(self, "Save ZIP Archive", str(archive_name), "ZIP files (*.zip)")
        if not dest:
            return
        try:
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for root, _, files in os.walk(exp_path):
                    for f in files:
                        fp = Path(root) / f
                        arcname = str(fp.relative_to(exp_path))
                        z.write(fp, arcname)
            QMessageBox.information(self, "Archive", f"Archived to:\n{dest}")
        except Exception as e:
            QMessageBox.warning(self, "Archive", f"Failed to archive:\n{e}")

    def export_selected(self):
        exp_path = self.selected_experiment_path()
        if not exp_path:
            QMessageBox.information(self, "Export", "Please select an experiment.")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Choose export destination")
        if not target_dir:
            return
        dest = Path(target_dir) / exp_path.name
        if dest.exists():
            confirm = QMessageBox.question(
                self, "Export",
                f"Destination {dest} already exists.\nOverwrite?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
            try:
                shutil.rmtree(dest)
            except Exception as e:
                QMessageBox.warning(self, "Export", f"Failed to remove existing folder:\n{e}")
                return
        try:
            shutil.copytree(exp_path, dest)
            QMessageBox.information(self, "Export", f"Exported to:\n{dest}")
        except Exception as e:
            QMessageBox.warning(self, "Export", f"Export failed:\n{e}")

    def delete_selected(self):
        exp_path = self.selected_experiment_path()
        if not exp_path:
            QMessageBox.information(self, "Delete", "Please select an experiment.")
            return
        confirm = QMessageBox.question(
            self, "Delete Experiment",
            f"Are you sure you want to permanently delete:\n{exp_path} ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(exp_path)
            self.populate()
            QMessageBox.information(self, "Delete", "Experiment deleted.")
        except Exception as e:
            QMessageBox.warning(self, "Delete", f"Delete failed:\n{e}")
