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


def _load_col_descriptions(columns: list) -> tuple:
    """
    Return ({column: description}, matched_csv_name | None) for every column in *columns*.
    Tries each header CSV in turn; uses the first where every data column
    appears in the CSV (the CSV may list extra optional columns).
    Columns not listed in the matched CSV get ''.
    Returns ({}, None) when no CSV matches.
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
                return {c: desc.get(c, '') for c in columns}, path.name
        except (OSError, KeyError):
            continue
    return {}, None


def load_wells_col_descriptions() -> dict:
    """Return {column: description} for all wells-table columns (no match needed)."""
    import csv as _csv
    path = Path(__file__).parent / 'wellstableheaders.csv'
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            rows = list(_csv.DictReader(f))
        return {r['Column Name']: r['Description'] for r in rows}
    except (OSError, KeyError):
        return {}


# ── Wells aggregation specs ────────────────────────────────────────────────
# Each tuple: (wells_col, requires, kind, src_col, agg_fn)
#   wells_col : output column name in the aggregated wells table
#   requires  : tuple of cells-table column names needed to compute this column
#   kind      : 'count'|'agg'|'tile'|'pct_pos'|'first'|'avg_granules'|'corrected_bg'
#   src_col   : source cells column (used by 'agg', 'pct_pos', 'first')
#   agg_fn    : pandas agg string ('mean','std','median','min') used by 'agg'/'tile'

_WELLS_AGG_SPECS: list = [
    ("NumCells",                                  (),                                             "count",        None,                                     None),
    ("Tiles_MeanNumCells",                        ("Tile",),                                      "tile",         None,                                     "mean"),
    ("Tiles_StdNumCells",                         ("Tile",),                                      "tile",         None,                                     "std"),
    ("Tiles_MedianNumCells",                      ("Tile",),                                      "tile",         None,                                     "median"),
    ("PercentageCellsWithGranules",               ("CellNumGranules",),                           "pct_pos",      "CellNumGranules",                        None),
    ("MeanCellNumberGranules",                    ("CellNumGranules",),                           "agg",          "CellNumGranules",                        "mean"),
    ("StdCellNumberGranules",                     ("CellNumGranules",),                           "agg",          "CellNumGranules",                        "std"),
    ("MedianCellNumberGranules",                  ("CellNumGranules",),                           "agg",          "CellNumGranules",                        "median"),
    ("MeanNucleusNumberGranules",                 ("NucleusNumGranules",),                        "agg",          "NucleusNumGranules",                     "mean"),
    ("StdNucleusNumberGranules",                  ("NucleusNumGranules",),                        "agg",          "NucleusNumGranules",                     "std"),
    ("MedianNucleusNumberGranules",               ("NucleusNumGranules",),                        "agg",          "NucleusNumGranules",                     "median"),
    ("MeanCytoplasmNumberGranules",               ("CytoplasmNumGranules",),                      "agg",          "CytoplasmNumGranules",                   "mean"),
    ("StdCytoplasmNumberGranules",                ("CytoplasmNumGranules",),                      "agg",          "CytoplasmNumGranules",                   "std"),
    ("MedianCytoplasmNumberGranules",             ("CytoplasmNumGranules",),                      "agg",          "CytoplasmNumGranules",                   "median"),
    ("MeanCellArea",                              ("CellArea",),                                  "agg",          "CellArea",                               "mean"),
    ("StdCellArea",                               ("CellArea",),                                  "agg",          "CellArea",                               "std"),
    ("MeanCytoplasmArea",                         ("CytoplasmArea",),                             "agg",          "CytoplasmArea",                          "mean"),
    ("StdCytoplasmArea",                          ("CytoplasmArea",),                             "agg",          "CytoplasmArea",                          "std"),
    ("MeanNucleusArea",                           ("NucleusArea",),                               "agg",          "NucleusArea",                            "mean"),
    ("StdNucleusArea",                            ("NucleusArea",),                               "agg",          "NucleusArea",                            "std"),
    ("MeanNucleusIntensity",                      ("NucleusMeanIntensity",),                      "agg",          "NucleusMeanIntensity",                   "mean"),
    ("StdNucleusIntensity",                       ("NucleusMeanIntensity",),                      "agg",          "NucleusMeanIntensity",                   "std"),
    ("MeanNucleusTotalIntensity",                 ("NucleusTotalIntensity",),                     "agg",          "NucleusTotalIntensity",                  "mean"),
    ("StdNucleusTotalIntensity",                  ("NucleusTotalIntensity",),                     "agg",          "NucleusTotalIntensity",                  "std"),
    ("MeanCellIntensityGranules",                 ("CellMeanIntensityGranules",),                 "agg",          "CellMeanIntensityGranules",              "mean"),
    ("StdCellIntensityGranules",                  ("CellMeanIntensityGranules",),                 "agg",          "CellMeanIntensityGranules",              "std"),
    ("MeanNucleusIntensityGranules",              ("NucleusMeanIntensityGranules",),              "agg",          "NucleusMeanIntensityGranules",           "mean"),
    ("StdNucleusIntensityGranules",               ("NucleusMeanIntensityGranules",),              "agg",          "NucleusMeanIntensityGranules",           "std"),
    ("MeanCytoplasmIntensityGranules",            ("CytoplasmMeanIntensityGranules",),            "agg",          "CytoplasmMeanIntensityGranules",         "mean"),
    ("StdCytoplasmIntensityGranules",             ("CytoplasmMeanIntensityGranules",),            "agg",          "CytoplasmMeanIntensityGranules",         "std"),
    ("MeanCellGranulesChannelIntensity",          ("CellGranulesChannelMeanIntensity",),          "agg",          "CellGranulesChannelMeanIntensity",       "mean"),
    ("MeanCellGranulesChannelTotalIntensity",     ("CellGranulesChannelTotalIntensity",),         "agg",          "CellGranulesChannelTotalIntensity",      "mean"),
    ("MeanCytoplasmGranulesChannelIntensity",     ("CytoplasmGranulesChannelMeanIntensity",),     "agg",          "CytoplasmGranulesChannelMeanIntensity",  "mean"),
    ("MeanCytoplasmGranulesChannelTotalIntensity",("CytoplasmGranulesChannelTotalIntensity",),    "agg",          "CytoplasmGranulesChannelTotalIntensity", "mean"),
    ("MeanNucleusGranulesChannelIntensity",       ("NucleusGranulesChannelMeanIntensity",),       "agg",          "NucleusGranulesChannelMeanIntensity",    "mean"),
    ("MeanNucleusGranulesChannelTotalIntensity",  ("NucleusGranulesChannelTotalIntensity",),      "agg",          "NucleusGranulesChannelTotalIntensity",   "mean"),
    ("MedianCellGranulesChannelIntensity",        ("CellGranulesChannelMeanIntensity",),          "agg",          "CellGranulesChannelMeanIntensity",       "median"),
    ("MedianCytoplasmGranulesChannelIntensity",   ("CytoplasmGranulesChannelMeanIntensity",),     "agg",          "CytoplasmGranulesChannelMeanIntensity",  "median"),
    ("MedianNucleusGranulesChannelIntensity",     ("NucleusGranulesChannelMeanIntensity",),       "agg",          "NucleusGranulesChannelMeanIntensity",    "median"),
    ("MinimumCellGranulesChannelIntensity",       ("CellGranulesChannelMeanIntensity",),          "agg",          "CellGranulesChannelMeanIntensity",       "min"),
    ("MinimumCytoplasmGranulesChannelIntensity",  ("CytoplasmGranulesChannelMeanIntensity",),     "agg",          "CytoplasmGranulesChannelMeanIntensity",  "min"),
    ("MinimumNucleusGranulesChannelIntensity",    ("NucleusGranulesChannelMeanIntensity",),       "agg",          "NucleusGranulesChannelMeanIntensity",    "min"),
    ("MeanCellGranulesChannelIntensityCorrected", ("CellGranulesChannelMeanIntensity",),          "corrected_bg", None,                                     None),
    ("AvgNumGranulesCells",                       ("CellNumGranules",),                           "avg_granules", None,                                     None),
    ("ImageNumber",                               ("ImageNumber",),                               "first",        "ImageNumber",                            None),
    ("ParentsName",                               ("ParentsName",),                               "first",        "ParentsName",                            None),
]


def available_wells_columns(cells_cols: list) -> list:
    """Return the wells-table column names that can be computed from cells_cols."""
    cells_set = set(cells_cols)
    return [
        spec[0]
        for spec in _WELLS_AGG_SPECS
        if all(r in cells_set for r in spec[1])
    ]


def aggregate_cells_to_wells(df: pd.DataFrame, wells_cols: list) -> pd.DataFrame:
    """
    Aggregate a cells-level DataFrame to one row per well.

    Parameters
    ----------
    df         : cells DataFrame already filtered to the desired wells / row sample
    wells_cols : wells-table column names to compute

    Returns
    -------
    DataFrame with SeriesName as the first column and one row per well.
    """
    WELL_COL  = "SeriesName"
    cells_set = set(df.columns)
    wells_set = set(wells_cols)

    # corrected_bg requires MeanCellGranulesChannelIntensity as an intermediate
    need_corrected  = "MeanCellGranulesChannelIntensityCorrected" in wells_set
    add_mean_ch_int = (
        need_corrected
        and "MeanCellGranulesChannelIntensity" not in wells_set
        and "CellGranulesChannelMeanIntensity" in cells_set
    )
    effective_set = set(wells_set)
    if add_mean_ch_int:
        effective_set.add("MeanCellGranulesChannelIntensity")

    grp = df.groupby(WELL_COL, sort=True)

    # Pre-compute per-tile cell counts once for all Tile_* columns
    tile_grp = None
    if "Tile" in cells_set and any(
        s[2] == "tile" and s[0] in effective_set for s in _WELLS_AGG_SPECS
    ):
        tile_grp = (
            df.groupby([WELL_COL, "Tile"], sort=False)
            .size()
            .reset_index(name="_n_per_tile")
            .groupby(WELL_COL)["_n_per_tile"]
        )

    result: dict = {}

    for (wells_col, requires, kind, src_col, agg_fn) in _WELLS_AGG_SPECS:
        if wells_col not in effective_set:
            continue
        if not all(r in cells_set for r in requires):
            continue

        if kind == "count":
            result[wells_col] = grp.size()

        elif kind == "agg":
            result[wells_col] = grp[src_col].agg(agg_fn)

        elif kind == "tile":
            if tile_grp is not None:
                result[wells_col] = tile_grp.agg(agg_fn)

        elif kind == "pct_pos":
            pos = (df[src_col] > 0).astype(float)
            result[wells_col] = 100.0 * df.assign(_pos=pos).groupby(WELL_COL)["_pos"].mean()

        elif kind == "first":
            result[wells_col] = grp[src_col].first()

        elif kind == "avg_granules":
            result[wells_col] = grp["CellNumGranules"].sum() / grp.size()

        elif kind == "corrected_bg":
            pass  # computed in post-step below

    if not result:
        wells_names = sorted(
            df[WELL_COL].dropna().unique().tolist(),
            key=lambda w: (w[0], int(w[1:]) if w[1:].isdigit() else 0),
        )
        return pd.DataFrame({WELL_COL: wells_names})

    out = pd.DataFrame(result)
    out.index.name = WELL_COL
    out = out.reset_index()

    # Post-step: background-corrected channel intensity
    if need_corrected and "MeanCellGranulesChannelIntensity" in out.columns:
        mn = out["MeanCellGranulesChannelIntensity"]
        out["MeanCellGranulesChannelIntensityCorrected"] = mn - mn.min()

    # Remove the internal helper column if it was not explicitly requested
    if add_mean_ch_int and "MeanCellGranulesChannelIntensity" in out.columns:
        out = out.drop(columns=["MeanCellGranulesChannelIntensity"])

    # Sort wells by letter then number
    sort_key = out[WELL_COL].apply(
        lambda w: (ord(w[0]) * 100000 + int(w[1:]))
        if isinstance(w, str) and len(w) > 1 and w[1:].isdigit()
        else 0
    )
    out = out.iloc[sort_key.argsort(kind="stable").values].reset_index(drop=True)

    # Return columns in canonical wells-spec order
    spec_ordered = [WELL_COL] + [
        s[0] for s in _WELLS_AGG_SPECS if s[0] in out.columns and s[0] in wells_set
    ]
    return out[[c for c in spec_ordered if c in out.columns]]


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

    loaded   = pyqtSignal(object, list, list, dict, str)   # (DataFrame, wells, columns, col_descriptions, table_type)
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

            col_descriptions, matched_csv = _load_col_descriptions(columns)
            table_type = (
                'cells' if matched_csv == 'cellstableheaders.csv' else
                'wells' if matched_csv == 'wellstableheaders.csv' else
                ''
            )
            self.progress.emit(100)
            self.loaded.emit(df, wells, columns, col_descriptions, table_type)

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
        aggregate_to_wells: bool = False,
        wells_columns: List[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._df                 = df
        self._wells              = set(wells)
        self._columns            = list(columns)
        self._output_path        = output_path
        self._row_pct            = max(1, min(100, row_pct))
        self._aggregate_to_wells = aggregate_to_wells
        self._wells_columns      = list(wells_columns) if wells_columns else []

    def run(self) -> None:
        try:
            # Filter rows by well
            mask = self._df[self.WELL_COLUMN].isin(self._wells)
            filtered = self._df.loc[mask]

            # Row sampling: keep every Nth row so rows are evenly distributed
            if self._row_pct < 100:
                step = max(1, round(100 / self._row_pct))
                filtered = filtered.iloc[::step]

            if self._aggregate_to_wells:
                out = aggregate_cells_to_wells(filtered, self._wells_columns)
            else:
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
