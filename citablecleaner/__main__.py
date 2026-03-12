"""
__main__.py — entry point.
Run with:  python -m citablecleaner   (from the CITableCleaner/ directory)
"""

import ctypes
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QImageReader, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication

from citablecleaner.main_window import MainWindow, _APP_VERSION

_ICON_PATH = Path(__file__).parent / "resources" / "app.ico"


def _load_ico_icon(path: str) -> QIcon:
    """Load an .ico file robustly (same pattern as CellCounter)."""
    reader = QImageReader(path, b"ICO")
    icon = QIcon()
    images = []
    for i in range(reader.imageCount()):
        reader.jumpToImage(i)
        img = reader.read()
        if not img.isNull():
            images.append(img)
            icon.addPixmap(QPixmap.fromImage(img))

    if images:
        largest = max(images, key=lambda im: im.width())
        for sz in (32, 48):
            if not any(im.width() == sz for im in images):
                scaled = largest.scaled(
                    sz, sz,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon.addPixmap(QPixmap.fromImage(scaled))
    return icon


def _apply_dark_palette(app: QApplication) -> None:
    """Apply a dark slate / sky-blue palette."""
    app.setStyle("Fusion")
    p = QPalette()
    bg     = QColor("#0f172a")
    surface= QColor("#1e293b")
    text   = QColor("#f1f5f9")
    dim    = QColor("#94a3b8")
    accent = QColor("#38bdf8")
    white  = QColor("#ffffff")

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            surface)
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor("#243040"))
    p.setColor(QPalette.ColorRole.ToolTipBase,     surface)
    p.setColor(QPalette.ColorRole.ToolTipText,     text)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.Button,          surface)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.BrightText,      white)
    p.setColor(QPalette.ColorRole.Highlight,       accent)
    p.setColor(QPalette.ColorRole.HighlightedText, bg)
    p.setColor(QPalette.ColorRole.Link,            accent)
    p.setColor(QPalette.ColorRole.PlaceholderText, dim)

    # Disabled state
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, dim)

    app.setPalette(p)


def main() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "RonHoebe.CITableCleaner.1"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("CITableCleaner")
    app.setOrganizationName("RonHoebe")
    app.setApplicationVersion(_APP_VERSION)

    _apply_dark_palette(app)

    icon = QIcon()
    if _ICON_PATH.exists():
        icon = _load_ico_icon(str(_ICON_PATH))
        if not icon.isNull():
            app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)   # explicit set → taskbar picks it up on Windows
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
