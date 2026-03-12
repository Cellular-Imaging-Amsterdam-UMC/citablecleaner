"""
worker.py — Background QThread workers for CSV load and export.

LoadWorker   — reads a CSV file with pandas and emits parsed data.
ExportWorker — filters a DataFrame and writes the output CSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Set

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal


class LoadWorker(QThread):
    """
    Read a CSV file on a background thread.

    Signals
    -------
    loaded(df, wells, columns)
        df      : pandas DataFrame (full file)
        wells   : sorted list of unique SeriesName values
        columns : list of column names (excluding SeriesName which is always first)
    progress(int)
        0-100 progress indication (emitted at start and end only for large files)
    error(str)
        Human-readable error message if loading failed.
    """

    loaded   = pyqtSignal(object, list, list)   # (DataFrame, wells, columns)
    progress = pyqtSignal(int)
    error    = pyqtSignal(str)

    WELL_COLUMN = "SeriesName"

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    @staticmethod
    def _sniff_separator(path: str) -> str:
        """Read the first line and return the most likely delimiter."""
        import csv
        with open(path, newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            return dialect.delimiter
        except csv.Error:
            return ","  # fall back to comma

    def run(self) -> None:
        try:
            self.progress.emit(0)
            ext = Path(self._path).suffix.lower()
            if ext in (".xls", ".xlsx"):
                df = pd.read_excel(self._path, sheet_name=0)
            else:
                sep = self._sniff_separator(self._path)
                df = pd.read_csv(self._path, sep=sep)
            self.progress.emit(80)

            if self.WELL_COLUMN not in df.columns:
                self.error.emit(
                    f"Column '{self.WELL_COLUMN}' not found in the file.\n"
                    f"Available columns: {', '.join(df.columns[:10])}"
                )
                return

            wells   = sorted(df[self.WELL_COLUMN].dropna().unique().tolist(),
                             key=lambda w: (w[0], int(w[1:]) if w[1:].isdigit() else 0))
            columns = [c for c in df.columns if c != self.WELL_COLUMN]

            self.progress.emit(100)
            self.loaded.emit(df, wells, columns)

        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Failed to load file:\n{exc}")


class ExportWorker(QThread):
    """
    Filter df by wells + columns and write to a CSV file.

    Signals
    -------
    done(path)  — export succeeded, path is the output file path.
    error(str)  — export failed with this message.
    """

    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    WELL_COLUMN = "SeriesName"

    def __init__(
        self,
        df: pd.DataFrame,
        wells: Set[str],
        columns: List[str],
        output_path: str,
        row_pct: int = 100,
        parent=None,
    ):
        super().__init__(parent)
        self._df          = df
        self._wells       = set(wells)
        self._columns     = list(columns)
        self._output_path = output_path
        self._row_pct     = max(1, min(100, row_pct))

    def run(self) -> None:
        try:
            # Filter rows by well
            mask = self._df[self.WELL_COLUMN].isin(self._wells)
            filtered = self._df.loc[mask]

            # Row sampling: keep every Nth row so rows are evenly distributed
            if self._row_pct < 100:
                step = max(1, round(100 / self._row_pct))
                filtered = filtered.iloc[::step]

            # Build column list: SeriesName always first, then user selection
            cols = [self.WELL_COLUMN] + [
                c for c in self._columns if c in filtered.columns
            ]
            # Deduplicate while preserving order
            seen: set = set()
            final_cols = []
            for c in cols:
                if c not in seen:
                    seen.add(c)
                    final_cols.append(c)

            out = filtered[final_cols]
            out.to_csv(self._output_path, index=False)
            self.done.emit(self._output_path)

        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Export failed:\n{exc}")
