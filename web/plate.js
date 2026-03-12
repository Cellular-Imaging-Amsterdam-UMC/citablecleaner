/**
 * plate.js — Canvas-based well-plate widget.
 * Direct port of citablecleaner/plate_widget.py.
 *
 * Usage:
 *   const plate = new WellPlate(document.getElementById('plate-canvas'));
 *   plate.setAvailableWells(['A01','B02', ...]);
 *   plate.addEventListener('selectionChanged', e => console.log(e.detail));
 */

const _ROW_LETTERS = 'ABCDEFGHIJKLMNOP'; // 16 → covers 384-well

const _C = {
  bg:        '#1e293b',
  empty:     '#2d3f55',
  available: '#0d9488',
  selected:  '#38bdf8',
  hover:     '#0ea5e9',
  header:    '#0f172a',
  text:      '#f1f5f9',
  textDim:   '#64748b',
  textSel:   '#0f172a',
  border:    '#475569',
};

const _FORMATS = {
  96:  { rows: 8,  cols: 12, label: '96-well' },
  384: { rows: 16, cols: 24, label: '384-well' },
};

function _wellName(r, c) {
  return `${_ROW_LETTERS[r]}${String(c + 1).padStart(2, '0')}`;
}

function _parseWell(name) {
  if (!name || name.length < 2) return null;
  const rowLetter = name[0].toUpperCase();
  const colStr = name.slice(1);
  const rowIdx = _ROW_LETTERS.indexOf(rowLetter);
  if (rowIdx === -1) return null;
  const colNum = parseInt(colStr, 10);
  if (isNaN(colNum)) return null;
  return { r: rowIdx, c: colNum - 1 };
}

export class WellPlate extends EventTarget {
  #canvas;
  #ctx;
  #format = 96;
  #rows   = 8;
  #cols   = 12;
  #available = new Set();
  #selected  = new Set();
  #hovered   = null;

  // layout cache
  #cellW = 0; #cellH = 0; #hSz = 0; #ox = 0; #oy = 0;

  static #MARGIN      = 6;
  static #HEADER_SIZE = 22;
  static #WELL_GAP    = 3;

