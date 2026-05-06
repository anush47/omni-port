import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as cp from "child_process";
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
        case "cancelJob":
          await this._cancelJob(msg.jobId);
          break;
        case "resetRepo":
          await this._resetRepo(msg.jobId);
          break;
        case "onComplete":
          break;
        case "showPatch":
          await this._showPatch(msg.patch as string);
          break;
        case "openSettings":
          vscode.commands.executeCommand("workbench.action.openSettings", "omniport");
          break;
        case "checkHealth":
          await this._checkHealth();
          break;
        case "fetchBranches":
          this._fetchBranches(msg.repo);
          break;
        case "getConfig":
          this._sendConfigToPanel();
          break;
        case "applyConfig":
          await this._applyConfig(msg.data);
          break;
        case "checkCommit":
          this._checkCommit(msg.repo, msg.commit);
          break;
        case "viewCommit":
          await this._viewCommit(msg.repo, msg.commit);
          break;
      }
    });

    // Push current config to the panel on open
    this._sendConfigToPanel();

    // If backend is already running, sync VS Code settings to it immediately
    this._server.isRunning().then((up) => {
      if (up) this._server.ensureRunning().catch(() => {});
    });
  }

  private async _checkHealth(): Promise<void> {
    try {
      const res = await fetch(`${this._server.baseUrl}/health`);
      if (res.ok) {
        const data = await res.json() as Record<string, unknown>;
        this._post("healthStatus", { connected: true, ...data });
      } else {
        this._post("healthStatus", { connected: false });
      }
    } catch {
      this._post("healthStatus", { connected: false });
    }
  }

  private _sendConfigToPanel(): void {
    const cfg = vscode.workspace.getConfiguration("omniport");
    this._post("configLoaded", {
      backendUrl:       cfg.get<string>("backendUrl", "http://localhost:7890/api/v1"),
      provider:         cfg.get<string>("provider", "openai"),
      openaiApiKey:     cfg.get<string>("openaiApiKey", ""),
      openaiBaseUrl:    cfg.get<string>("openaiBaseUrl", ""),
      azureApiKey:      cfg.get<string>("azureApiKey", ""),
      azureEndpoint:    cfg.get<string>("azureEndpoint", ""),
      azureApiVersion:  cfg.get<string>("azureApiVersion", "2024-02-15-preview"),
      fastModel:        cfg.get<string>("fastModel", "gpt-4o-mini"),
      balancedModel:    cfg.get<string>("balancedModel", "gpt-4o"),
      reasoningModel:   cfg.get<string>("reasoningModel", "o1-preview"),
      microservicesUrl: cfg.get<string>("microservicesUrl", "http://localhost:8080"),
    });
  }

  private async _applyConfig(data: Record<string, string>): Promise<void> {
    // Save to VS Code settings
    const cfg = vscode.workspace.getConfiguration("omniport");
    const target = vscode.ConfigurationTarget.Global;
    const toPromise = (t: Thenable<void>): Promise<void> => Promise.resolve(t);
    const saves = [
      toPromise(cfg.update("backendUrl",       data.backendUrl,       target)),
      toPromise(cfg.update("provider",         data.provider,         target)),
      toPromise(cfg.update("fastModel",        data.fastModel,        target)),
      toPromise(cfg.update("balancedModel",    data.balancedModel,    target)),
      toPromise(cfg.update("reasoningModel",   data.reasoningModel,   target)),
      toPromise(cfg.update("microservicesUrl", data.microservicesUrl, target)),
    ];
    if (data.provider === "azure") {
      saves.push(
        toPromise(cfg.update("azureApiKey",     data.azureApiKey,     target)),
        toPromise(cfg.update("azureEndpoint",   data.azureEndpoint,   target)),
        toPromise(cfg.update("azureApiVersion", data.azureApiVersion, target)),
      );
    } else {
      saves.push(
        toPromise(cfg.update("openaiApiKey",  data.openaiApiKey,  target)),
        toPromise(cfg.update("openaiBaseUrl", data.openaiBaseUrl, target)),
      );
    }
    await Promise.all(saves);

    // Push to running backend
    try {
      await this._server.sendConfig(data);
      this._post("configApplied", { ok: true });
      await this._checkHealth();
    } catch {
      this._post("configApplied", { ok: false });
    }
  }

  private _fetchBranches(repoPath: string): void {
    const result = cp.spawnSync("git", ["-C", repoPath, "branch", "-r"], {
      timeout: 5000, encoding: "utf8"
    });
    if (result.status !== 0 || result.error) {
      this._post("branchList", { branches: null });
      return;
    }
    const branches = (result.stdout as string)
      .split("\n")
      .map((l) => l.trim().replace(/^origin\//, "").trim())
      .filter((l) => l && !l.includes("->"))
      .filter((v, i, a) => a.indexOf(v) === i)
      .sort();
    this._post("branchList", { branches });
  }

  private async _pickFolder(field: string): Promise<void> {
    const uris = await vscode.window.showOpenDialog({
      canSelectFolders: true, canSelectFiles: false,
      canSelectMany: false, openLabel: "Select Repository",
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
      mainline_repo:   data.mainlineRepo,
      commit:          data.commit || undefined,
      patch_text:      data.patchText || undefined,
      target_repo:     data.useOtherRepo === "true" ? data.targetRepo : undefined,
      target_branch:   data.targetBranch,
      backport_commit: data.backportCommit || undefined,
      evaluate_mode:   data.evaluateMode === "true",
      build_cmd:       data.buildCmd || undefined,
      test_cmd:        data.testCmd || undefined,
      max_retries:     3,
    });

    const res = await fetch(`${this._server.baseUrl}/backport`, {
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
    const url = `${this._server.baseUrl}/backport/${jobId}/stream`;
    const stream = async (retries = 5): Promise<void> => {
      try {
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
                if (event.status === "complete" || event.status === "error" ||
                    event.status === "cancelled") {
                  return;
                }
              } catch { /* malformed line */ }
            }
          }
        }
      } catch (err: unknown) {
        const msg = String(err);
        if (retries > 0 && (msg.includes("terminated") || msg.includes("network"))) {
          await new Promise((r) => setTimeout(r, 1500));
          return stream(retries - 1);
        }
        this._post("error", { message: msg });
      }
    };
    stream();
  }

  private async _cancelJob(jobId: string): Promise<void> {
    await fetch(`${this._server.baseUrl}/backport/${jobId}/cancel`, { method: "POST" });
  }

  private async _resetRepo(jobId: string): Promise<void> {
    const res = await fetch(`${this._server.baseUrl}/backport/${jobId}/reset`, { method: "POST" });
    if (res.ok) {
      this._post("repoReset", {});
    } else {
      this._post("error", { message: `Reset failed: ${await res.text()}` });
    }
  }

  private async _onComplete(jobId: string, targetRepo: string, passed: boolean, patch: string): Promise<void> {
    if (!patch) return;
    this._post("log", { status: "diff_ready", message: "Opening diff view…" });

    const changedFiles = this._parseFilesFromPatch(patch);
    if (changedFiles.length === 0) {
      vscode.window.showInformationMessage("OmniPort: Backport complete — no file changes detected.");
      return;
    }

    const scheme = "omniport-original";
    const provider = new OriginalContentProvider(this._preApplySnapshots);
    const disposable = vscode.workspace.registerTextDocumentContentProvider(scheme, provider);

    for (const rel of changedFiles.slice(0, 5)) {
      const modified = vscode.Uri.file(path.join(targetRepo, rel));
      const original = vscode.Uri.parse(`${scheme}:${path.join(targetRepo, rel)}`);
      await vscode.commands.executeCommand(
        "vscode.diff", original, modified,
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

  private _checkCommit(repo: string, commit: string): void {
    const result = cp.spawnSync("git", ["-C", repo, "cat-file", "-e", commit], { timeout: 5000 });
    this._post("commitStatus", { valid: result.status === 0 });
  }

  private _patchShowDisposable?: vscode.Disposable;
  private _commitShowDisposable?: vscode.Disposable;
  private _patchCounter = 0;

  private async _showPatch(patch: string): Promise<void> {
    if (!patch) return;
    try {
      const scheme = "omniport-patch";
      if (this._patchShowDisposable) { this._patchShowDisposable.dispose(); }
      this._patchShowDisposable = vscode.workspace.registerTextDocumentContentProvider(scheme, {
        provideTextDocumentContent: () => patch,
      });
      const uri = vscode.Uri.parse(`${scheme}:backport-${this._patchCounter++}.diff`);
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One, preview: true });
    } catch { /* ignore */ }
  }

  private async _viewCommit(repo: string, commit: string): Promise<void> {
    try {
      const result = cp.spawnSync(
        "git", ["-C", repo, "show", "--stat", "--patch", commit],
        { timeout: 15000, encoding: "utf8", maxBuffer: 5 * 1024 * 1024 }
      );
      if (result.status !== 0 || !result.stdout) return;
      const content = result.stdout as string;
      const scheme = "omniport-show";
      if (this._commitShowDisposable) { this._commitShowDisposable.dispose(); }
      this._commitShowDisposable = vscode.workspace.registerTextDocumentContentProvider(scheme, {
        provideTextDocumentContent: () => content,
      });
      const uri = vscode.Uri.parse(`${scheme}:${commit.slice(0, 8)}.diff`);
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One, preview: true, preserveFocus: true });
    } catch { /* ignore */ }
  }

  private _post(command: string, data?: Record<string, unknown>): void {
    this._view?.webview.postMessage({ command, ...data });
  }

  private _getHtml(webview: vscode.Webview): string {
    const mediaDir = vscode.Uri.joinPath(this._extensionUri, "src", "media");
    const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaDir, "panel.css"));
    const jsUri  = webview.asWebviewUri(vscode.Uri.joinPath(mediaDir, "panel.js"));
    return fs.readFileSync(
      path.join(this._extensionUri.fsPath, "src", "media", "panel.html"), "utf8"
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
