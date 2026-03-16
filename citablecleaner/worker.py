"""
worker.py — Background QThread workers for CSV load and export.

LoadWorker   — reads a CSV file with pandas and emits parsed data.
ExportWorker — filters a DataFrame and writes the output CSV.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Set

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

# Well-ID pattern: one letter followed by 1-3 digits, e.g. A01, H12, P024
_WELL_RE = re.compile(r'^[A-Pa-p]\d{1,3}$')

# Preferred column names to probe, in priority order
_WELL_COLUMN_CANDIDATES = (
    "SeriesName", "Well", "WellName", "WellID", "Well_ID",
    "Position", "Sample", "Series",
)


def _detect_well_column(df: pd.DataFrame) -> str | None:
    """Return the name of the column that contains well identifiers, or None."""
    # 1. Try known names (case-sensitive first, then case-insensitive)
    cols_lower = {c.lower(): c for c in df.columns}
    for candidate in _WELL_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate
        if candidate.lower() in cols_lower:
            return cols_lower[candidate.lower()]
    # 2. Fall back: any string column whose values look like well IDs
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().head(20).astype(str)
            if len(sample) > 0 and sample.map(lambda v: bool(_WELL_RE.match(v))).mean() >= 0.8:
                return col
    return None


_HEADER_CSVS = [
    Path(__file__).parent / 'cellstableheaders.csv',
    Path(__file__).parent / 'wellstableheaders.csv',
]


def _load_col_descriptions(columns: list) -> dict:
    """
    Return {column: description} for every column in *columns*.
    Tries each header CSV in turn; uses the first where every data column
    appears in the CSV (the CSV may list extra optional columns).
    Columns not listed in the matched CSV get ''.
    Returns {} when no CSV matches.
    """
    import csv as _csv
    col_set = set(columns)
    for path in _HEADER_CSVS:
        try:
            with open(path, newline='', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                rows = list(reader)
            hdr_cols = {r['Column Name'] for r in rows}
            if col_set <= (hdr_cols - {'SeriesName'}):
                desc = {r['Column Name']: r['Description'] for r in rows}
                return {c: desc.get(c, '') for c in columns}
        except (OSError, KeyError):
            continue
    return {}


class LoadWorker(QThread):
    """
    Read a CSV file on a background thread.

    Signals
    -------
    loaded(df, wells, columns)
        df      : pandas DataFrame (full file)
        wells   : sorted list of unique well-ID values
        columns : list of column names (excluding the well column)
    progress(int)
        0-100 progress indication (emitted at start and end only for large files)
    error(str)
        Human-readable error message if loading failed.
    """

    loaded   = pyqtSignal(object, list, list, dict)   # (DataFrame, wells, columns, col_descriptions)
    progress = pyqtSignal(int)
    error    = pyqtSignal(str)

    WELL_COLUMN = "SeriesName"  # kept for ExportWorker compatibility; overridden at load time

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
            pass
        # Sniffer failed — count each candidate in the first line and pick the winner
        first_line = sample.split("\n")[0] if "\n" in sample else sample
        counts = {d: first_line.count(d) for d in (",", "\t", ";", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","

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

            well_col = _detect_well_column(df)
            if well_col is None:
                self.error.emit(
                    f"Could not find a well-identifier column in the file.\n"
                    f"Tried: {', '.join(_WELL_COLUMN_CANDIDATES)}\n"
                    f"Available columns: {', '.join(str(c) for c in df.columns[:10])}"
                )
                return

            # Rename to SeriesName so the rest of the app works unchanged
            if well_col != self.WELL_COLUMN:
                df = df.rename(columns={well_col: self.WELL_COLUMN})

            wells   = sorted(df[self.WELL_COLUMN].dropna().unique().tolist(),
                             key=lambda w: (w[0], int(w[1:]) if w[1:].isdigit() else 0))
            columns = [c for c in df.columns if c != self.WELL_COLUMN]

            col_descriptions = _load_col_descriptions(columns)
            self.progress.emit(100)
            self.loaded.emit(df, wells, columns, col_descriptions)

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