  constructor(canvas) {
    super();
    this.#canvas = canvas;
    this.#ctx    = canvas.getContext('2d');

    canvas.addEventListener('mousemove', e => this.#onMouseMove(e));
    canvas.addEventListener('mouseleave', () => this.#onMouseLeave());
    canvas.addEventListener('click', e => this.#onClick(e));

    // Redraw when the canvas element is resized
    const ro = new ResizeObserver(() => this.#resize());
    ro.observe(canvas);
    this.#resize();
  }

  // ── Public API ───────────────────────────────────────────────────────────

  setAvailableWells(wells) {
    this.#available = new Set(wells);
    this.#selected.clear();
    this.#hovered = null;

    let needs384 = false;
    for (const name of wells) {
      const p = _parseWell(name);
      if (p && (p.r >= 8 || p.c >= 12)) { needs384 = true; break; }
    }
    const fmt = needs384 ? 384 : 96;
    this.#format = fmt;
    this.#rows  = _FORMATS[fmt].rows;
    this.#cols  = _FORMATS[fmt].cols;

    this.#draw();
    this.#emitSelection();
  }

  selectAll() {
    this.#selected = new Set(this.#available);
    this.#draw();
    this.#emitSelection();
  }

  deselectAll() {
    this.#selected.clear();
    this.#draw();
    this.#emitSelection();
  }

  selectedWells() { return new Set(this.#selected); }

  plateLabel() {
    return `${_FORMATS[this.#format].label} · ${this.#available.size} well(s) found`;
  }

  // ── Private ──────────────────────────────────────────────────────────────

  #emitSelection() {
    this.dispatchEvent(new CustomEvent('selectionChanged', {
      detail: new Set(this.#selected),
    }));
  }

  #resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.#canvas.getBoundingClientRect();
    this.#canvas.width  = rect.width  * dpr;
    this.#canvas.height = rect.height * dpr;
    this.#ctx.scale(dpr, dpr);
    this.#draw();
  }

  #computeLayout() {
    const dpr  = window.devicePixelRatio || 1;
    const w    = this.#canvas.width  / dpr;
    const h    = this.#canvas.height / dpr;
    const m    = WellPlate.#MARGIN;
    const gap  = WellPlate.#WELL_GAP;
    const hSz  = this.#format === 96 ? WellPlate.#HEADER_SIZE
                                     : Math.max(14, WellPlate.#HEADER_SIZE - 4);

    const cellW = Math.max(4, Math.floor((w - 2*m - hSz - gap*(this.#cols-1)) / this.#cols));
    const cellH = Math.max(4, Math.floor((h - 2*m - hSz - gap*(this.#rows-1)) / this.#rows));

    const totalW = hSz + this.#cols*cellW + (this.#cols-1)*gap + gap;
    const totalH = hSz + this.#rows*cellH + (this.#rows-1)*gap;
    const ox = m + Math.max(0, Math.floor((w - 2*m - totalW) / 2));
    const oy = m + Math.max(0, Math.floor((h - 2*m - totalH) / 2));

    this.#cellW = cellW; this.#cellH = cellH;
    this.#hSz   = hSz;  this.#ox = ox; this.#oy = oy;
  }

  #draw() {
    const dpr  = window.devicePixelRatio || 1;
    const w    = this.#canvas.width  / dpr;
    const h    = this.#canvas.height / dpr;
    const ctx  = this.#ctx;
    const gap  = WellPlate.#WELL_GAP;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = _C.bg;
    ctx.fillRect(0, 0, w, h);

    this.#computeLayout();
    const { '#cellW': cellW, '#cellH': cellH, '#hSz': hSz, '#ox': ox, '#oy': oy } = this;
    const cW = this.#cellW, cH = this.#cellH, hS = this.#hSz;
    const oX = this.#ox,   oY = this.#oy;

    // Column headers
    const hdrSize = this.#format === 96 ? 9 : 7;
    ctx.font = `bold ${hdrSize}px "Segoe UI", sans-serif`;
    ctx.fillStyle = _C.text;
    for (let c = 0; c < this.#cols; c++) {
      const x = oX + hS + c*(cW + gap);
      ctx.fillStyle = _C.header;
      ctx.fillRect(x, oY, cW, hS);
      ctx.fillStyle = _C.text;
      const label = this.#format === 384 && (c+1) % 2 !== 0 ? '' : String(c+1);
      if (label) {
        ctx.fillText(label, x + cW/2 - ctx.measureText(label).width/2, oY + hS*0.72);
      }
    }

    // Row headers
    for (let r = 0; r < this.#rows; r++) {
      const y = oY + hS + r*(cH + gap);
      ctx.fillStyle = _C.header;
      ctx.fillRect(oX, y, hS, cH);
      ctx.fillStyle = _C.text;
      const letter = _ROW_LETTERS[r];
      ctx.fillText(letter, oX + hS/2 - ctx.measureText(letter).width/2, y + cH*0.68);
    }

    // Wells
    const wellFontSz = this.#format === 96
      ? Math.max(6, Math.floor(Math.min(cW, cH) / 3))
      : Math.max(5, Math.floor(Math.min(cW, cH) / 4));
    ctx.font = `${wellFontSz}px "Segoe UI", sans-serif`;

    for (let r = 0; r < this.#rows; r++) {
      for (let c = 0; c < this.#cols; c++) {
        const name = _wellName(r, c);
        const x = oX + hS + c*(cW + gap);
        const y = oY + hS + r*(cH + gap);

        const isAvail   = this.#available.has(name);
        const isSel     = this.#selected.has(name);
        const isHovered = name === this.#hovered && isAvail && !isSel;

        let fill, textCol;
        if (isSel)         { fill = _C.selected;  textCol = _C.textSel; }
        else if (isHovered){ fill = _C.hover;      textCol = _C.textSel; }
        else if (isAvail)  { fill = _C.available;  textCol = _C.text;    }
        else               { fill = _C.empty;      textCol = _C.textDim; }

        // Ellipse
        const pad = Math.max(1, Math.floor(Math.min(cW, cH) * 0.08));
        ctx.fillStyle = fill;
        ctx.beginPath();
        ctx.ellipse(
          x + cW/2, y + cH/2,
          (cW/2 - pad), (cH/2 - pad),
          0, 0, 2*Math.PI
        );
        ctx.fill();

        // Label
        if (isAvail || isSel) {
          if (this.#format === 96 || (cW >= 20 && cH >= 14)) {
            ctx.fillStyle = textCol;
            ctx.fillText(name, x + cW/2 - ctx.measureText(name).width/2, y + cH*0.65);
          }
        }
      }
    }
  }

  #wellAt(px, py) {
    const dpr = window.devicePixelRatio || 1;
    const gap = WellPlate.#WELL_GAP;
    const rx = px - this.#ox - this.#hSz;
    const ry = py - this.#oy - this.#hSz;
    if (rx < 0 || ry < 0) return null;
    const c = Math.floor(rx / (this.#cellW + gap));
    const r = Math.floor(ry / (this.#cellH + gap));
    if (r >= 0 && r < this.#rows && c >= 0 && c < this.#cols) {
      return _wellName(r, c);
    }
    return null;
  }

  #canvasPos(e) {
    const rect = this.#canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  #onMouseMove(e) {
    const { x, y } = this.#canvasPos(e);
    const well = this.#wellAt(x, y);
    if (well !== this.#hovered) {
      this.#hovered = well;
      this.#draw();
    }
  }

  #onMouseLeave() {
    if (this.#hovered !== null) {
      this.#hovered = null;
      this.#draw();
    }
  }

  #onClick(e) {
    const { x, y } = this.#canvasPos(e);
    const well = this.#wellAt(x, y);
    if (well && this.#available.has(well)) {
      if (this.#selected.has(well)) this.#selected.delete(well);
      else this.#selected.add(well);
      this.#hovered = null;
      this.#draw();
      this.#emitSelection();
    }
  }
}
