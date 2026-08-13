import { Cell, ICellModel } from '@jupyterlab/cells';
import { IObservableList } from '@jupyterlab/observables';
import { NotebookActions, NotebookPanel } from '@jupyterlab/notebook';

import { INBFixDiagnostic, postEvent } from './handler';
import { diagnosticsStore, getEditorView, toCodeMirrorDiagnostics } from './linter';

const CHANGE_DEBOUNCE_MS = 500;
// Matches events.py's AddCellEvent `kind` values: only code cells are
// tracked in NBFix's notebook_IR, so newly added cells are always
// reported as kind 2 (code) regardless of their actual cell type.
const CODE_CELL_KIND = 2;

/**
 * Merges two diagnostic sets by cell_id, concatenating each cell's errors.
 * Used to combine the always-on deterministic analyses with the on-demand
 * LLM findings without either one clobbering the other when re-rendered.
 */
function mergeDiagnostics(
  a: INBFixDiagnostic[],
  b: INBFixDiagnostic[]
): INBFixDiagnostic[] {
  const byCellId = new Map<number, INBFixDiagnostic['errors']>();
  for (const source of [a, b]) {
    for (const cellDiagnostic of source) {
      const existing = byCellId.get(cellDiagnostic.cell_id) ?? [];
      byCellId.set(cellDiagnostic.cell_id, [...existing, ...cellDiagnostic.errors]);
    }
  }
  return Array.from(byCellId.entries()).map(([cell_id, errors]) => ({
    cell_id,
    errors
  }));
}

function countFindings(diagnostics?: INBFixDiagnostic[]): number {
  return (diagnostics ?? []).reduce((sum, cellDiagnostic) => sum + cellDiagnostic.errors.length, 0);
}

/**
 * Wires one NotebookPanel's lifecycle/edit/execute signals to the NBFix
 * server extension, and renders the diagnostics it returns via the
 * CodeMirror linter registered in linter.ts.
 *
 * Cell identity for the backend is purely positional (matches events.py's
 * position-based Event model), so every event resolves a cell's index from
 * its live position in `panel.content.widgets` at the moment the event
 * fires, rather than capturing an index up front - positions shift under
 * concurrent adds/removes/debounced edits otherwise.
 */
export class NotebookSessionManager {
  private _panel: NotebookPanel;
  private _notebookId: string;
  private _pendingEdits = new Map<string, number>();
  private _watched = new WeakSet<ICellModel>();
  private _deterministicDiagnostics: INBFixDiagnostic[] = [];
  private _llmDiagnostics: INBFixDiagnostic[] = [];

  constructor(panel: NotebookPanel) {
    this._panel = panel;
    this._notebookId = panel.context.path;
  }

  async start(): Promise<void> {
    await this._panel.context.ready;

    const response = await postEvent('open_notebook', this._notebookId, {
      notebook_json: this._cellsAsJSON()
    });
    this._setDeterministicDiagnostics(response.diagnostics);

    this._panel.content.model?.cells.changed.connect(this._onCellsChanged, this);
    NotebookActions.executed.connect(this._onCellExecuted, this);
    this._panel.disposed.connect(this._onDisposed, this);

    this._panel.content.widgets.forEach(cellWidget => this._watchCell(cellWidget));
  }

  /**
   * Runs an on-demand LLM bug check over the connected-cell subgraph around
   * cellIndex (not just that one cell in isolation - cross-cell bugs are
   * the priority target). Findings are merged with, not replacing, the
   * live deterministic diagnostics already on screen. Returns the number
   * of findings - Notification.promise (the caller) requires a
   * JSON-serializable resolution value, and the count doubles as a useful
   * success message.
   */
  async checkCellForBugs(cellIndex: number): Promise<number> {
    const response = await postEvent('detect_bugs', this._notebookId, {
      scope: 'subgraph',
      cell_index: cellIndex
    });
    this._setLLMDiagnostics(response.diagnostics);
    return countFindings(response.diagnostics);
  }

  /** Runs an on-demand LLM bug check over the whole notebook. */
  async checkNotebookForBugs(): Promise<number> {
    const response = await postEvent('detect_bugs', this._notebookId, {
      scope: 'full'
    });
    this._setLLMDiagnostics(response.diagnostics);
    return countFindings(response.diagnostics);
  }

