# CITableCleaner

A desktop tool for filtering and exporting cell imaging measurement tables exported by CI Analyze 5+.

Load a CSV/Excel results file, select which wells and measurement columns to keep, and export a clean CSV — one file per selection. Column choices are remembered between sessions when the same file format is reloaded.

## Download

Download the latest `CITableCleaner.zip` from the [Releases](../../releases) page, unzip, and run `CITableCleaner.exe`. No installation required.

## How it works

CITableCleaner is built around a three-step workflow:

1. **Load** — Open a CSV or Excel file exported by CI Analyze 5+. The file is parsed in a background thread so the UI stays responsive. The app auto-detects the plate format (e.g. 96-well, 384-well) from the well identifiers found in the data.

2. **Select** — The left panel shows an interactive well-plate grid. Click individual wells, or use *Select All* / *Deselect All* to choose which wells to include. The right panel lists every measurement column in the file; tick or untick columns the same way. Your column selections are saved per distinct set of column names and are restored automatically the next time you load a file with the same format.

3. **Export** — Choose an output folder and click *Export CSV*. One clean CSV is written for every selected well, containing only the chosen measurement columns. File names follow the pattern `<WellID>-cells.csv`.

A status bar at the bottom always shows the current row count, number of selected wells, and number of selected columns.

## Requirements

| Package | Minimum version | Purpose |
|---|---|---|
| Python | 3.10 | Runtime |
| PyQt6 | 6.6 | GUI framework |
| pandas | 2.0 | Table loading and filtering |
| openpyxl | 3.1 | Excel (`.xlsx`) file support |
| xlrd | 2.0 | Legacy Excel (`.xls`) file support |
| PyInstaller | 6.0 | Building standalone executables (dev only) |

Install all runtime + build dependencies at once:

```
pip install -r requirements.txt
```

## Run from source

```
pip install -r requirements.txt
python -m citablecleaner
```

## Build a standalone executable with PyInstaller

Two `.spec` files are provided. Run all commands from the repository root.

### Quick-start / development build (recommended)

Produces a **folder** distribution (`dist/CITableCleaner/`). The app starts instantly because no extraction step is needed, and incremental rebuilds are fast.

```
pyinstaller citablecleaner-quickstart.spec
```

The executable is at `dist/CITableCleaner/CITableCleaner.exe`. It must stay inside the `dist/CITableCleaner/` folder (it depends on the sibling `_internal/` directory). To share the build, zip the whole `dist/CITableCleaner/` folder.

### Single-file release build

Packs everything into one self-contained `.exe`. Startup is slightly slower because the files are extracted to a temp directory on first run.

```
pyinstaller citablecleaner.spec
```

The executable is at `dist/CITableCleaner.exe`.

### Cleaning old build artefacts

Before doing a clean rebuild it is good practice to remove previous output:

```
Remove-Item -Recurse -Force build, dist   # PowerShell
# or
rmdir /s /q build dist                    # cmd
```
