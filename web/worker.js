/**
 * worker.js — Pyodide Web Worker for CITableCleaner.
 *
 * Message protocol (main → worker):
 *   { type: 'init' }
 *   { type: 'load',   buf: ArrayBuffer, ext: string, sizeMB: number }
 *   { type: 'export', wells: string[], columns: string[], rowPct: number,
 *                     splitCol: string, threshold: number,
 *                     aggregateToWells: boolean, wellsColumns: string[] }
 *   { type: 'colRange', colName: string }
 *
 * Message protocol (worker → main):
 *   { type: 'ready' }
 *   { type: 'progress', value: number }   // 0-100
 *   { type: 'loaded',   wells, columns, numericCols, rowCount, singleRowPerWell,
 *                       wellColumn, colDescriptions, matchedHeaderCsv,
 *                       isCellsTable, availableWellsCols, wellsColDescs }
 *   { type: 'exported', files: [{filename, csv_text}] }
 *   { type: 'colRange', min, max }
 *   { type: 'error',    message: string }
 */

/* eslint-env worker */
importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.3/full/pyodide.js');

let pyodide = null;
let appPyText = null;

// ── Boot ──────────────────────────────────────────────────────────────────

async function init() {
  try {
    postMessage({ type: 'progress', value: 5 });

    pyodide = await loadPyodide();
    postMessage({ type: 'progress', value: 30 });

    await pyodide.loadPackage(['pandas', 'micropip']);
    postMessage({ type: 'progress', value: 55 });

    // openpyxl is not bundled in Pyodide — install from PyPI via micropip
    await pyodide.runPythonAsync("import micropip; await micropip.install('openpyxl')");
    postMessage({ type: 'progress', value: 70 });

    // Fetch app.py relative to this worker script's location
    const resp = await fetch(new URL('app.py', self.location.href));
    appPyText = await resp.text();
    pyodide.runPython(appPyText);

    // Pre-load header CSVs into the virtual FS so app.py can match them for column tooltips
    for (const name of ['cellstableheaders.csv', 'wellstableheaders.csv']) {
      try {
        const r = await fetch(new URL(name, self.location.href));
        if (r.ok) pyodide.FS.writeFile(`/tmp/${name}`, await r.text());
      } catch (_) { /* non-critical — tooltips simply won't appear */ }
    }

    postMessage({ type: 'progress', value: 100 });
    postMessage({ type: 'ready' });
  } catch (err) {
    postMessage({ type: 'error', message: `Pyodide init failed: ${err}` });
  }
}

// ── Load file ─────────────────────────────────────────────────────────────

async function loadFile(buf, ext, sizeMB) {
  try {
    postMessage({ type: 'progress', value: 10 });

    // Write bytes to Pyodide virtual FS
    pyodide.FS.writeFile('/tmp/citabledatafile' + ext, new Uint8Array(buf));
    postMessage({ type: 'progress', value: 50 });

    const result = pyodide.globals.get('load_file')('/tmp/citabledatafile' + ext, ext);
    const info = result.toJs({ dict_converter: Object.fromEntries });
    result.destroy();

    postMessage({ type: 'progress', value: 100 });
    postMessage({
      type: 'loaded',
      wells:            info.wells,
      columns:          info.columns,
      numericCols:      info.numeric_cols,
      rowCount:         info.row_count,
      singleRowPerWell: info.single_row_per_well,
      wellColumn:       info.well_column,
      colDescriptions:  info.col_descriptions || {},
      matchedHeaderCsv: info.matched_header_csv || null,
      isCellsTable:     info.is_cells_table || false,
      availableWellsCols: info.available_wells_cols || [],
      wellsColDescs:    info.wells_col_descs || {},
    });
  } catch (err) {
    postMessage({ type: 'error', message: `Load failed: ${err}` });
  }
}

// ── Export ────────────────────────────────────────────────────────────────

async function exportData({ wells, columns, rowPct, splitCol, threshold, aggregateToWells, wellsColumns }) {
  try {
    const pyWells     = pyodide.toPy(wells);
    const pyCols      = pyodide.toPy(columns);
    const pyWellsCols = pyodide.toPy(wellsColumns || []);
    const pyResult    = pyodide.globals.get('export_data')(
      pyWells, pyCols, rowPct, splitCol || '(none)', threshold ?? 0,
      aggregateToWells || false, pyWellsCols
    );
    pyWells.destroy();
    pyCols.destroy();
    pyWellsCols.destroy();

    // Convert list of dicts to plain JS array
    const files = [];
    for (let i = 0; i < pyResult.length; i++) {
      const item = pyResult.get(i);
      files.push({
        filename: item.get('filename'),
        csv_text: item.get('csv_text'),
      });
      item.destroy();
    }
    pyResult.destroy();

    postMessage({ type: 'exported', files });
  } catch (err) {
    postMessage({ type: 'error', message: `Export failed: ${err}` });
  }
}

// ── Column range ──────────────────────────────────────────────────────────

function getColRange(colName) {
  try {
    const r = pyodide.globals.get('get_col_range')(colName);
    const info = r.toJs({ dict_converter: Object.fromEntries });
    r.destroy();
    postMessage({ type: 'colRange', min: info.min, max: info.max });
  } catch (err) {
    postMessage({ type: 'error', message: `col range failed: ${err}` });
  }
}

// ── Row stats ──────────────────────────────────────────────────────────────

function getRowStats({ wells, rowPct, splitCol, threshold, aggregateToWells }) {
  try {
    const pyWells = pyodide.toPy(wells);
    const result  = pyodide.globals.get('get_row_stats')(
      pyWells, rowPct, splitCol || '(none)', threshold ?? 0,
      aggregateToWells || false
    );
    pyWells.destroy();
    const info = result.toJs({ dict_converter: Object.fromEntries });
    result.destroy();
    postMessage({ type: 'rowStats', ...info });
  } catch (err) {
    // Non-critical — just skip the update silently
  }
}

// ── Message router ────────────────────────────────────────────────────────

self.onmessage = async (e) => {
  const msg = e.data;
  switch (msg.type) {
    case 'init':     await init(); break;
    case 'load':     await loadFile(msg.buf, msg.ext, msg.sizeMB); break;
    case 'export':   await exportData(msg); break;
    case 'colRange': getColRange(msg.colName); break;
    case 'rowStats': getRowStats(msg); break;
  }
};