  private _cellsAsJSON(): Array<{ cell_type: string; source: string }> {
    return this._panel.content.widgets.map(cellWidget => ({
      cell_type: cellWidget.model.type,
      source: cellWidget.model.sharedModel.getSource()
    }));
  }

  private _watchCell(cellWidget: Cell): void {
    if (this._watched.has(cellWidget.model)) {
      return;
    }
    this._watched.add(cellWidget.model);
    cellWidget.model.contentChanged.connect(() => this._scheduleChangeCell(cellWidget));
  }

  private _scheduleChangeCell(cellWidget: Cell): void {
    const model = cellWidget.model;
    const existing = this._pendingEdits.get(model.id);
    if (existing !== undefined) {
      window.clearTimeout(existing);
    }

    const handle = window.setTimeout(() => {
      this._pendingEdits.delete(model.id);
      const index = this._panel.content.widgets.indexOf(cellWidget);
      if (index === -1) {
        // Cell was removed before the debounce fired.
        return;
      }
      void postEvent('change_cell', this._notebookId, {
        new_code: model.sharedModel.getSource(),
        cell_index: index,
        with_result: true
      }).then(response => {
        // The edited cell's code changed, so any prior LLM finding about
        // it (or cells connected to it) may no longer apply - drop the
        // whole LLM set rather than show a possibly-stale AI finding.
        this._llmDiagnostics = [];
        this._setDeterministicDiagnostics(response.diagnostics);
      });
    }, CHANGE_DEBOUNCE_MS);

    this._pendingEdits.set(model.id, handle);
  }

  private _onCellsChanged(
    _cells: unknown,
    change: IObservableList.IChangedArgs<ICellModel>
  ): void {
    if (change.type === 'add') {
      this._llmDiagnostics = [];
      void postEvent('add_cell', this._notebookId, {
        position: change.newIndex,
        kind: CODE_CELL_KIND,
        content: change.newValues[0]?.sharedModel.getSource() ?? ''
      }).then(response => this._setDeterministicDiagnostics(response.diagnostics));

      const cellWidget = this._panel.content.widgets[change.newIndex];
      if (cellWidget) {
        this._watchCell(cellWidget);
      }
    } else if (change.type === 'remove') {
      this._llmDiagnostics = [];
      void postEvent('remove_cell', this._notebookId, {
        position: change.oldIndex
      }).then(response => this._setDeterministicDiagnostics(response.diagnostics));
    }
    // 'move'/'set' changes aren't reported as distinct events yet - cell
    // reordering falls back to whatever the next run/edit on the affected
    // cells resolves to.
  }

  private _onCellExecuted(
    _emitter: unknown,
    args: { cell: Cell; success: boolean }
  ): void {
    if (!args.success) {
      return;
    }
    const index = this._panel.content.widgets.indexOf(args.cell);
    if (index === -1) {
      return;
    }
    // Running a cell doesn't change its source, so any existing LLM
    // finding about that code is still valid - only the deterministic set
    // is refreshed here.
    void postEvent('run_cell', this._notebookId, { cell_index: index }).then(
      response => this._setDeterministicDiagnostics(response.diagnostics)
    );
  }

  private _setDeterministicDiagnostics(diagnostics?: INBFixDiagnostic[]): void {
    if (diagnostics) {
      this._deterministicDiagnostics = diagnostics;
    }
    this._render();
  }

  private _setLLMDiagnostics(diagnostics?: INBFixDiagnostic[]): void {
    if (diagnostics) {
      this._llmDiagnostics = diagnostics;
    }
    this._render();
  }

  private _render(): void {
    const merged = mergeDiagnostics(this._deterministicDiagnostics, this._llmDiagnostics);

    this._panel.content.widgets.forEach(cellWidget => {
      const view = getEditorView(cellWidget.editor);
      if (view) {
        diagnosticsStore.clear(view);
      }
    });

    for (const cellDiagnostic of merged) {
      const cellWidget = this._panel.content.widgets[cellDiagnostic.cell_id];
      const view = cellWidget && getEditorView(cellWidget.editor);
      if (view) {
        diagnosticsStore.set(view, toCodeMirrorDiagnostics(view, cellDiagnostic));
      }
    }
  }

  private _onDisposed(): void {
    void postEvent('close_notebook', this._notebookId);
    for (const handle of this._pendingEdits.values()) {
      window.clearTimeout(handle);
    }
    this._pendingEdits.clear();
  }
}
