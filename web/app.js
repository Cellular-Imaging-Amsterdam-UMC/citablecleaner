/**
 * app.js — Main-thread logic for CITableCleaner web version.
 *
 * Responsibilities:
 *   • Spawn worker.js and handle its message protocol
 *   • File picker + drag-and-drop → transfer ArrayBuffer to worker
 *   • Wire all UI controls (plate, column list, bottom bar)
 *   • localStorage persistence (column selection)
 *   • Trigger browser file downloads on export
 */

import { WellPlate } from './plate.js';

// ── Constants ──────────────────────────────────────────────────────────────
const XLSX_WARN_MB = 50;
const LS_SOURCE    = 'col_selection_source_cols';
const LS_CHECKED   = 'col_selection_checked';

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const initOverlay    = $('init-overlay');
const initProgress   = $('init-progress');
const initMsg        = $('init-msg');
const toast          = $('toast');

const loadBtn        = $('load-btn');
const fileInput      = $('file-input');
const fileLabel      = $('file-label');
const loadProgress   = $('load-progress');
const progressWrap   = $('progress-wrap');

const plateCanvas    = $('plate-canvas');
const plateFormatLbl = $('plate-format-label');
const selAllWellBtn  = $('sel-all-wells');
const deselAllWellBtn= $('desel-all-wells');

const colList        = $('col-list');
const selAllColBtn   = $('sel-all-cols');
const deselAllColBtn = $('desel-all-cols');
const snInfo         = $('sn-info');

const rowPctInput    = $('row-pct');
const splitColSel    = $('split-col');
const splitThreshold = $('split-threshold');
const exportBtn      = $('export-btn');

const statusRows     = $('status-rows');
const statusWells    = $('status-wells');
const statusCols     = $('status-cols');
const statusOutput   = $('status-output');

// ── State ──────────────────────────────────────────────────────────────────
let plate        = null;
let worker       = null;
let workerReady  = false;
let currentFile  = null;  // File object
let outputStats  = null;  // last rowStats response from worker
// ── Init Web Worker ────────────────────────────────────────────────────────
function startWorker() {
  worker = new Worker('./worker.js');
  worker.onmessage = onWorkerMessage;
  worker.postMessage({ type: 'init' });
}

function onWorkerMessage(e) {
  const msg = e.data;
  switch (msg.type) {
    case 'progress':
      if (!workerReady) {
        // Boot progress
        initProgress.value = msg.value;
        initMsg.textContent = msg.value < 70
          ? 'Loading Python runtime… (first visit ~5 s)'
          : 'Loading packages…';
      } else {
        // File-load progress
        loadProgress.value = msg.value;
      }
      break;

    case 'ready':
      workerReady = true;
      initOverlay.classList.add('hidden');
      loadBtn.disabled = false;
      break;

    case 'loaded':
      onFileLoaded(msg);
      break;

    case 'exported':
      onExported(msg.files);
      break;

    case 'colRange':
      splitThreshold.min   = msg.min;
      splitThreshold.max   = msg.max;
      // Only snap value if user hasn't changed it yet
      if (Number(splitThreshold.value) === 0) splitThreshold.value = 0;
      break;

    case 'rowStats':
      outputStats = msg;
      renderOutputStatus();
      break;

    case 'error':
      hideProgress();
      exportBtn.disabled = false;
      showToast(`Error: ${msg.message}`, true);
      break;
  }
}

// ── Well plate ─────────────────────────────────────────────────────────────
function initPlate() {
  plate = new WellPlate(plateCanvas);
  plate.addEventListener('selectionChanged', () => updateStatus());
}

// ── File loading ───────────────────────────────────────────────────────────
loadBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) loadFile(fileInput.files[0]);
  fileInput.value = '';   // reset so the same file can be re-selected
});

// Drag-and-drop
document.addEventListener('dragover', e => {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
});
document.addEventListener('drop', e => {
  e.preventDefault();
  const f = e.dataTransfer.files[0];
  if (f) loadFile(f);
});

function loadFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  const validExts = ['.csv', '.tsv', '.txt', '.xlsx'];
  if (!validExts.includes(ext)) {
    showToast(`Unsupported file type: ${ext}. Use CSV, TSV, TXT or XLSX.`, true);
    return;
  }

  const sizeMB = file.size / 1024 / 1024;

  // .xlsx size warning
  if (ext === '.xlsx' && sizeMB > XLSX_WARN_MB) {
    showToast(
      `⚠ Large Excel file (${sizeMB.toFixed(0)} MB). Parsing may take a while. ` +
      'Consider exporting as CSV for faster loading.',
      false
    );
  }

  currentFile = file;
  fileLabel.textContent = file.name;
  showProgress();

  file.arrayBuffer().then(buf => {
    worker.postMessage({ type: 'load', buf, ext, sizeMB }, [buf]);
  });
}

function onFileLoaded({ wells, columns, numericCols, rowCount, singleRowPerWell }) {
  hideProgress();

  // Plate
  plate.setAvailableWells(wells);
  plate.selectAll();
  plateFormatLbl.textContent = plate.plateLabel();

  // Column list
  buildColList(columns, numericCols);

  // Row sampling
  rowPctInput.disabled = singleRowPerWell;
  rowPctInput.title = singleRowPerWell
    ? 'Disabled: only one row per well in this data.'
    : 'Percentage of rows to keep. 10% → every 10th row.';

  // Split combo
  buildSplitCombo(numericCols);

  statusRows.textContent = `Rows: ${rowCount.toLocaleString()}`;
  updateStatus();
  updateExportBtn();
}

// ── Column list ────────────────────────────────────────────────────────────
function buildColList(columns, numericCols) {
  colList.innerHTML = '';

  // Restore persisted selection if columns match
  let checkedSet = new Set(columns);
  try {
    const savedSource  = JSON.parse(localStorage.getItem(LS_SOURCE)  || '[]');
    const savedChecked = JSON.parse(localStorage.getItem(LS_CHECKED) || '[]');
    const match = savedSource.length === columns.length &&
      [...columns].every(c => savedSource.includes(c));
    if (match) checkedSet = new Set(savedChecked);
  } catch (_) { /* ignore corrupt storage */ }

  for (const col of columns) {
    const lbl = document.createElement('label');
    const cb  = document.createElement('input');
    cb.type    = 'checkbox';
    cb.checked = checkedSet.has(col);
    cb.dataset.col = col;
    cb.addEventListener('change', () => { saveColSelection(); updateStatus(); updateExportBtn(); });
    lbl.append(cb, col);
    colList.appendChild(lbl);
  }

  saveColSelection();
}

function selectedColumns() {
  return [...colList.querySelectorAll('input[type=checkbox]:checked')]
    .map(cb => cb.dataset.col);
}

function saveColSelection() {
  const all     = [...colList.querySelectorAll('input[type=checkbox]')].map(cb => cb.dataset.col);
  const checked = selectedColumns();
  localStorage.setItem(LS_SOURCE,  JSON.stringify(all));
  localStorage.setItem(LS_CHECKED, JSON.stringify(checked));
}

selAllColBtn.addEventListener('click', () => {
  colList.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = true);
  saveColSelection(); updateStatus(); updateExportBtn();
});
deselAllColBtn.addEventListener('click', () => {
  colList.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = false);
  saveColSelection(); updateStatus(); updateExportBtn();
});

// ── Well buttons ───────────────────────────────────────────────────────────
selAllWellBtn.addEventListener('click',   () => plate?.selectAll());
deselAllWellBtn.addEventListener('click', () => plate?.deselectAll());

// ── Split combo ────────────────────────────────────────────────────────────
function buildSplitCombo(numericCols) {
  splitColSel.innerHTML = '';
  const noneOpt = document.createElement('option');
  noneOpt.value = '(none)';
  noneOpt.textContent = '(none)';
  splitColSel.appendChild(noneOpt);
  for (const col of numericCols) {
    const opt = document.createElement('option');
    opt.value = col;
    opt.textContent = col;
    splitColSel.appendChild(opt);
  }
  splitColSel.disabled      = false;
  splitThreshold.disabled   = true;
  splitThreshold.value      = 0;
}

splitColSel.addEventListener('change', () => {
  const chosen = splitColSel.value !== '(none)';
  splitThreshold.disabled = !chosen;
  if (chosen) {
    worker.postMessage({ type: 'colRange', colName: splitColSel.value });
  }
  requestRowStats();
});

