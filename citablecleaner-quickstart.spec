# citablecleaner-quickstart.spec — PyInstaller one-FOLDER build spec
# Build with:  pyinstaller citablecleaner-quickstart.spec
#              (run from the CITableCleaner/ directory)
#
# Produces:  dist/CITableCleaner/CITableCleaner.exe  (folder distribution)
#            Run CITableCleaner.exe from inside dist/CITableCleaner/ — it needs
#            the _internal/ sibling folder next to it.
#            For release: zip the dist/CITableCleaner/ folder itself.
#
# Why use this instead of citablecleaner.spec?
#   • Folder builds skip the single-file extraction step → app starts instantly.
#   • Incremental rebuilds are much faster (only changed files are re-written).
#   • Ideal for quick iteration / testing during development.
#   • Ship the whole dist/CITableCleaner/ folder (e.g. zip it) for distribution.

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all PyQt6 and pandas submodules, data files, and binaries
pyqt6_datas,  pyqt6_binaries,  pyqt6_hiddenimports  = collect_all('PyQt6')
pandas_datas, pandas_binaries, pandas_hiddenimports  = collect_all('pandas')

a = Analysis(
    ['citablecleaner/__main__.py'],
    pathex=['.'],
    binaries=pyqt6_binaries + pandas_binaries,
    datas=[
        ('citablecleaner/resources', 'citablecleaner/resources'),
        ('version.txt', '.'),
    ] + pyqt6_datas + pandas_datas,
    hiddenimports=[
        'pandas',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.skiplist',
        'numpy',
    ] + pyqt6_hiddenimports + pandas_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'torch', 'torchvision', 'torchaudio',
        'scipy', 'sklearn', 'IPython', 'matplotlib',
        'pandas.tests', 'pytest',
        'tkinter', '_tkinter',
        'notebook', 'nbformat', 'jupyter',
        'zmq', 'jedi', 'parso',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],                         # no binaries/datas embedded — goes into COLLECT
    name='CITableCleaner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # skip UPX compression for faster builds
    console=False,              # windowless app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='citablecleaner/resources/app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CITableCleaner',      # → dist/CITableCleaner/
)

# ── Post-build: remove the bare bootloader exe that PyInstaller writes to
#    dist/ as a side-effect of the EXE step.  Only the folder in
#    dist/CITableCleaner/ is a working distribution.
import os as _os
_stale = _os.path.join(DISTPATH, 'CITableCleaner.exe')
if _os.path.isfile(_stale):
    _os.remove(_stale)
    print(f'Removed stale bootloader: {_stale}')
