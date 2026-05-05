import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";
import * as http from "http";

export class ServerManager {
  private process: cp.ChildProcess | null = null;
  private readonly extensionPath: string;
  private _output: vscode.OutputChannel;

  constructor(extensionPath: string) {
    this.extensionPath = extensionPath;
    this._output = vscode.window.createOutputChannel("OmniPort Server");
  }

  get port(): number {
    return vscode.workspace.getConfiguration("omniport").get<number>("serverPort", 7890);
  }

  get baseUrl(): string {
    return `http://127.0.0.1:${this.port}`;
  }

  async isRunning(): Promise<boolean> {
    return new Promise((resolve) => {
      const req = http.get(`${this.baseUrl}/api/health`, (res) => {
        resolve(res.statusCode === 200);
      });
      req.on("error", () => resolve(false));
      req.setTimeout(1500, () => { req.destroy(); resolve(false); });
    });
  }

  async ensureRunning(): Promise<void> {
    if (await this.isRunning()) return;

    const cfg = vscode.workspace.getConfiguration("omniport");
    const provider    = cfg.get<string>("provider", "openai");
    const javaHome    = cfg.get<string>("javaHome", "");
    const python      = cfg.get<string>("pythonPath", "python3");
    const projectRoot = path.dirname(this.extensionPath);

    // Validate that the right key is present for the chosen provider
    const isAzure = provider === "azure";
    const azureKey      = cfg.get<string>("azureApiKey", "");
    const azureEndpoint = cfg.get<string>("azureEndpoint", "");
    const openaiKey     = cfg.get<string>("openaiApiKey", "");

    if (isAzure && (!azureKey || !azureEndpoint)) {
      const action = await vscode.window.showWarningMessage(
        "OmniPort: Azure API key and endpoint are required.",
        "Open Settings"
      );
      if (action === "Open Settings") {
        vscode.commands.executeCommand("workbench.action.openSettings", "omniport.azureApiKey");
      }
      throw new Error("Azure credentials not configured");
    }

    if (!isAzure && !openaiKey) {
      const action = await vscode.window.showWarningMessage(
        "OmniPort: OpenAI API key is not set.",
        "Open Settings"
      );
      if (action === "Open Settings") {
        vscode.commands.executeCommand("workbench.action.openSettings", "omniport.openaiApiKey");
      }
      throw new Error("OPENAI_API_KEY not configured");
    }

    // Build env — mirrors the variables llm_router.py reads
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      OMNIPORT_PORT:      String(this.port),
      FAST_MODEL_NAME:    cfg.get<string>("fastModel", "gpt-4o-mini"),
      BALANCED_MODEL_NAME:cfg.get<string>("balancedModel", "gpt-4o"),
      REASONING_MODEL_NAME:cfg.get<string>("reasoningModel", "o1-preview"),
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

    // Wait up to 8s for the server to be ready
    for (let i = 0; i < 16; i++) {
      await new Promise((r) => setTimeout(r, 500));
      if (await this.isRunning()) {
        this._output.appendLine(`[omniport] Server ready on port ${this.port}`);
        return;
      }
    }
    throw new Error("OmniPort backend failed to start within 8 seconds");
  }

  dispose(): void {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this._output.dispose();
  }
}