rowPctInput.addEventListener('input', () => requestRowStats());
splitThreshold.addEventListener('input', () => requestRowStats());

// ── Export ─────────────────────────────────────────────────────────────────
exportBtn.addEventListener('click', () => {
  const wells   = [...plate.selectedWells()];
  const columns = selectedColumns();
  if (!wells.length) { showToast('Please select at least one well.', true); return; }
  if (!columns.length){ showToast('Please select at least one column.', true); return; }

  exportBtn.disabled = true;
  exportBtn.textContent = 'Exporting…';

  worker.postMessage({
    type:      'export',
    wells,
    columns,
    rowPct:    Number(rowPctInput.value) || 100,
    splitCol:  splitColSel.value,
    threshold: Number(splitThreshold.value) || 0,
  });
});

function onExported(files) {
  exportBtn.disabled = false;
  exportBtn.textContent = 'Export CSV';

  if (!files.length) {
    showToast('Nothing exported — both split groups were empty.', true);
    return;
  }

  // Build well-based filename prefix from selected wells
  const wells = [...plate.selectedWells()].sort((a, b) => {
    if (a[0] !== b[0]) return a[0] < b[0] ? -1 : 1;
    return parseInt(a.slice(1)) - parseInt(b.slice(1));
  });
  const namePart = wells.length <= 4
    ? wells.join('-')
    : `${wells[0]}-${wells[wells.length - 1]}`;

  // Download each file with a short stagger
  files.forEach((f, i) => {
    setTimeout(() => {
      const blob = new Blob([f.csv_text], { type: 'text/csv' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `${namePart}-${f.filename}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, i * 150);
  });

  showToast(
    files.length === 1
      ? `Saved: ${namePart}-${files[0].filename}`
      : `Saved ${files.length} files: ${files.map(f => f.filename).join(', ')}`,
    false
  );
}

// ── Status ─────────────────────────────────────────────────────────────────
function updateStatus() {
  const nWells = plate ? plate.selectedWells().size : 0;
  const nCols  = selectedColumns().length;
  statusWells.textContent = `Wells selected: ${nWells}`;
  statusCols.textContent  = `Columns selected: ${nCols}`;
  requestRowStats();
}

// Debounced: avoids hammering the worker while threshold/pct is being typed
let statsDebounce = null;
function requestRowStats() {
  clearTimeout(statsDebounce);
  if (!workerReady || !plate) return;
  const wells = [...plate.selectedWells()];
  if (!wells.length) { outputStats = null; renderOutputStatus(); return; }
  statsDebounce = setTimeout(() => {
    worker.postMessage({
      type:      'rowStats',
      wells,
      rowPct:    Number(rowPctInput.value) || 100,
      splitCol:  splitColSel.value,
      threshold: Number(splitThreshold.value) || 0,
    });
  }, 150);
}

function renderOutputStatus() {
  if (!outputStats) { statusOutput.textContent = ''; return; }
  const { step, sampled, low, high } = outputStats;
  const approx = step > 1 ? '~' : '';
  const thr    = Number(splitThreshold.value);
  if (low !== undefined && high !== undefined) {
    statusOutput.textContent =
      `Output:  ≤${thr}: ${approx}${low.toLocaleString()}  |  >${thr}: ${approx}${high.toLocaleString()}`;
  } else if (step > 1) {
    statusOutput.textContent = `Output: ${approx}${sampled.toLocaleString()} rows`;
  } else {
    statusOutput.textContent = '';
  }
}

function updateExportBtn() {
  const ready = plate && plate.selectedWells().size > 0 && selectedColumns().length > 0;
  exportBtn.disabled = !ready;
}

// ── Progress helpers ───────────────────────────────────────────────────────
function showProgress() {
  loadProgress.value = 0;
  progressWrap.style.display = '';
}
function hideProgress() {
  progressWrap.style.display = 'none';
}

// ── Toast ──────────────────────────────────────────────────────────────────
let toastTimer = null;
function showToast(msg, isError, duration = 5000) {
  toast.textContent = msg;
  toast.className   = isError ? '' : 'success';
  toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add('hidden'), duration);
}

// ── Bootstrap ──────────────────────────────────────────────────────────────
initPlate();
updateStatus();
hideProgress();
startWorker();
