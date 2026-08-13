import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { ICommandPalette, Notification } from '@jupyterlab/apputils';
import { IEditorExtensionRegistry } from '@jupyterlab/codemirror';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { NotebookSessionManager } from './manager';
import { registerNBFixLinter } from './linter';

namespace CommandIDs {
  export const checkCell = 'nbfix:check-cell-for-bugs';
  export const checkNotebook = 'nbfix:check-notebook-for-bugs';
}

/**
 * Initialization data for the jupyterlab-nbfix extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab-nbfix:plugin',
  description: 'Live NBFix notebook diagnostics inside JupyterLab.',
  autoStart: true,
  requires: [INotebookTracker, IEditorExtensionRegistry, ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    editorExtensionRegistry: IEditorExtensionRegistry,
    palette: ICommandPalette
  ) => {
    registerNBFixLinter(editorExtensionRegistry);

    const managers = new WeakMap<NotebookPanel, NotebookSessionManager>();

    tracker.widgetAdded.connect((_sender, panel) => {
      const manager = new NotebookSessionManager(panel);
      managers.set(panel, manager);
      void manager.start().catch(error => {
        console.error('nbfix: failed to start notebook session', error);
      });
    });

    const { commands } = app;

    commands.addCommand(CommandIDs.checkNotebook, {
      label: 'NBFix: Check Notebook for Bugs',
      iconClass: 'jp-nbfix-icon',
      isEnabled: () => !!tracker.currentWidget,
      execute: () => {
        const panel = tracker.currentWidget;
        const manager = panel && managers.get(panel);
        if (!manager) {
          return;
        }
        Notification.promise(manager.checkNotebookForBugs(), {
          pending: { message: 'NBFix: checking notebook for bugs…' },
          success: { message: (count: unknown) => `NBFix: check complete - ${count} finding(s).` },
          error: { message: (reason: unknown) => `NBFix: check failed - ${reason}` }
        });
      }
    });

    commands.addCommand(CommandIDs.checkCell, {
      label: 'NBFix: Check Cell for Bugs',
      iconClass: 'jp-nbfix-icon',
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
          pending: { message: 'NBFix: checking cell for bugs…' },
          success: { message: (count: unknown) => `NBFix: check complete - ${count} finding(s).` },
          error: { message: (reason: unknown) => `NBFix: check failed - ${reason}` }
        });
      }
    });

    palette.addItem({ command: CommandIDs.checkNotebook, category: 'NBFix' });
    palette.addItem({ command: CommandIDs.checkCell, category: 'NBFix' });
  }
};

export default plugin;
