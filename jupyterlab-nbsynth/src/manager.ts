import { Cell, ICellModel } from '@jupyterlab/cells';
import { IObservableList } from '@jupyterlab/observables';
import { NotebookActions, NotebookPanel } from '@jupyterlab/notebook';

import { INBSynthDiagnostic, postEvent } from './handler';
import { diagnosticsStore, getEditorView, toCodeMirrorDiagnostics } from './linter';

const CHANGE_DEBOUNCE_MS = 500;
// Matches events.py's AddCellEvent `kind` values: only code cells are
// tracked in NBSynth's notebook_IR, so newly added cells are always
// reported as kind 2 (code) regardless of their actual cell type.
const CODE_CELL_KIND = 2;

/**
 * Wires one NotebookPanel's lifecycle/edit/execute signals to the NBSynth
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

  constructor(panel: NotebookPanel) {
    this._panel = panel;
    this._notebookId = panel.context.path;
  }

  async start(): Promise<void> {
    await this._panel.context.ready;

    const response = await postEvent('open_notebook', this._notebookId, {
      notebook_json: this._cellsAsJSON()
    });
    this._applyDiagnostics(response.diagnostics);

    this._panel.content.model?.cells.changed.connect(this._onCellsChanged, this);
    NotebookActions.executed.connect(this._onCellExecuted, this);
    this._panel.disposed.connect(this._onDisposed, this);

    this._panel.content.widgets.forEach(cellWidget => this._watchCell(cellWidget));
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
      }).then(response => this._applyDiagnostics(response.diagnostics));
    }, CHANGE_DEBOUNCE_MS);

    this._pendingEdits.set(model.id, handle);
  }

  private _onCellsChanged(
    _cells: unknown,
    change: IObservableList.IChangedArgs<ICellModel>
  ): void {
    if (change.type === 'add') {
      void postEvent('add_cell', this._notebookId, {
        position: change.newIndex,
        kind: CODE_CELL_KIND,
        content: change.newValues[0]?.sharedModel.getSource() ?? ''
      }).then(response => this._applyDiagnostics(response.diagnostics));

      const cellWidget = this._panel.content.widgets[change.newIndex];
      if (cellWidget) {
        this._watchCell(cellWidget);
      }
    } else if (change.type === 'remove') {
      void postEvent('remove_cell', this._notebookId, {
        position: change.oldIndex
      }).then(response => this._applyDiagnostics(response.diagnostics));
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
    void postEvent('run_cell', this._notebookId, { cell_index: index }).then(
      response => this._applyDiagnostics(response.diagnostics)
    );
  }

  private _applyDiagnostics(diagnostics?: INBSynthDiagnostic[]): void {
    if (!diagnostics) {
      return;
    }

    this._panel.content.widgets.forEach(cellWidget => {
      const view = getEditorView(cellWidget.editor);
      if (view) {
        diagnosticsStore.clear(view);
      }
    });

    for (const cellDiagnostic of diagnostics) {
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
