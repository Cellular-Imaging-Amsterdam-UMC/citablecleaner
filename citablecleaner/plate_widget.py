"""
plate_widget.py — Visual microplate well-selector widget.

Supports 96-well plates (8 rows × 12 cols, A–H, 1–12) and
384-well plates (16 rows × 24 cols, A–P, 1–24).

The format is auto-chosen based on the well names found in the
loaded CSV:  if any well falls outside A-H / 1-12 the widget
switches to 384-well layout.
"""

from __future__ import annotations

import math
from typing import FrozenSet, Set

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

# ── Plate format definitions ───────────────────────────────────────────────

_FORMATS = {
    96:  {"rows": 8,  "cols": 12, "label": "96-well"},
    384: {"rows": 16, "cols": 24, "label": "384-well"},
}

_ROW_LETTERS = "ABCDEFGHIJKLMNOP"   # 16 letters → covers 384-well

# ── Colour palette (dark slate / sky-blue theme) ──────────────────────────
_C_BG        = QColor("#1e293b")   # widget background
_C_EMPTY     = QColor("#2d3f55")   # well with no data
_C_AVAILABLE = QColor("#0d9488")   # well has data, not selected  (teal)
_C_SELECTED  = QColor("#38bdf8")   # well has data and is selected (sky blue)
_C_HOVER     = QColor("#0ea5e9")   # hover over available well
_C_BORDER    = QColor("#475569")   # grid header / label area border
_C_HEADER    = QColor("#0f172a")   # header cell background
_C_TEXT      = QColor("#f1f5f9")   # primary text
_C_TEXT_DIM  = QColor("#64748b")   # dimmed text for empty wells
_C_SELECTED_TEXT = QColor("#0f172a")   # text drawn on selected well


def _well_name(row: int, col: int) -> str:
    """Return canonical well name, e.g. row=0 col=0 → 'A01'."""
    return f"{_ROW_LETTERS[row]}{col + 1:02d}"


def _parse_well(name: str) -> tuple[int, int] | None:
    """
    Parse a well name like 'G02' or 'B12' into (row_index, col_index).
    Returns None if the string is not a recognisable well label.
    """
    name = name.strip()
    if len(name) < 2:
        return None
    row_letter = name[0].upper()
    col_str = name[1:]
    if row_letter not in _ROW_LETTERS:
        return None
    try:
        col_num = int(col_str)
    except ValueError:
        return None
    row_idx = _ROW_LETTERS.index(row_letter)
    col_idx = col_num - 1
    return row_idx, col_idx


