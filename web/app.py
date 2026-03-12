"""
app.py — CITableCleaner Python data layer for Pyodide.

Exposes three module-level functions that worker.js calls via pyodide.globals:
  load_file(path, ext)                              -> dict
  export_data(wells, columns, row_pct,              -> list[dict]
              split_col, threshold)
  get_col_range(col_name)                           -> dict  (min/max for threshold hint)

The loaded DataFrame is kept in _df so it survives between calls inside the
same Pyodide instance (one file at a time).
"""

from __future__ import annotations

import csv
import io
import re as _re
from typing import Any

import pandas as pd

# ── Module-level state ─────────────────────────────────────────────────────
_df: pd.DataFrame | None = None
_WELL_COLUMN = "SeriesName"


# ── Helpers ────────────────────────────────────────────────────────────────

def _sniff_separator(path: str) -> str:
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _sort_well_key(w: str):
    return (w[0], int(w[1:]) if w[1:].isdigit() else 0)


def _safe_col(name: str) -> str:
    return _re.sub(r"[^\w.-]", "_", name)


def _build_filtered(df: pd.DataFrame, wells: list, columns: list, row_pct: int) -> pd.DataFrame:
    mask = df[_WELL_COLUMN].isin(set(wells))
    filtered = df.loc[mask]
    if row_pct < 100:
        step = max(1, round(100 / row_pct))
        filtered = filtered.iloc[::step]
    cols = [_WELL_COLUMN] + [c for c in columns if c in filtered.columns]
    seen: set = set()
    final_cols = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            final_cols.append(c)
    return filtered[final_cols]


# ── Public API ─────────────────────────────────────────────────────────────

def load_file(path: str, ext: str) -> dict[str, Any]:
    """
    Parse the file at *path* and return a summary dict.
    Keeps the DataFrame in the module-level _df for later export calls.
    Raises RuntimeError on any problem so worker.js can catch it.
    """
    global _df

    ext = ext.lower()
    if ext in (".xls", ".xlsx"):
        df = pd.read_excel(path, sheet_name=0)
    else:
        sep = _sniff_separator(path)
        df = pd.read_csv(path, sep=sep, low_memory=False)

    if _WELL_COLUMN not in df.columns:
        raise RuntimeError(
            f"Column '{_WELL_COLUMN}' not found in the file. "
            f"Available columns: {', '.join(str(c) for c in df.columns[:10])}"
        )

    wells = sorted(
        df[_WELL_COLUMN].dropna().unique().tolist(),
        key=_sort_well_key,
    )
    columns = [c for c in df.columns if c != _WELL_COLUMN]
    numeric_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
    single_row_per_well = int(df.groupby(_WELL_COLUMN).size().max()) <= 1 if len(df) else True

    _df = df

    return {
        "wells": wells,
        "columns": columns,
        "numeric_cols": numeric_cols,
        "row_count": len(df),
        "single_row_per_well": single_row_per_well,
    }


def export_data(
    wells: list,
    columns: list,
    row_pct: int = 100,
    split_col: str = "",
    threshold: float = 0.0,
) -> list[dict[str, str]]:
    """
    Filter _df and return a list of {filename, csv_text} dicts.
    One dict  → no split.
    Two dicts → split by split_col <= threshold / > threshold.
    """
    if _df is None:
        raise RuntimeError("No file loaded. Call load_file() first.")

    row_pct = max(1, min(100, int(row_pct)))

    if not split_col or split_col == "(none)":
        out = _build_filtered(_df, wells, columns, row_pct)
        return [{"filename": "filtered.csv", "csv_text": out.to_csv(index=False)}]

    # ── Split export ──────────────────────────────────────────────────
    thr       = float(threshold)
    safe      = _safe_col(split_col)
    thr_str   = f"{thr:g}"
    mask_low  = _df[split_col] <= thr
    mask_high = _df[split_col] >  thr

    results = []
    for mask, suffix in (
        (mask_low,  f"below_or_equal_{safe}_{thr_str}.csv"),
        (mask_high, f"above_{safe}_{thr_str}.csv"),
    ):
        subset = _df[mask]
        if subset.empty:
            continue
        out = _build_filtered(subset, wells, columns, row_pct)
        results.append({"filename": suffix, "csv_text": out.to_csv(index=False)})

    return results


def get_col_range(col_name: str) -> dict[str, float]:
    """Return {min, max} for a numeric column (used to hint the threshold input)."""
    if _df is None or col_name not in _df.columns:
        return {"min": 0.0, "max": 0.0}
    col = _df[col_name].dropna()
    return {"min": float(col.min()), "max": float(col.max())}


def get_row_stats(
    wells: list,
    row_pct: int,
    split_col: str,
    threshold: float,
) -> dict[str, Any]:
    """
    Return estimated output row counts without performing the actual export.
    Result keys: step, sampled (total after sampling), and optionally low / high
    when split_col is active.
    """
    import math as _math

    if _df is None:
        return {}

    row_pct = max(1, min(100, int(row_pct)))
    mask      = _df[_WELL_COLUMN].isin(set(wells))
    well_rows = int(mask.sum())
    step      = max(1, round(100 / row_pct))
    sampled   = _math.ceil(well_rows / step)

    result: dict[str, Any] = {"step": step, "sampled": sampled}

    if split_col and split_col != "(none)" and split_col in _df.columns:
        col_vals  = _df.loc[mask, split_col]
        low_rows  = int((col_vals <= float(threshold)).sum())
        high_rows = int((col_vals >  float(threshold)).sum())
        result["low"]  = _math.ceil(low_rows  / step)
        result["high"] = _math.ceil(high_rows / step)

    return result
