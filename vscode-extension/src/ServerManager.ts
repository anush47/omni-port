import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";
import * as http from "http";
import * as https from "https";

export class ServerManager {
  private process: cp.ChildProcess | null = null;
  private readonly extensionPath: string;
  private _output: vscode.OutputChannel;

  constructor(extensionPath: string) {
    this.extensionPath = extensionPath;
    this._output = vscode.window.createOutputChannel("OmniPort Server");
  }

  get baseUrl(): string {
    return vscode.workspace
      .getConfiguration("omniport")
      .get<string>("backendUrl", "http://localhost:7890/api/v1")
      .replace(/\/$/, "");
  }

  private _get(url: string): Promise<boolean> {
    return new Promise((resolve) => {
      const lib = url.startsWith("https") ? https : http;
      const req = lib.get(url, (res) => resolve((res.statusCode ?? 0) < 500));
      req.on("error", () => resolve(false));
      req.setTimeout(1500, () => { req.destroy(); resolve(false); });
    });
  }

  async isRunning(): Promise<boolean> {
    return this._get(`${this.baseUrl}/health`);
  }

  async sendConfig(data: Record<string, string>): Promise<void> {
    const url = `${this.baseUrl}/config`;
    const body = JSON.stringify(data);
    return new Promise((resolve) => {
      const lib = url.startsWith("https") ? https : http;
      const u = new URL(url);
      const req = lib.request(
        { hostname: u.hostname, port: u.port, path: u.pathname, method: "POST",
          headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } },
        () => resolve()
      );
      req.on("error", () => resolve());
      req.setTimeout(3000, () => { req.destroy(); resolve(); });
      req.write(body);
      req.end();
    });
  }

  async ensureRunning(): Promise<void> {
    const cfg          = vscode.workspace.getConfiguration("omniport");
    const provider     = cfg.get<string>("provider", "openai");
    const isAzure      = provider === "azure";
    const azureKey     = cfg.get<string>("azureApiKey", "");
    const azureEndpoint= cfg.get<string>("azureEndpoint", "");
    const openaiKey    = cfg.get<string>("openaiApiKey", "");

    if (await this.isRunning()) {
      // Server already up — push current VS Code settings so backend reflects latest config
      await this._pushStartupConfig(cfg, provider, isAzure, azureKey, azureEndpoint, openaiKey);
      return;
    }

    const javaHome    = cfg.get<string>("javaHome", "");
    const python      = cfg.get<string>("pythonPath", "python3");
    const projectRoot = path.dirname(this.extensionPath);

    if (isAzure && (!azureKey || !azureEndpoint)) {
      const action = await vscode.window.showWarningMessage(
        "OmniPort: Azure API key and endpoint are required.", "Open Settings"
      );
      if (action === "Open Settings") {
        vscode.commands.executeCommand("workbench.action.openSettings", "omniport.azureApiKey");
      }
      throw new Error("Azure credentials not configured");
    }

    if (!isAzure && !openaiKey) {
      const action = await vscode.window.showWarningMessage(
        "OmniPort: OpenAI API key is not set.", "Open Settings"
      );
      if (action === "Open Settings") {
        vscode.commands.executeCommand("workbench.action.openSettings", "omniport.openaiApiKey");
      }
      throw new Error("OPENAI_API_KEY not configured");
    }

    const env: NodeJS.ProcessEnv = {
      ...process.env,
      FAST_MODEL_NAME:      cfg.get<string>("fastModel", "gpt-4o-mini"),
      BALANCED_MODEL_NAME:  cfg.get<string>("balancedModel", "gpt-4o"),
      REASONING_MODEL_NAME: cfg.get<string>("reasoningModel", "o1-preview"),
    };

    if (isAzure) {
      env["AZURE_OPENAI_API_KEY"]  = azureKey;
      env["AZURE_OPENAI_ENDPOINT"] = azureEndpoint;
      env["OPENAI_API_VERSION"]    = cfg.get<string>("azureApiVersion", "2024-02-15-preview");
    } else {
      env["OPENAI_API_KEY"] = openaiKey;
      const baseUrl = cfg.get<string>("openaiBaseUrl", "");
      if (baseUrl) env["OPENAI_BASE_URL"] = baseUrl;
    }

    if (javaHome) env["JAVA_HOME"] = javaHome;

    // Derive the port from backendUrl for the local server process
    const backendUrl = this.baseUrl;
    const portMatch = backendUrl.match(/:(\d+)/);
    if (portMatch) env["OMNIPORT_PORT"] = portMatch[1];

    this._output.appendLine(`[omniport] Starting backend: ${python} server/app.py`);
    this.process = cp.spawn(python, ["server/app.py"], {
      cwd: projectRoot,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    this.process.stdout?.on("data", (d) => this._output.append(d.toString()));
    this.process.stderr?.on("data", (d) => this._output.append(d.toString()));
    this.process.on("exit", (code) => {
      this._output.appendLine(`[omniport] Server exited with code ${code}`);
      this.process = null;
    });

    for (let i = 0; i < 16; i++) {
      await new Promise((r) => setTimeout(r, 500));
      if (await this.isRunning()) {
        this._output.appendLine(`[omniport] Server ready at ${this.baseUrl}`);
        // Push config to backend so runtime values take effect immediately
        await this._pushStartupConfig(cfg, provider, isAzure, azureKey, azureEndpoint, openaiKey);
        return;
      }
    }
    throw new Error("OmniPort backend failed to start within 8 seconds");
  }

  private async _pushStartupConfig(
    cfg: vscode.WorkspaceConfiguration,
    provider: string, isAzure: boolean,
    azureKey: string, azureEndpoint: string, openaiKey: string
  ): Promise<void> {
    const data: Record<string, string> = {
      provider,
      fast_model:      cfg.get<string>("fastModel", "gpt-4o-mini"),
      balanced_model:  cfg.get<string>("balancedModel", "gpt-4o"),
      reasoning_model: cfg.get<string>("reasoningModel", "o1-preview"),
      microservices_url: cfg.get<string>("microservicesUrl", "http://localhost:8080"),
    };
    if (isAzure) {
      data["azure_api_key"]    = azureKey;
      data["azure_endpoint"]   = azureEndpoint;
      data["azure_api_version"]= cfg.get<string>("azureApiVersion", "2024-02-15-preview");
    } else {
      data["openai_api_key"]  = openaiKey;
      const base = cfg.get<string>("openaiBaseUrl", "");
      if (base) data["openai_base_url"] = base;
    }
    await this.sendConfig(data);
  }

  dispose(): void {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this._output.dispose();
  }
}
