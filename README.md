# CITableCleaner

A desktop tool for filtering and exporting cell imaging measurement tables exported by CI Analyze 5+.

Load a CSV/Excel results file, select which wells and measurement columns to keep, and export a clean CSV — one file per selection. Column choices are remembered between sessions when the same file format is reloaded.

## Download

Download the latest `CITableCleaner.zip` from the [Releases](../../releases) page, unzip, and run `CITableCleaner.exe`. No installation required.

## Run from source

```
pip install -r requirements.txt
python -m citablecleaner
```

Requires Python 3.10+ and PyQt6.
