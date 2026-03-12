# citablecleaner.spec — PyInstaller build spec
# Build with:  pyinstaller citablecleaner.spec
#              (run from the CITableCleaner/ directory)
#
# Produces:  dist/CITableCleaner.exe  (single-file executable)

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
    a.binaries,
    a.zipfiles,
    a.datas,
    name='CITableCleaner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowless app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='citablecleaner/resources/app.ico',
)