class WellPlateWidget(QWidget):
    """
    Custom widget that paints a clickable microplate well grid.

    Signals
    -------
    selectionChanged(frozenset)
        Emitted whenever the set of selected well names changes.
        The frozenset contains canonical well-name strings (e.g. 'G02').
    """

    selectionChanged = pyqtSignal(object)   # frozenset[str]

    # ── Geometry constants ─────────────────────────────────────────────────
    _MARGIN      = 6   # px margin around the whole grid
    _HEADER_SIZE = 22  # px for row/col header cells (96-well; scales down for 384)
    _WELL_GAP    = 3   # px gap between wells

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 200)

        self._format: int = 96
        self._rows: int = 8
        self._cols: int = 12
        self._available: Set[str] = set()
        self._selected: Set[str] = set()
        self._hovered: str | None = None

        self.setMouseTracking(True)

    # ── Public API ─────────────────────────────────────────────────────────

    def setAvailableWells(self, wells: Set[str]) -> None:
        """
        Called after a CSV is loaded.  wells is the set of unique values
        in the SeriesName column.  The widget auto-selects plate format.
        """
        self._available = set(wells)
        self._selected.clear()

        # Determine plate format
        needs_384 = False
        for name in wells:
            parsed = _parse_well(name)
            if parsed is None:
                continue
            r, c = parsed
            if r >= 8 or c >= 12:   # outside 96-well range
                needs_384 = True
                break

        fmt = 384 if needs_384 else 96
        self._format = fmt
        self._rows = _FORMATS[fmt]["rows"]
        self._cols = _FORMATS[fmt]["cols"]

        self.update()
        self.selectionChanged.emit(frozenset(self._selected))

    def selectAll(self) -> None:
        self._selected = set(self._available)
        self.update()
        self.selectionChanged.emit(frozenset(self._selected))

    def deselectAll(self) -> None:
        self._selected.clear()
        self.update()
        self.selectionChanged.emit(frozenset(self._selected))

    def selectedWells(self) -> FrozenSet[str]:
        return frozenset(self._selected)

    def plateLabel(self) -> str:
        return _FORMATS[self._format]["label"]

    # ── Qt overrides ───────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        # Provide a reasonable default size for the splitter
        return QSize(640, 280)

    def minimumSizeHint(self) -> QSize:
        return QSize(320, 160)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        well = self._well_at(event.pos().x(), event.pos().y())
        if well and well in self._available:
            if well in self._selected:
                self._selected.discard(well)
            else:
                self._selected.add(well)
            # Clear hover so the well repaints with its true state colour
            # immediately (teal when deselected), without waiting for mouseMoveEvent.
            self._hovered = None
            self.update()
            self.selectionChanged.emit(frozenset(self._selected))

    def mouseMoveEvent(self, event) -> None:
        well = self._well_at(event.pos().x(), event.pos().y())
        if well != self._hovered:
            self._hovered = well
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hovered is not None:
            self._hovered = None
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), _C_BG)

        cell_w, cell_h, h_sz, ox, oy = self._layout()

        # ── Column headers (1 … cols) ─────────────────────────────────────
        hdr_font = self._header_font()
        painter.setFont(hdr_font)
        for c in range(self._cols):
            x = ox + h_sz + c * (cell_w + self._WELL_GAP)
            rect = QRect(x, oy, cell_w, h_sz)
            painter.fillRect(rect, _C_HEADER)
            painter.setPen(_C_TEXT)
            if self._format == 96:
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(c + 1))
            else:
                # 384: only draw every other column label to avoid crowding
                if (c + 1) % 2 == 0 or self._cols <= 12:
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(c + 1))

        # ── Row headers (A … P) ───────────────────────────────────────────
        for r in range(self._rows):
            y = oy + h_sz + r * (cell_h + self._WELL_GAP)
            rect = QRect(ox, y, h_sz, cell_h)
            painter.fillRect(rect, _C_HEADER)
            painter.setPen(_C_TEXT)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, _ROW_LETTERS[r])

        # ── Wells ─────────────────────────────────────────────────────────
        well_font = self._well_font(cell_w, cell_h)
        painter.setFont(well_font)

        for r in range(self._rows):
            for c in range(self._cols):
                name = _well_name(r, c)
                x = ox + h_sz + c * (cell_w + self._WELL_GAP)
                y = oy + h_sz + r * (cell_h + self._WELL_GAP)
                rect = QRect(x, y, cell_w, cell_h)

                # Choose fill colour
                # Hover only applies to available wells that are NOT selected,
                # so deselecting immediately shows green without moving the mouse.
                is_hovered = (name == self._hovered
                              and name in self._available
                              and name not in self._selected)
                if name in self._selected:
                    fill = _C_SELECTED
                    text_col = _C_SELECTED_TEXT
                elif is_hovered:
                    fill = _C_HOVER
                    text_col = _C_SELECTED_TEXT
                elif name in self._available:
                    fill = _C_AVAILABLE
                    text_col = _C_TEXT
                else:
                    fill = _C_EMPTY
                    text_col = _C_TEXT_DIM

                # Draw circle (ellipse inscribed in rect with small padding)
                pad = max(1, int(min(cell_w, cell_h) * 0.08))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                painter.drawEllipse(rect.adjusted(pad, pad, -pad, -pad))

                # Label inside well — show full well name (e.g. A01, B12)
                if name in self._available or name in self._selected:
                    painter.setPen(text_col)
                    if self._format == 96:
                        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name)
                    else:
                        # 384-well: cells are small — show only if there is room
                        if cell_w >= 20 and cell_h >= 14:
                            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name)

        painter.end()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, int, int, int]:
        """
        Compute well cell dimensions and offsets from current widget size.

        Returns
        -------
        cell_w, cell_h, header_size, origin_x, origin_y
        """
        m  = self._MARGIN
        gw = self._WELL_GAP

        # Scale header size down for 384-well to keep everything visible
        h_sz = self._HEADER_SIZE if self._format == 96 else max(14, self._HEADER_SIZE - 4)

        avail_w = self.width()  - 2 * m - h_sz - gw * (self._cols - 1)
        avail_h = self.height() - 2 * m - h_sz - gw * (self._rows - 1)

        cell_w = max(4, avail_w // self._cols)
        cell_h = max(4, avail_h // self._rows)

        # Centre the grid in the widget
        total_w = h_sz + self._cols * cell_w + (self._cols - 1) * gw + gw
        total_h = h_sz + self._rows * cell_h + (self._rows - 1) * gw
        ox = m + max(0, (self.width()  - 2 * m - total_w) // 2)
        oy = m + max(0, (self.height() - 2 * m - total_h) // 2)

        return cell_w, cell_h, h_sz, ox, oy

    def _well_at(self, px: int, py: int) -> str | None:
        """Return canonical well name at pixel position, or None."""
        cell_w, cell_h, h_sz, ox, oy = self._layout()
        gw = self._WELL_GAP

        # Relative to the grid origin (after header)
        rx = px - ox - h_sz
        ry = py - oy - h_sz
        if rx < 0 or ry < 0:
            return None

        c = rx // (cell_w + gw)
        r = ry // (cell_h + gw)

        if 0 <= r < self._rows and 0 <= c < self._cols:
            return _well_name(r, c)
        return None

    def _header_font(self) -> QFont:
        sz = 8 if self._format == 384 else 9
        f = QFont("Segoe UI", sz, QFont.Weight.Bold)
        return f

    def _well_font(self, cell_w: int, cell_h: int) -> QFont:
        if self._format == 384:
            return QFont("Segoe UI", max(5, min(cell_w, cell_h) // 4))
        return QFont("Segoe UI", max(6, min(cell_w, cell_h) // 3))
