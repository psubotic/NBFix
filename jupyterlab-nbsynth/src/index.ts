import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { IEditorExtensionRegistry } from '@jupyterlab/codemirror';
import { INotebookTracker } from '@jupyterlab/notebook';

import { NotebookSessionManager } from './manager';
import { registerNBSynthLinter } from './linter';

/**
 * Initialization data for the jupyterlab-nbsynth extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab-nbsynth:plugin',
  description: 'Live NBSynth notebook diagnostics inside JupyterLab.',
  autoStart: true,
  requires: [INotebookTracker, IEditorExtensionRegistry],
  activate: (
    _app: JupyterFrontEnd,
    tracker: INotebookTracker,
    editorExtensionRegistry: IEditorExtensionRegistry
  ) => {
    registerNBSynthLinter(editorExtensionRegistry);

    tracker.widgetAdded.connect((_sender, panel) => {
      const manager = new NotebookSessionManager(panel);
      void manager.start().catch(error => {
        console.error('nbsynth: failed to start notebook session', error);
      });
    });
  }
};

export default plugin;
