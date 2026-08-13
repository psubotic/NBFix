import * as vscode from 'vscode';
import {Events} from './events';
import { ServerHandler } from './server_handler';
import * as constants from './constants'

function activate(context: vscode.ExtensionContext) {
	let nbfixDiagnostics = vscode.languages.createDiagnosticCollection("NBFix");
	context.subscriptions.push(nbfixDiagnostics);
	let notebookEvents = new Events(new ServerHandler(nbfixDiagnostics));
	vscode.workspace.onDidOpenNotebookDocument(async (notebook_doc) => notebookEvents.openNotebook(notebook_doc, context.extensionPath + constants.SERVER_PATH));
	vscode.workspace.onDidChangeNotebookDocument(async (event) => notebookEvents.changeNotebook(event));
	vscode.workspace.onDidCloseNotebookDocument(async (notebook_doc) => notebookEvents.closeNotebook(notebook_doc));
	vscode.workspace.notebookDocuments.forEach(notebook_doc => {
        notebookEvents.openNotebook(notebook_doc, context.extensionPath + constants.SERVER_PATH);
    })
	context.subscriptions.push(vscode.commands.registerCommand("nbfixvscode.filterResults", async() => notebookEvents.chooseAnalyses()));
	vscode.window.onDidChangeNotebookEditorSelection(async (notebookEditorChange) => notebookEvents.changeCellCode(notebookEditorChange));
}

function deactivate() {}

module.exports = {
	activate,
	deactivate
};
