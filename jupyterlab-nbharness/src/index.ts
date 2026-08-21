import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { Dialog, ICommandPalette, Notification, showDialog } from '@jupyterlab/apputils';
import { IEditorExtensionRegistry } from '@jupyterlab/codemirror';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';

import { AnalysesDialogBody } from './analysesDialog';
import { ANALYSIS_OPTIONS, NotebookSessionManager } from './manager';
import { registerNBHarnessLinter } from './linter';

namespace CommandIDs {
  export const checkCell = 'nbharness:check-cell-for-bugs';
  export const checkNotebook = 'nbharness:check-notebook-for-bugs';
  export const chooseActiveAnalyses = 'nbharness:choose-active-analyses';
}

/**
 * Initialization data for the jupyterlab-nbharness extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab-nbharness:plugin',
  description: 'Live NBHarness notebook diagnostics inside JupyterLab.',
  autoStart: true,
  requires: [INotebookTracker, IEditorExtensionRegistry, ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    editorExtensionRegistry: IEditorExtensionRegistry,
    palette: ICommandPalette
  ) => {
    registerNBHarnessLinter(editorExtensionRegistry);

    const managers = new WeakMap<NotebookPanel, NotebookSessionManager>();

    tracker.widgetAdded.connect((_sender, panel) => {
      const manager = new NotebookSessionManager(panel);
      managers.set(panel, manager);
      void manager.start().catch(error => {
        console.error('nbharness: failed to start notebook session', error);
      });
    });

    const { commands } = app;

    commands.addCommand(CommandIDs.checkNotebook, {
      label: 'NBHarness: Check Notebook for Bugs',
      iconClass: 'jp-nbharness-icon',
      isEnabled: () => !!tracker.currentWidget,
      execute: () => {
        const panel = tracker.currentWidget;
        const manager = panel && managers.get(panel);
        if (!manager) {
          return;
        }
        Notification.promise(manager.checkNotebookForBugs(), {
          pending: { message: 'NBHarness: checking notebook for bugs…' },
          success: { message: (count: unknown) => `NBHarness: check complete - ${count} finding(s).` },
          error: { message: (reason: unknown) => `NBHarness: check failed - ${reason}` }
        });
      }
    });

    commands.addCommand(CommandIDs.checkCell, {
      label: 'NBHarness: Check Cell for Bugs',
      iconClass: 'jp-nbharness-icon',
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
          pending: { message: 'NBHarness: checking cell for bugs…' },
          success: { message: (count: unknown) => `NBHarness: check complete - ${count} finding(s).` },
          error: { message: (reason: unknown) => `NBHarness: check failed - ${reason}` }
        });
      }
    });

    commands.addCommand(CommandIDs.chooseActiveAnalyses, {
      label: 'NBHarness: Choose Active Analyses',
      iconClass: 'jp-nbharness-icon',
      isEnabled: () => !!tracker.currentWidget,
      execute: async () => {
        const panel = tracker.currentWidget;
        const manager = panel && managers.get(panel);
        if (!manager) {
          return;
        }
        const body = new AnalysesDialogBody(ANALYSIS_OPTIONS, manager.activeAnalyses);
        const result = await showDialog<Set<string>>({
          title: 'Choose Active Analyses',
          body,
          buttons: [Dialog.cancelButton(), Dialog.okButton({ label: 'Apply' })]
        });
        if (!result.button.accept || !result.value) {
          return;
        }
        try {
          await manager.setActiveAnalyses(result.value);
        } catch (error) {
          Notification.error(`NBHarness: failed to update active analyses - ${error}`);
        }
      }
    });

    palette.addItem({ command: CommandIDs.checkNotebook, category: 'NBHarness' });
    palette.addItem({ command: CommandIDs.checkCell, category: 'NBHarness' });
    palette.addItem({ command: CommandIDs.chooseActiveAnalyses, category: 'NBHarness' });
  }
};

export default plugin;
