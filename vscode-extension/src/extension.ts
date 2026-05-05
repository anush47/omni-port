import * as vscode from "vscode";
import { ServerManager } from "./ServerManager";
import { BackportPanel } from "./BackportPanel";

let server: ServerManager;

export function activate(context: vscode.ExtensionContext): void {
  server = new ServerManager(context.extensionPath);

  const provider = new BackportPanel(context.extensionUri, server);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(BackportPanel.viewType, provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("omniport.openPanel", () => {
      vscode.commands.executeCommand("omniport.panel.focus");
    })
  );

  context.subscriptions.push({
    dispose: () => server.dispose(),
  });
}

export function deactivate(): void {
  server?.dispose();
}
