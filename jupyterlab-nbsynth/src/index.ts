import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { ICommandPalette, Notification } from '@jupyterlab/apputils';
import { IEditorExtensionRegistry } from '@jupyterlab/codemirror';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { NotebookSessionManager } from './manager';
import { registerNBSynthLinter } from './linter';

namespace CommandIDs {
  export const checkCell = 'nbsynth:check-cell-for-bugs';
  export const checkNotebook = 'nbsynth:check-notebook-for-bugs';
}

/**
 * Initialization data for the jupyterlab-nbsynth extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab-nbsynth:plugin',
  description: 'Live NBSynth notebook diagnostics inside JupyterLab.',
  autoStart: true,
  requires: [INotebookTracker, IEditorExtensionRegistry, ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    editorExtensionRegistry: IEditorExtensionRegistry,
    palette: ICommandPalette
  ) => {
    registerNBSynthLinter(editorExtensionRegistry);

    const managers = new WeakMap<NotebookPanel, NotebookSessionManager>();

    tracker.widgetAdded.connect((_sender, panel) => {
      const manager = new NotebookSessionManager(panel);
      managers.set(panel, manager);
      void manager.start().catch(error => {
        console.error('nbsynth: failed to start notebook session', error);
      });
    });

    const { commands } = app;

    commands.addCommand(CommandIDs.checkNotebook, {
      label: 'NBSynth: Check Notebook for Bugs',
      isEnabled: () => !!tracker.currentWidget,
      execute: () => {
        const panel = tracker.currentWidget;
        const manager = panel && managers.get(panel);
        if (!manager) {
          return;
        }
        Notification.promise(manager.checkNotebookForBugs(), {
          pending: { message: 'NBSynth: checking notebook for bugs…' },
          success: { message: (count: unknown) => `NBSynth: check complete - ${count} finding(s).` },
          error: { message: (reason: unknown) => `NBSynth: check failed - ${reason}` }
        });
      }
    });

    commands.addCommand(CommandIDs.checkCell, {
      label: 'NBSynth: Check Cell for Bugs',
      isEnabled: () => !!tracker.currentWidget && !!tracker.activeCell,
      execute: () => {
        const panel = tracker.currentWidget;
        const manager = panel && managers.get(panel);
        const activeCell = tracker.activeCell;
        if (!manager || !panel || !activeCell) {
          return;
        }
        const cellIndex = panel.content.widgets.indexOf(activeCell);
        if (cellIndex === -1) {
          return;
        }
        Notification.promise(manager.checkCellForBugs(cellIndex), {
          pending: { message: 'NBSynth: checking cell for bugs…' },
          success: { message: (count: unknown) => `NBSynth: check complete - ${count} finding(s).` },
          error: { message: (reason: unknown) => `NBSynth: check failed - ${reason}` }
        });
      }
    });

    palette.addItem({ command: CommandIDs.checkNotebook, category: 'NBSynth' });
    palette.addItem({ command: CommandIDs.checkCell, category: 'NBSynth' });
  }
};

export default plugin;
