"""
main_window.py — CITableCleaner main application window.

Layout
------
  ┌─────────────────────────────────────────────────────────┐
  │  [Load CSV]  <filename label>           [loading bar]   │  ← toolbar
  ├────────────────────────────┬────────────────────────────┤
  │                            │  Columns                   │
  │   Well-plate grid          │  ┌──────────────────────┐  │
  │   (WellPlateWidget)        │  │ ☑ CellArea           │  │
  │                            │  │ ☑ NucleusArea        │  │
  │  [Sel All] [Desel All]     │  │ …                    │  │
  │  <plate format label>      │  └──────────────────────┘  │
  │                            │  [Sel All] [Desel All]     │
  ├────────────────────────────┴────────────────────────────┤
  │  Output folder: <path>  [Browse]       [Export CSV]     │  ← bottom bar
  ├─────────────────────────────────────────────────────────┤
  │  statusbar: rows / wells / columns info                 │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import List, Set

import pandas as pd
from PyQt6.QtCore import Qt, QSettings, QThread
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from citablecleaner.plate_widget import WellPlateWidget
from citablecleaner.worker import ExportWorker, LoadWorker

_VERSION_FILE = Path(__file__).parent.parent / "version.txt"
try:
    _APP_VERSION = _VERSION_FILE.read_text().strip()
except OSError:
    _APP_VERSION = "1.0.0"

# ── Stylesheet (dark slate / sky-blue) ─────────────────────────────────────

_STYLESHEET = """
/* ── Global ── */
QMainWindow, QWidget {
    background-color: #0f172a;
    color: #f1f5f9;
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}

/* ── Toolbar ── */
QToolBar {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
    padding: 4px 8px;
    spacing: 8px;
}

/* ── Buttons ── */
QPushButton {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #38bdf8;
    color: #38bdf8;
}
QPushButton:pressed {
    background-color: #0ea5e9;
    color: #0f172a;
    border-color: #0ea5e9;
}
QPushButton:disabled {
    background-color: #1e293b;
    color: #475569;
    border-color: #334155;
}

/* ── Accent button (Export) ── */
QPushButton#exportBtn {
    background-color: #0369a1;
    border-color: #38bdf8;
    color: #f1f5f9;
    font-weight: bold;
}
QPushButton#exportBtn:hover {
    background-color: #0ea5e9;
    color: #0f172a;
}
QPushButton#exportBtn:pressed {
    background-color: #0284c7;
}
QPushButton#exportBtn:disabled {
    background-color: #1e293b;
    color: #475569;
    border-color: #334155;
    font-weight: normal;
}

/* ── Labels ── */
QLabel#fileLabel {
    color: #94a3b8;
    font-size: 9pt;
}
QLabel#sectionTitle {
    color: #38bdf8;
    font-weight: bold;
    font-size: 10pt;
    padding: 4px 0 2px 0;
}
QLabel#plateFormatLabel {
    color: #94a3b8;
    font-size: 9pt;
    font-style: italic;
}
QLabel#outputFolderLabel {
    color: #94a3b8;
    font-size: 9pt;
}

/* ── Progress bar ── */
QProgressBar {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #38bdf8;
    border-radius: 4px;
}

/* ── List / scroll ── */
QListWidget {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
    alternate-background-color: #243040;
}
QListWidget::item {
    padding: 3px 4px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #0369a1;
    color: #f1f5f9;
}
QListWidget::item:hover {
    background-color: #334155;
}

QScrollBar:vertical {
    background: #1e293b;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #475569;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #38bdf8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* ── Splitter ── */
QSplitter::handle {
    background-color: #334155;
    width: 3px;
}

/* ── Status bar ── */
QStatusBar {
    background-color: #1e293b;
    border-top: 1px solid #334155;
    color: #94a3b8;
    font-size: 9pt;
}

/* ── Frames / separators ── */
QFrame#separator {
    background-color: #334155;
    max-height: 1px;
}

