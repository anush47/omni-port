import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { ServerManager } from "./ServerManager";

interface BackportJob {
  jobId: string;
  targetRepo: string;
}

export class BackportPanel implements vscode.WebviewViewProvider {
  public static readonly viewType = "omniport.panel";

  private _view?: vscode.WebviewView;
  private _currentJob?: BackportJob;
  private readonly _extensionUri: vscode.Uri;
  private readonly _server: ServerManager;

  // Stores pre-patch file contents for diff view (path → content)
  private _preApplySnapshots: Map<string, string> = new Map();

  constructor(extensionUri: vscode.Uri, server: ServerManager) {
    this._extensionUri = extensionUri;
    this._server = server;
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this._extensionUri, "src", "media")],
    };
    webviewView.webview.html = this._getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.command) {
        case "pickFolder":
          await this._pickFolder(msg.field);
          break;
        case "startBackport":
          await this._startBackport(msg.data);
          break;
        case "openSettings":
          vscode.commands.executeCommand("workbench.action.openSettings", "omniport");
          break;
      }
    });
  }

  private async _pickFolder(field: string): Promise<void> {
    const uris = await vscode.window.showOpenDialog({
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
      openLabel: "Select Repository",
    });
    if (uris && uris.length > 0) {
      this._view?.webview.postMessage({ command: "folderPicked", field, path: uris[0].fsPath });
    }
  }

  private async _startBackport(data: Record<string, string>): Promise<void> {
    try {
      await this._server.ensureRunning();
    } catch (err: unknown) {
      this._post("error", { message: String(err) });
      return;
    }

    const targetRepo = data.targetRepo || data.mainlineRepo;
    this._currentJob = undefined;
    this._preApplySnapshots.clear();
    this._post("log", { phase: "setup", status: "connecting", message: "Connecting to backend..." });

    const body = JSON.stringify({
      mainline_repo: data.mainlineRepo,
      commit: data.commit || undefined,
      patch_text: data.patchText || undefined,
      target_repo: data.useOtherRepo === "true" ? data.targetRepo : undefined,
      target_branch: data.targetBranch,
      build_cmd: data.buildCmd || undefined,
      test_cmd: data.testCmd || undefined,
      max_retries: 3,
    });

    const res = await fetch(`${this._server.baseUrl}/api/backport`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    if (!res.ok) {
      this._post("error", { message: `Backend error: ${await res.text()}` });
      return;
    }

    const { job_id } = await res.json() as { job_id: string };
    this._currentJob = { jobId: job_id, targetRepo };

    this._post("jobStarted", { jobId: job_id });
    this._streamJob(job_id, targetRepo);
  }

  private _streamJob(jobId: string, targetRepo: string): void {
    const url = `${this._server.baseUrl}/api/backport/${jobId}/stream`;

    // We use the node http module via fetch for SSE
    const stream = async () => {
      const response = await fetch(url);
      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              this._post("log", event);

              if (event.status === "complete") {
                this._onComplete(jobId, targetRepo, event.validation_passed);
              }
            } catch {
              // malformed line — skip
            }
          }
        }
      }
    };

    stream().catch((err) => this._post("error", { message: String(err) }));
  }

  private async _onComplete(jobId: string, targetRepo: string, passed: boolean): Promise<void> {
    if (!passed) return;

    // Notify the apply endpoint (pipeline already wrote to disk)
    await fetch(`${this._server.baseUrl}/api/backport/${jobId}/apply`, { method: "POST" });

    this._post("log", { status: "diff_ready", message: "Opening diff view..." });

    // Open VSCode diff for each changed file (captured via git diff --cached earlier)
    const resultRes = await fetch(`${this._server.baseUrl}/api/backport/${jobId}/result`);
    if (!resultRes.ok) return;
    const { patch } = await resultRes.json() as { patch: string };

    const changedFiles = this._parseFilesFromPatch(patch);
    if (changedFiles.length === 0) {
      vscode.window.showInformationMessage("OmniPort: Backport complete — no file changes detected.");
      return;
    }

    // Register a content provider for the original (pre-patch) side
    const scheme = "omniport-original";
    const provider = new OriginalContentProvider(this._preApplySnapshots);
    const disposable = vscode.workspace.registerTextDocumentContentProvider(scheme, provider);

    for (const rel of changedFiles.slice(0, 5)) { // cap at 5 diffs
      const modified = vscode.Uri.file(path.join(targetRepo, rel));
      const original = vscode.Uri.parse(`${scheme}:${path.join(targetRepo, rel)}`);
      await vscode.commands.executeCommand(
        "vscode.diff",
        original,
        modified,
        `OmniPort: ${path.basename(rel)} (backported)`
      );
    }

    setTimeout(() => disposable.dispose(), 60_000);
    vscode.window.showInformationMessage(`OmniPort: Backport complete — ${changedFiles.length} file(s) changed.`);
  }

  private _parseFilesFromPatch(patch: string): string[] {
    const files: string[] = [];
    for (const line of patch.split("\n")) {
      const m = line.match(/^\+\+\+ b\/(.+)$/);
      if (m) files.push(m[1]);
    }
    return [...new Set(files)];
  }

  private _post(command: string, data?: Record<string, unknown>): void {
    this._view?.webview.postMessage({ command, ...data });
  }

  private _getHtml(webview: vscode.Webview): string {
    const mediaDir = vscode.Uri.joinPath(this._extensionUri, "src", "media");
    const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaDir, "panel.css"));
    const jsUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaDir, "panel.js"));
    return fs.readFileSync(
      path.join(this._extensionUri.fsPath, "src", "media", "panel.html"),
      "utf8"
    )
      .replace("{{cssUri}}", cssUri.toString())
      .replace("{{jsUri}}", jsUri.toString());
  }
}

class OriginalContentProvider implements vscode.TextDocumentContentProvider {
  constructor(private readonly snapshots: Map<string, string>) {}

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.snapshots.get(uri.fsPath) ?? "";
  }
}