/* ── SpinBox — base colours only; arrow buttons styled per-widget at runtime ── */
QSpinBox {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 3px 4px;
    min-height: 24px;
}
QSpinBox:hover {
    border-color: #38bdf8;
}
QSpinBox:disabled {
    color: #475569;
    border-color: #334155;
    background-color: #1e293b;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"CITableCleaner {_APP_VERSION}")
        self.setMinimumSize(900, 580)
        self.resize(1200, 700)
        self.setStyleSheet(_STYLESHEET)

        # ── Persistent settings ────────────────────────────────────────────
        self._settings = QSettings("RonHoebe", "CITableCleaner")

        # ── State ─────────────────────────────────────────────────────────
        self._df: pd.DataFrame | None = None
        self._last_csv_path: str = self._settings.value(
            "last_csv_path", str(Path.home())
        )
        self._output_folder: str = self._settings.value(
            "output_folder", str(Path.home())
        )
        self._load_worker:   LoadWorker   | None = None
        self._export_worker: ExportWorker | None = None

        # ── Build UI ──────────────────────────────────────────────────────
        self._build_toolbar()
        self._build_central()
        self._build_bottom_bar()
        self._build_statusbar()

        self._update_export_button()

        # ── Accept file drops on the whole window ──────────────────────────
        self.setAcceptDrops(True)

    # ══════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════

    # ── Drag-and-drop ──────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(('.csv', '.tsv', '.txt', '.xls', '.xlsx'))
                   for u in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        csv_files = [u.toLocalFile() for u in urls
                     if u.toLocalFile().lower().endswith(('.csv', '.tsv', '.txt', '.xls', '.xlsx'))]
        if csv_files:
            self._start_load(csv_files[0])

    # ── UI construction ────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)

        self._load_btn = QPushButton("Load file")
        self._load_btn.clicked.connect(self._on_load_csv)
        tb.addWidget(self._load_btn)

        self._file_label = QLabel("No file loaded  (or drag & drop a CSV / Excel file here)")
        self._file_label.setObjectName("fileLabel")
        self._file_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(self._file_label)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(140)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        tb.addWidget(self._progress)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # ── Left pane: well plate ─────────────────────────────────────────
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 10, 6, 6)
        lv.setSpacing(6)

        well_title = QLabel("Well Selection")
        well_title.setObjectName("sectionTitle")
        lv.addWidget(well_title)

        self._plate = WellPlateWidget()
        self._plate.selectionChanged.connect(self._on_well_selection_changed)
        lv.addWidget(self._plate, stretch=1)

        self._plate_format_label = QLabel("")
        self._plate_format_label.setObjectName("plateFormatLabel")
        lv.addWidget(self._plate_format_label)

        well_btns = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._plate.selectAll)
        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.clicked.connect(self._plate.deselectAll)
        well_btns.addWidget(sel_all_btn)
        well_btns.addWidget(desel_all_btn)
        well_btns.addStretch()
        lv.addLayout(well_btns)

        # ── Right pane: column list ────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 10, 10, 6)
        rv.setSpacing(6)

        col_title = QLabel("Column Selection")
        col_title.setObjectName("sectionTitle")
        rv.addWidget(col_title)

        # SeriesName is always included — show it as a locked item
        sn_info = QLabel("  SeriesName  (always included)")
        sn_info.setObjectName("plateFormatLabel")
        rv.addWidget(sn_info)

        self._col_list = QListWidget()
        self._col_list.setAlternatingRowColors(True)
        self._col_list.itemChanged.connect(self._on_col_item_changed)
        rv.addWidget(self._col_list, stretch=1)

        col_btns = QHBoxLayout()
        col_sel_all = QPushButton("Select All")
        col_sel_all.clicked.connect(self._col_select_all)
        col_desel_all = QPushButton("Deselect All")
        col_desel_all.clicked.connect(self._col_deselect_all)
        col_btns.addWidget(col_sel_all)
        col_btns.addWidget(col_desel_all)
        col_btns.addStretch()
        rv.addLayout(col_btns)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 4)

        self.setCentralWidget(splitter)

    def _build_bottom_bar(self) -> None:
        # Use a bottom QToolBar as the container — it keeps proper ownership
        # of its child widgets and never deletes them unexpectedly.
        bottom_tb = QToolBar("BottomBar", self)
        bottom_tb.setMovable(False)
        bottom_tb.setFloatable(False)
        bottom_tb.setStyleSheet("""
            QToolBar {
                background-color: #1e293b;
                border-top: 1px solid #334155;
                padding: 0;
                spacing: 0;
            }
        """)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bottom_tb)

        # Inner container widget — parent is the toolbar so Qt owns it
        self._bottom_bar = QWidget(bottom_tb)
        self._bottom_bar.setStyleSheet(
            "background-color: #1e293b;"
        )
        h = QHBoxLayout(self._bottom_bar)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._on_browse_folder)
        h.addWidget(browse_btn)

        folder_lbl = QLabel("Output folder:")
        folder_lbl.setStyleSheet("color: #94a3b8;")
        h.addWidget(folder_lbl)

        self._folder_label = QLabel(self._output_folder)  # pre-filled from settings
        self._folder_label.setObjectName("outputFolderLabel")
        self._folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        h.addWidget(self._folder_label, stretch=1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #334155;")
        h.addWidget(sep1)

        sample_lbl = QLabel("Row sampling:")
        sample_lbl.setStyleSheet("color: #94a3b8;")
        h.addWidget(sample_lbl)

        self._row_pct_spin = QSpinBox()
        self._row_pct_spin.setRange(1, 100)
        self._row_pct_spin.setValue(100)
        self._row_pct_spin.setSuffix(" %")
        self._row_pct_spin.setFixedWidth(94)
        self._row_pct_spin.setEnabled(False)
        self._row_pct_spin.setToolTip(
            "Percentage of rows to keep.\n"
            "10 % → keeps every 10th row (evenly distributed)."
        )        # Apply arrow-button stylesheet with resolved SVG paths
        _res = Path(__file__).parent / "resources"
        _up  = (_res / "arrow_up.svg").as_posix()
        _dn  = (_res / "arrow_dn.svg").as_posix()
        self._row_pct_spin.setStyleSheet(f"""
            QSpinBox {{
                padding-right: 20px;
            }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
                border-left: 1px solid #475569;
                background: #334155;
                border-top-right-radius: 4px;
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
                border-left: 1px solid #475569;
                background: #334155;
                border-bottom-right-radius: 4px;
            }}
            QSpinBox::up-button:hover   {{ background: #0ea5e9; }}
            QSpinBox::down-button:hover {{ background: #0ea5e9; }}
            QSpinBox::up-arrow   {{ image: url({_up}); width: 8px; height: 5px; }}
            QSpinBox::down-arrow {{ image: url({_dn}); width: 8px; height: 5px; }}
        """)
        h.addWidget(self._row_pct_spin)
        self._row_pct_spin.valueChanged.connect(self._update_status_counts)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #334155;")
        h.addWidget(sep2)

        split_lbl = QLabel("Split by:")
        split_lbl.setStyleSheet("color: #94a3b8;")
        h.addWidget(split_lbl)

        self._split_col_combo = QComboBox()
        self._split_col_combo.addItem("(none)")
        self._split_col_combo.setEnabled(False)
        self._split_col_combo.setMinimumWidth(140)
        self._split_col_combo.setToolTip(
            "Choose a numeric column to split the export into two files:\n"
            "  • below_or_equal — rows where value ≤ threshold\n"
            "  • above — rows where value > threshold"
        )
        self._split_col_combo.currentIndexChanged.connect(self._on_split_col_changed)
        h.addWidget(self._split_col_combo)

        threshold_lbl = QLabel("≤")
        threshold_lbl.setStyleSheet("color: #94a3b8;")
        h.addWidget(threshold_lbl)

        self._split_threshold = QDoubleSpinBox()
        self._split_threshold.setRange(-1e9, 1e9)
        self._split_threshold.setDecimals(3)
        self._split_threshold.setSingleStep(1.0)
        self._split_threshold.setValue(0.0)
        self._split_threshold.setFixedWidth(110)
        self._split_threshold.setEnabled(False)
        self._split_threshold.setToolTip("Threshold value — rows ≤ this go to file 1, rows > this go to file 2.")
        h.addWidget(self._split_threshold)
        self._split_threshold.valueChanged.connect(self._update_status_counts)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet("color: #334155;")
        h.addWidget(sep3)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setObjectName("exportBtn")
        self._export_btn.setFixedWidth(120)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        h.addWidget(self._export_btn)

        bottom_tb.addWidget(self._bottom_bar)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_rows   = QLabel("Rows: —")
        self._status_wells  = QLabel("Wells selected: 0")
        self._status_cols   = QLabel("Columns selected: 0")
        self._status_output = QLabel("")
        for lbl in (self._status_rows, self._status_wells, self._status_cols, self._status_output):
            lbl.setStyleSheet("color: #94a3b8; padding: 0 10px;")
            sb.addWidget(lbl)

    # ══════════════════════════════════════════════════════════════════════
    # Slots
    # ══════════════════════════════════════════════════════════════════════

    def _on_load_csv(self) -> None:
        start_dir = str(Path(self._last_csv_path).parent) \
            if Path(self._last_csv_path).exists() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open data file",
            start_dir,
            "All supported (*.csv *.tsv *.txt *.xls *.xlsx);;CSV files (*.csv);;Tab-separated (*.tsv *.txt);;Excel files (*.xls *.xlsx);;All files (*)",
        )
        if not path:
            return
        self._start_load(path)

    def _start_load(self, path: str) -> None:
        """Common entry point for file-dialog and drag-and-drop loads."""
        self._last_csv_path = path
        self._settings.setValue("last_csv_path", path)

        self._load_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._file_label.setText(Path(path).name)

        self._load_worker = LoadWorker(path, self)
        self._load_worker.progress.connect(self._progress.setValue)
        self._load_worker.loaded.connect(self._on_csv_loaded)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.start()

    def _on_csv_loaded(self, df: pd.DataFrame, wells: list, columns: list, col_descriptions: dict) -> None:
        self._df = df

        # Update plate widget
        self._plate.setAvailableWells(set(wells))
        self._plate_format_label.setText(
            f"{self._plate.plateLabel()}  ·  {len(wells)} well(s) found"
        )

        # Populate column list (block signals to avoid spurious updates)
        self._col_list.blockSignals(True)
        self._col_list.clear()
        # Restore saved selection when the file has the same columns as last time
        saved_source = self._settings.value("column_selection_source_cols", [])
        saved_checked = self._settings.value("column_selection_checked", [])
        if not isinstance(saved_source, list):
            saved_source = list(saved_source) if saved_source else []
        if not isinstance(saved_checked, list):
            saved_checked = list(saved_checked) if saved_checked else []
        columns_match = sorted(saved_source) == sorted(columns)
        checked_set: Set[str] = set(saved_checked) if columns_match else set(columns)
        for col in columns:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if col in checked_set else Qt.CheckState.Unchecked
            )
            desc = col_descriptions.get(col, '')
            if desc:
                item.setToolTip(desc)
            self._col_list.addItem(item)
        self._col_list.blockSignals(False)

        self._status_rows.setText(f"Rows: {len(df):,}")
        self._update_status_counts()

        # Disable row sampling when there is at most 1 row per well
        max_rows_per_well = df.groupby("SeriesName").size().max() if len(df) else 0
        single_row = max_rows_per_well <= 1
        self._row_pct_spin.setEnabled(not single_row)
        self._row_pct_spin.setToolTip(
            "Disabled: only one row per well in this data."
            if single_row else
            "Percentage of rows to keep.\n10 % → keeps every 10th row (evenly distributed)."
        )

        # Populate split-by combo with numeric columns
        numeric_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
        self._split_col_combo.blockSignals(True)
        self._split_col_combo.clear()
        self._split_col_combo.addItem("(none)")
        for c in numeric_cols:
            self._split_col_combo.addItem(c)
        self._split_col_combo.setCurrentIndex(0)
        self._split_col_combo.blockSignals(False)
        self._split_col_combo.setEnabled(True)
        self._split_threshold.setEnabled(False)

    def _on_load_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Load Error", msg)

    def _on_load_finished(self) -> None:
        self._load_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._update_export_button()

    def _on_well_selection_changed(self, selected: frozenset) -> None:
        self._update_status_counts()
        self._update_export_button()

    def _on_col_item_changed(self, item: QListWidgetItem) -> None:
        self._update_status_counts()
        self._update_export_button()
        self._save_column_selection()

    def _col_select_all(self) -> None:
        self._col_list.blockSignals(True)
        for i in range(self._col_list.count()):
            self._col_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._col_list.blockSignals(False)
        self._update_status_counts()
        self._update_export_button()
        self._save_column_selection()

    def _col_deselect_all(self) -> None:
        self._col_list.blockSignals(True)
        for i in range(self._col_list.count()):
            self._col_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._col_list.blockSignals(False)
        self._update_status_counts()
        self._update_export_button()
        self._save_column_selection()

    def _on_browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", self._output_folder
        )
        if folder:
            self._output_folder = folder
            self._folder_label.setText(folder)
            self._settings.setValue("output_folder", folder)

    def _on_export(self) -> None:
        if self._df is None:
            return

        wells   = self._plate.selectedWells()
        columns = self._selected_columns()

        if not wells:
            QMessageBox.warning(self, "No wells selected", "Please select at least one well.")
            return
        if not columns:
            QMessageBox.warning(self, "No columns selected", "Please select at least one column.")
            return

        # Build base filename part from selected wells
        well_list = sorted(wells, key=lambda w: (w[0], int(w[1:]) if w[1:].isdigit() else 0))
        if len(well_list) <= 4:
            name_part = "-".join(well_list)
        else:
            name_part = f"{well_list[0]}-{well_list[-1]}"

        split_col = self._split_col_combo.currentText()

        if split_col == "(none)" or not split_col:
            # ── Single-file export (original behaviour) ────────────────
            out_path = str(Path(self._output_folder) / f"{name_part}-filtered.csv")
            self._export_btn.setEnabled(False)
            self._export_worker = ExportWorker(
                self._df, wells, columns, out_path,
                row_pct=self._row_pct_spin.value(), parent=self
            )
            self._export_worker.done.connect(self._on_export_done)
            self._export_worker.error.connect(self._on_export_error)
            self._export_worker.finished.connect(lambda: self._update_export_button())
            self._export_worker.start()
        else:
            # ── Split export ───────────────────────────────────────────
            threshold  = self._split_threshold.value()
            safe_col   = re.sub(r"[^\w.-]", "_", split_col)
            thr_str    = f"{threshold:g}"          # compact numeric string, e.g. "0" or "2.5"
            out_low  = str(Path(self._output_folder) /
                           f"{name_part}-below_or_equal_{safe_col}_{thr_str}.csv")
            out_high = str(Path(self._output_folder) /
                           f"{name_part}-above_{safe_col}_{thr_str}.csv")

            # Pre-filter the full DataFrame by the threshold column
            mask_low  = self._df[split_col] <= threshold
            mask_high = self._df[split_col] >  threshold
            df_low  = self._df[mask_low]
            df_high = self._df[mask_high]

            has_low  = not df_low.empty
            has_high = not df_high.empty

            if not has_low and not has_high:
                QMessageBox.warning(self, "Split export",
                                    "No rows match either group. Nothing exported.")
                return

            if not has_low:
                QMessageBox.information(
                    self, "Split export",
                    f"No rows with '{split_col}' ≤ {threshold}.\n"
                    "Only the 'above' file will be written."
                )
            if not has_high:
                QMessageBox.information(
                    self, "Split export",
                    f"No rows with '{split_col}' > {threshold}.\n"
                    "Only the 'below or equal' file will be written."
                )

            self._export_btn.setEnabled(False)
            row_pct = self._row_pct_spin.value()

            # Keep references so Qt doesn't garbage-collect the workers
            self._export_worker        = None
            self._export_worker_split2 = None

            if has_low and has_high:
                # Start worker1 (low); on finish, start worker2 (high)
                self._export_worker = ExportWorker(
                    df_low, wells, columns, out_low, row_pct=row_pct, parent=self
                )
                self._export_worker.error.connect(self._on_export_error)

                def _start_second(path1: str) -> None:
                    self._on_export_done(path1)
                    self._export_worker_split2 = ExportWorker(
                        df_high, wells, columns, out_high, row_pct=row_pct, parent=self
                    )
                    self._export_worker_split2.done.connect(self._on_export_done)
                    self._export_worker_split2.error.connect(self._on_export_error)
                    self._export_worker_split2.finished.connect(
                        lambda: self._update_export_button()
                    )
                    self._export_worker_split2.start()

                self._export_worker.done.connect(_start_second)
                self._export_worker.start()

            elif has_low:
                self._export_worker = ExportWorker(
                    df_low, wells, columns, out_low, row_pct=row_pct, parent=self
                )
                self._export_worker.done.connect(self._on_export_done)
                self._export_worker.error.connect(self._on_export_error)
                self._export_worker.finished.connect(lambda: self._update_export_button())
                self._export_worker.start()

            else:  # has_high only
                self._export_worker = ExportWorker(
                    df_high, wells, columns, out_high, row_pct=row_pct, parent=self
                )
                self._export_worker.done.connect(self._on_export_done)
                self._export_worker.error.connect(self._on_export_error)
                self._export_worker.finished.connect(lambda: self._update_export_button())
                self._export_worker.start()

    def _on_export_done(self, path: str) -> None:
        QMessageBox.information(
            self,
            "Export complete",
            f"Saved to:\n{path}",
        )

    def _on_export_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Export Error", msg)

    # ══════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════

    def _on_split_col_changed(self, index: int) -> None:
        """Enable/disable the threshold spinbox based on combo selection."""
        self._split_threshold.setEnabled(index > 0)
        self._update_status_counts()

    def _save_column_selection(self) -> None:
        """Persist the current column list and checked state to QSettings."""
        all_cols = [self._col_list.item(i).text() for i in range(self._col_list.count())]
        checked  = [self._col_list.item(i).text() for i in range(self._col_list.count())
                    if self._col_list.item(i).checkState() == Qt.CheckState.Checked]
        self._settings.setValue("column_selection_source_cols", all_cols)
        self._settings.setValue("column_selection_checked", checked)

    def _selected_columns(self) -> List[str]:
        cols = []
        for i in range(self._col_list.count()):
            item = self._col_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cols.append(item.text())
        return cols

    def _update_export_button(self) -> None:
        ready = (
            self._df is not None
            and len(self._plate.selectedWells()) > 0
            and len(self._selected_columns()) > 0
        )
        self._export_btn.setEnabled(ready)

    def _update_status_counts(self) -> None:
        n_wells = len(self._plate.selectedWells())
        n_cols  = len(self._selected_columns())
        self._status_wells.setText(f"Wells selected: {n_wells}")
        self._status_cols.setText(f"Columns selected: {n_cols}")

        if self._df is None or n_wells == 0:
            self._status_output.setText("")
            return

        wells     = self._plate.selectedWells()
        row_pct   = self._row_pct_spin.value()
        step      = max(1, round(100 / row_pct)) if row_pct < 100 else 1
        approx    = "~" if step > 1 else ""
        well_mask = self._df["SeriesName"].isin(wells)
        well_rows = int(well_mask.sum())
        split_col = self._split_col_combo.currentText()

        if split_col == "(none)" or not split_col:
            if step == 1:
                self._status_output.setText("")
            else:
                sampled = math.ceil(well_rows / step)
                self._status_output.setText(f"Output: {approx}{sampled:,} rows")
        else:
            thr       = self._split_threshold.value()
            col_vals  = self._df.loc[well_mask, split_col]
            low_rows  = int((col_vals <= thr).sum())
            high_rows = int((col_vals >  thr).sum())
            low_s     = math.ceil(low_rows  / step)
            high_s    = math.ceil(high_rows / step)
            self._status_output.setText(
                f"Output:  ≤{thr:g}: {approx}{low_s:,}  |  >{thr:g}: {approx}{high_s:,}"
            )
