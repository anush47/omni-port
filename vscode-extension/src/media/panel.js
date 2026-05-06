/* global acquireVsCodeApi */
const vscode = acquireVsCodeApi();

// ── State ────────────────────────────────────────────────────────────────────
let activeTab = "commit";
let activeProvider = "openai";
let useOtherRepo = false;
let running = false;
let currentJobId = null;
let _activeSpinner = null;
let _lastPatch = null;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const form = document.getElementById("backportForm");
const runBtn = document.getElementById("runBtn");
const stopBtn = document.getElementById("stopBtn");
const resetBtn = document.getElementById("resetBtn");
const logPanel = document.getElementById("logPanel");
const logBody = document.getElementById("logBody");
const resultBanner = document.getElementById("resultBanner");
const bannerText = document.getElementById("bannerText");
const targetRepoFld = document.getElementById("targetRepoField");
const advancedBody = document.getElementById("advancedBody");
const advancedToggle = document.getElementById("advancedToggle");
const chevron = advancedToggle.querySelector(".chevron");
const statusDot = document.getElementById("statusDot");
const targetBranchInput = document.getElementById("targetBranch");
const branchDrop = document.getElementById("branchDrop");
const branchHint = document.getElementById("branchHint");

// ── Config section ────────────────────────────────────────────────────────────
const configToggle = document.getElementById("configToggle");
const configBody = document.getElementById("configBody");
const configChevron = configToggle.querySelector(".chevron");

configToggle.addEventListener("click", () => {
  const open = configBody.classList.toggle("open");
  configChevron.classList.toggle("open", open);
});

// Provider tab switching inside config
document.querySelectorAll("#providerTabs .tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activeProvider = tab.dataset.provider;
    document.querySelectorAll("#providerTabs .tab").forEach((t) =>
      t.classList.toggle("active", t === tab)
    );
    const isAzure = activeProvider === "azure";
    document.getElementById("cfgOpenaiKeyField").classList.toggle("hidden", isAzure);
    document.getElementById("cfgOpenaiBaseUrlField").classList.toggle("hidden", isAzure);
    document.getElementById("cfgAzureKeyField").classList.toggle("hidden", !isAzure);
    document.getElementById("cfgAzureEndpointField").classList.toggle("hidden", !isAzure);
    document.getElementById("cfgAzureVersionField").classList.toggle("hidden", !isAzure);
  });
});

document.getElementById("applyConfigBtn").addEventListener("click", () => {
  const data = {
    backendUrl: document.getElementById("cfgBackendUrl").value.trim(),
    provider: activeProvider,
    openaiApiKey: document.getElementById("cfgApiKey").value.trim(),
    openaiBaseUrl: document.getElementById("cfgBaseUrl").value.trim(),
    azureApiKey: document.getElementById("cfgAzureKey").value.trim(),
    azureEndpoint: document.getElementById("cfgAzureEndpoint").value.trim(),
    azureApiVersion: document.getElementById("cfgAzureVersion").value.trim(),
    fastModel: document.getElementById("cfgFastModel").value.trim(),
    balancedModel: document.getElementById("cfgBalancedModel").value.trim(),
    reasoningModel: document.getElementById("cfgReasoningModel").value.trim(),
    microservicesUrl: document.getElementById("cfgMicroservicesUrl").value.trim(),
    datasetPath: document.getElementById("cfgDatasetPath").value.trim(),
    testApply: document.getElementById("cfgTestApply").checked,
    backportCommit: document.getElementById("cfgBackportCommit").value.trim(),
  };
  vscode.postMessage({ command: "applyConfig", data });
  document.getElementById("applyConfigBtn").textContent = "Applying…";
});

// ── Refresh status ────────────────────────────────────────────────────────────
document.getElementById("refreshBtn").addEventListener("click", () => {
  vscode.postMessage({ command: "checkHealth" });
});

// ── Button starts disabled until backend + inputs are ready ──────────────────
runBtn.disabled = true;

// ── Tab switching (source) ────────────────────────────────────────────────────
document.querySelectorAll("#sourceTabs .tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activeTab = tab.dataset.tab;
    document.querySelectorAll("#sourceTabs .tab").forEach((t) =>
      t.classList.toggle("active", t === tab)
    );
    document.querySelectorAll(".tab-content").forEach((el) =>
      el.classList.toggle("active", el.dataset.tab === activeTab)
    );
    _updateRunBtn();
  });
});

// Watch the three required fields
["mainlineRepo", "commit", "patchText"].forEach((id) => {
  document.getElementById(id).addEventListener("input", _updateRunBtn);
});
targetBranchInput.addEventListener("input", _updateRunBtn);
// Also fire when a branch is picked from the dropdown
branchDrop.addEventListener("mousedown", () => setTimeout(_updateRunBtn, 0));

// ── Repo mode toggle ──────────────────────────────────────────────────────────
document.querySelectorAll("input[name='repoMode']").forEach((radio) => {
  radio.addEventListener("change", () => {
    useOtherRepo = radio.value === "other";
    targetRepoFld.classList.toggle("hidden", !useOtherRepo);
    _allBranches = [];
    branchDrop.classList.add("hidden");
    if (!useOtherRepo) scheduleBranchFetch();
  });
});

// ── Branch combobox ───────────────────────────────────────────────────────────
let _allBranches = [];
let _branchTimer = null;

function getTargetBranch() { return targetBranchInput.value.trim(); }

function _repoForBranch() {
  return useOtherRepo
    ? document.getElementById("targetRepo").value.trim()
    : document.getElementById("mainlineRepo").value.trim();
}

function _renderBranchDrop(filter) {
  const q = (filter || "").toLowerCase();
  const hits = q ? _allBranches.filter(b => b.toLowerCase().includes(q)) : _allBranches;
  if (!hits.length) { branchDrop.classList.add("hidden"); return; }
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const hi = s => q
    ? s.replace(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
      m => `<mark>${esc(m)}</mark>`)
    : esc(s);
  branchDrop.innerHTML = hits.map(b =>
    `<div class="combobox-item" data-value="${esc(b)}">${hi(b)}</div>`
  ).join("");
  branchDrop.classList.remove("hidden");
}

targetBranchInput.addEventListener("focus", () => {
  if (_allBranches.length) _renderBranchDrop(targetBranchInput.value);
  else scheduleBranchFetch();
});
targetBranchInput.addEventListener("input", () => {
  if (_allBranches.length) _renderBranchDrop(targetBranchInput.value);
});
targetBranchInput.addEventListener("blur", () => {
  setTimeout(() => branchDrop.classList.add("hidden"), 150);
});
branchDrop.addEventListener("mousedown", (e) => {
  const item = e.target.closest(".combobox-item");
  if (!item) return;
  e.preventDefault();
  targetBranchInput.value = item.dataset.value;
  branchDrop.classList.add("hidden");
});

function scheduleBranchFetch() {
  const repo = _repoForBranch();
  if (!repo) { _allBranches = []; branchDrop.classList.add("hidden"); return; }
  branchHint.textContent = "Loading branches…";
  branchHint.classList.remove("hidden");
  clearTimeout(_branchTimer);
  _branchTimer = setTimeout(() => {
    vscode.postMessage({ command: "fetchBranches", repo });
  }, 400);
}

document.getElementById("mainlineRepo").addEventListener("input", () => {
  if (!useOtherRepo) scheduleBranchFetch();
});
document.getElementById("targetRepo").addEventListener("input", () => {
  if (useOtherRepo) scheduleBranchFetch();
});

// ── Commit validation ─────────────────────────────────────────────────────────
const commitInput = document.getElementById("commit");
const commitCheckEl = document.getElementById("commitCheck");
const commitCheckIcon = document.getElementById("commitCheckIcon");
const commitCheckMsg = document.getElementById("commitCheckMsg");
const viewCommitBtn = document.getElementById("viewCommitBtn");
let _commitTimer = null;

commitInput.addEventListener("input", () => {
  clearTimeout(_commitTimer);
  commitCheckEl.classList.add("hidden");
  const sha = commitInput.value.trim();
  if (sha.length < 7) return;
  _commitTimer = setTimeout(() => {
    const repo = document.getElementById("mainlineRepo").value.trim();
    if (!repo) return;
    vscode.postMessage({ command: "checkCommit", repo, commit: sha });
  }, 600);
});

viewCommitBtn.addEventListener("click", () => {
  const repo = document.getElementById("mainlineRepo").value.trim();
  const sha = commitInput.value.trim();
  if (repo && sha) vscode.postMessage({ command: "viewCommit", repo, commit: sha });
});

// ── Health check ──────────────────────────────────────────────────────────────
function requestHealth() {
  vscode.postMessage({ command: "checkHealth" });
}

let _backendConnected = false;

function _updateRunBtn() {
  if (running) return;
  const hasRepo = !!document.getElementById("mainlineRepo").value.trim();
  const hasBranch = !!getTargetBranch();
  const hasSource = activeTab === "commit"
    ? !!document.getElementById("commit").value.trim()
    : !!document.getElementById("patchText").value.trim();
  runBtn.disabled = !(_backendConnected && hasRepo && hasBranch && hasSource);
}

function updateStatusDot(connected, data) {
  _backendConnected = connected;
  _updateRunBtn();
  statusDot.className = "status-dot " + (
    !connected ? "status-error" :
      !data.api_key_configured ? "status-warn" :
        "status-ok"
  );

  const port = data.port ? `:${data.port}` : "";
  document.getElementById("spBackend").textContent = connected ? `online${port}` : "offline";
  document.getElementById("spProvider").textContent = data.provider || "—";
  document.getElementById("spFast").textContent = data.fast_model || "—";
  document.getElementById("spBalanced").textContent = data.balanced_model || "—";
  document.getElementById("spReasoning").textContent = data.reasoning_model || "—";

  const msOk = data.microservices_ok;
  const msUrl = data.microservices_url || "";
  document.getElementById("spMicroservices").textContent =
    msOk === undefined ? "—" :
      msOk ? `ok  ${msUrl}` : `unreachable  ${msUrl}`;
  document.getElementById("spMicroservices").style.color =
    msOk === undefined ? "" : msOk ? "var(--accent)" : "var(--warn)";
}

requestHealth();
setInterval(requestHealth, 20_000);

// ── Advanced collapsible ──────────────────────────────────────────────────────
advancedToggle.addEventListener("click", () => {
  const open = advancedBody.classList.toggle("open");
  chevron.classList.toggle("open", open);
});

// ── Folder pickers ────────────────────────────────────────────────────────────
document.querySelectorAll("[data-pick]").forEach((btn) => {
  btn.addEventListener("click", () => {
    vscode.postMessage({ command: "pickFolder", field: btn.dataset.pick });
  });
});

document.querySelectorAll("[data-pick-file]").forEach((btn) => {
  btn.addEventListener("click", () => {
    vscode.postMessage({ command: "pickFile", field: btn.dataset.pickFile });
  });
});

// ── Settings button ───────────────────────────────────────────────────────────
document.getElementById("settingsBtn").addEventListener("click", () => {
  vscode.postMessage({ command: "openSettings" });
});

// ── Clear log ─────────────────────────────────────────────────────────────────
document.getElementById("clearLogBtn").addEventListener("click", () => {
  logBody.innerHTML = "";
  logPanel.classList.add("hidden");
  hideBanner();
});

// ── Stop button ───────────────────────────────────────────────────────────────
stopBtn.addEventListener("click", () => {
  if (!currentJobId) return;
  vscode.postMessage({ command: "cancelJob", jobId: currentJobId });
  stopBtn.disabled = true;
  stopBtn.textContent = "Stopping…";
  appendLog("warn", "Cancellation requested — waiting for current step to finish…");
});

// ── Reset button ──────────────────────────────────────────────────────────────
resetBtn.addEventListener("click", () => {
  if (!currentJobId) return;
  resetBtn.disabled = true;
  resetBtn.textContent = "Resetting…";
  vscode.postMessage({ command: "resetRepo", jobId: currentJobId });
});

// ── View diff button (banner) ─────────────────────────────────────────────────
document.getElementById("bannerViewDiffBtn").addEventListener("click", () => {
  if (_lastPatch) vscode.postMessage({ command: "showPatch", patch: _lastPatch });
});

// ── Form submit ───────────────────────────────────────────────────────────────
form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (running) return;

  const data = {
    mainlineRepo: document.getElementById("mainlineRepo").value.trim(),
    commit: activeTab === "commit" ? document.getElementById("commit").value.trim() : "",
    patchText: activeTab === "patch" ? document.getElementById("patchText").value.trim() : "",
    targetRepo: document.getElementById("targetRepo").value.trim(),
    targetBranch: getTargetBranch(),
    backportCommit: document.getElementById("cfgBackportCommit").value.trim(),
    evaluateMode: String(document.getElementById("cfgTestApply").checked),
    buildCmd: document.getElementById("buildCmd").value.trim(),
    testCmd: document.getElementById("testCmd").value.trim(),
    useOtherRepo: String(useOtherRepo),
  };

  vscode.postMessage({ command: "startBackport", data });
  setRunning(true);
  resetLog();
});

// ── Message handler from extension host ──────────────────────────────────────
window.addEventListener("message", (e) => {
  const msg = e.data;
  switch (msg.command) {
    case "healthStatus":
      updateStatusDot(msg.connected, msg);
      break;
    case "folderPicked":
      document.getElementById(msg.field).value = msg.path;
      if ((msg.field === "mainlineRepo" && !useOtherRepo) ||
        (msg.field === "targetRepo" && useOtherRepo)) scheduleBranchFetch();
      break;
    case "branchList":
      branchHint.classList.add("hidden");
      if (!msg.branches || msg.branches.length === 0) {
        _allBranches = [];
        branchHint.textContent = "No branches found — type manually";
        branchHint.classList.remove("hidden");
        break;
      }
      _allBranches = msg.branches;
      // Only open dropdown if the branch input is currently focused
      if (document.activeElement === targetBranchInput) {
        _renderBranchDrop(targetBranchInput.value);
      }
      break;
    case "commitStatus":
      commitCheckEl.classList.remove("hidden");
      if (msg.valid) {
        commitCheckMsg.textContent = "";
        viewCommitBtn.classList.remove("hidden");
        // Auto-populate backport commit if provided and evaluate is on
        if (msg.backportCommit && document.getElementById("cfgTestApply").checked) {
          document.getElementById("cfgBackportCommit").value = msg.backportCommit;
        }
      } else {
        commitCheckIcon.textContent = "✗";
        commitCheckIcon.className = "commit-icon-err";
        commitCheckMsg.textContent = "Commit not found in repository";
        viewCommitBtn.classList.add("hidden");
      }
      break;
    case "configLoaded":
      populateConfig(msg);
      break;
    case "configApplied":
      document.getElementById("applyConfigBtn").textContent = msg.ok ? "Applied ✓" : "Apply failed ✗";
      setTimeout(() => {
        document.getElementById("applyConfigBtn").textContent = "Apply";
      }, 2000);
      break;
    case "jobStarted":
      currentJobId = msg.jobId;
      appendLog("info", `Connected to backend (Job ID: ${msg.jobId})`);
      break;
    case "log":
      handleLogEvent(msg);
      break;
    case "error":
      _resolveSpinner("fail", null);
      appendLog("fail", msg.message || "Unknown error");
      showBanner(false, msg.message || "Error occurred", false, false);
      setRunning(false);
      break;
    case "repoReset":
      resetBtn.disabled = false;
      resetBtn.textContent = "Reset Repository";
      appendLog("ok", "Repository reset to original state");
      break;
  }
});

// ── Config population ─────────────────────────────────────────────────────────
function populateConfig(cfg) {
  document.getElementById("cfgBackendUrl").value = cfg.backendUrl || "";
  document.getElementById("cfgApiKey").value = cfg.openaiApiKey || "";
  document.getElementById("cfgBaseUrl").value = cfg.openaiBaseUrl || "";
  document.getElementById("cfgAzureKey").value = cfg.azureApiKey || "";
  document.getElementById("cfgAzureEndpoint").value = cfg.azureEndpoint || "";
  document.getElementById("cfgAzureVersion").value = cfg.azureApiVersion || "";
  document.getElementById("cfgFastModel").value = cfg.fastModel || "";
  document.getElementById("cfgBalancedModel").value = cfg.balancedModel || "";
  document.getElementById("cfgReasoningModel").value = cfg.reasoningModel || "";
  document.getElementById("cfgMicroservicesUrl").value = cfg.microservicesUrl || "";
  document.getElementById("cfgDatasetPath").value = cfg.datasetPath || "";
  document.getElementById("cfgBackportCommit").value = cfg.backportCommit || "";
  document.getElementById("cfgTestApply").checked = cfg.testApply !== false; // default true

  activeProvider = cfg.provider || "openai";
  document.querySelectorAll("#providerTabs .tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.provider === activeProvider)
  );
  const isAzure = activeProvider === "azure";
  document.getElementById("cfgOpenaiKeyField").classList.toggle("hidden", isAzure);
  document.getElementById("cfgOpenaiBaseUrlField").classList.toggle("hidden", isAzure);
  document.getElementById("cfgAzureKeyField").classList.toggle("hidden", !isAzure);
  document.getElementById("cfgAzureEndpointField").classList.toggle("hidden", !isAzure);
  document.getElementById("cfgAzureVersionField").classList.toggle("hidden", !isAzure);
}

// ── Log rendering ─────────────────────────────────────────────────────────────
function handleLogEvent(event) {
  const { phase, status, agent, message, error, validation_passed,
    repair_status, routing_decision, attempt, via, patch } = event;

  // Direct apply phase
  if (phase === "phase0") {
    switch (status) {
      case "checking":
        appendLog("info", "Checking if patch applies cleanly…");
        break;
      case "applying":
        appendLog("info", "Patch applies — applying to target repository…");
        break;
      case "building":
        appendLog("spin", message || "Building project…");
        break;
      case "testing":
        _resolveSpinner("ok", "Build succeeded");
        appendLog("spin", "Running targeted tests…");
        break;
      case "success":
        _resolveSpinner("ok", "Tests passed");
        appendLog("ok", "Patch applied and verified — no AI needed");
        break;
      case "skipped":
        _resolveSpinner("step", null);
        appendLog("info", "Patch context differs — switching to AI pipeline");
        break;
      case "build_failed":
        _resolveSpinner("warn", "Build failed — switching to AI pipeline");
        break;
      case "test_failed":
        _resolveSpinner("warn", "Tests failed — switching to AI pipeline");
        break;
      default:
        appendLog("info", message || status);
    }
    return;
  }

  // Setup / housekeeping messages
  if (status === "setup") {
    const msg = message || "";
    const type = msg.toLowerCase().startsWith("loaded phase") ? "ok" : "info";
    appendLog(type, msg);
    return;
  }

  if (status === "pipeline_start") {
    appendLog("info", "Switching to AI backport pipeline…");
    return;
  }

  // Completion
  if (status === "complete") {
    _resolveSpinner("ok", null);
    setRunning(false);
    const via2 = via === "direct_apply" ? "direct apply" : "AI pipeline";
    if (validation_passed) {
      appendLog("ok", `Backport complete via ${via2}`);
      showBanner(true, `Backport complete (${via2}) — changes are on disk`, true, !!patch);
    } else {
      appendLog("fail", `Pipeline finished with errors${error ? ` — ${error}` : ""}`);
      showBanner(false, `Partial changes on disk — ${error || "see log for details"}`, true, !!patch);
    }
    if (patch) {
      _lastPatch = patch;
      vscode.postMessage({ command: "showPatch", patch });
    }
    return;
  }

  if (status === "cancelled") {
    _resolveSpinner("warn", null);
    setRunning(false);
    appendLog("warn", "Job cancelled — repository has been reset");
    showBanner(false, "Job cancelled — repository has been reset", false, false);
    return;
  }

  if (status === "error") {
    _resolveSpinner("fail", null);
    setRunning(false);
    appendLog("fail", message || "Unexpected error");
    showBanner(false, message || "Unexpected error", true, false);
    return;
  }

  // Agent pipeline events
  if (agent) {
    if (agent === "validator") {
      if (status === "building") {
        appendLog("spin", "Building project and running tests…");
        return;
      }
      _resolveSpinner(
        validation_passed ? "ok" : "warn",
        validation_passed
          ? "Build and tests passed"
          : `Build or tests failed${error ? ` — ${error.slice(0, 120)}` : ""}`
      );
      return;
    }
    if (agent === "fallback_agent") {
      appendLog("step", `Retrying failed changes (attempt ${attempt})…`);
      return;
    }
    if (agent === "syntax_repair") {
      const map2 = {
        clean: ["ok", "Syntax check passed — no issues found"],
        repaired: ["ok", "Syntax errors detected and automatically repaired"],
        failed: ["warn", "Could not repair syntax errors — escalating"],
        skipped: ["info", "Syntax check skipped — changes already verified clean"],
      };
      const [t, txt] = map2[repair_status] || ["info", message];
      appendLog(t, txt);
      return;
    }
    if (agent === "hunk_router") {
      const strategy = (routing_decision || "").replace(/_/g, " ");
      appendLog("step", `Strategy selected: ${strategy || "determining…"}`);
      return;
    }
    const agentMap = {
      code_localizer: ["step", "Locating changed code in target repository…"],
      patch_classifier: ["step", "Analysing patch complexity…"],
      fast_apply: ["step", "Applying directly matching changes…"],
      namespace_adapter: ["step", "Adapting namespaces and imports…"],
      structural_refactor: ["step", "Handling structural refactoring…"],
      hunk_synthesizer: ["spin", "Generating code changes with AI…"],
      atomic_rollback: ["step", "Rolling back partially applied changes…"],
    };
    const [t2, txt2] = agentMap[agent] || ["step", message || agent];
    appendLog(t2, txt2);
  }
}

function _resolveSpinner(type, text) {
  if (!_activeSpinner) return;
  const entry = _activeSpinner;
  _activeSpinner = null;
  const iconWrap = entry.querySelector(".log-icon-wrap");
  const msgEl = entry.querySelector(".log-msg");
  const cfg = {
    ok: { char: "✓", cls: "li-ok" },
    fail: { char: "✗", cls: "li-fail" },
    warn: { char: "!", cls: "li-warn" },
    step: { char: "·", cls: "li-step" },
    info: { char: "›", cls: "li-info" },
  }[type] || { char: "·", cls: "li-step" };
  iconWrap.innerHTML = "";
  iconWrap.textContent = cfg.char;
  iconWrap.className = `log-icon-wrap ${cfg.cls}`;
  if (text) msgEl.textContent = text;
}

function appendLog(type, text) {
  // Auto-resolve any active spinner when a static entry arrives
  if (_activeSpinner && type !== "spin") _resolveSpinner("step", null);

  logPanel.classList.remove("hidden");
  const entry = document.createElement("div");
  entry.className = "log-entry";

  const iconWrap = document.createElement("span");
  iconWrap.className = "log-icon-wrap";

  if (type === "spin") {
    const s = document.createElement("span");
    s.className = "log-spinner";
    iconWrap.appendChild(s);
  } else {
    const cfg = {
      ok: { char: "✓", cls: "li-ok" },
      fail: { char: "✗", cls: "li-fail" },
      warn: { char: "!", cls: "li-warn" },
      step: { char: "·", cls: "li-step" },
      info: { char: "›", cls: "li-info" },
    }[type] || { char: "›", cls: "li-info" };
    iconWrap.textContent = cfg.char;
    iconWrap.classList.add(cfg.cls);
  }

  const msgEl = document.createElement("span");
  msgEl.className = "log-msg";
  msgEl.textContent = text || "";

  entry.appendChild(iconWrap);
  entry.appendChild(msgEl);
  logBody.appendChild(entry);
  logBody.scrollTop = logBody.scrollHeight;

  if (type === "spin") _activeSpinner = entry;
}

function showBanner(success, text, showReset, showViewDiff) {
  resultBanner.className = `banner ${success ? "success" : "failure"}`;
  bannerText.textContent = (success ? "✓ " : "✗ ") + text;
  resetBtn.classList.toggle("hidden", !showReset);
  resetBtn.disabled = false;
  resetBtn.textContent = "Reset Repository";
  document.getElementById("bannerViewDiffBtn").classList.toggle("hidden", !showViewDiff);
}

function hideBanner() {
  resultBanner.className = "banner hidden";
  resetBtn.classList.add("hidden");
  document.getElementById("bannerViewDiffBtn").classList.add("hidden");
}

function setRunning(state) {
  running = state;
  runBtn.innerHTML = state
    ? '<span class="run-icon">⏳</span> Running…'
    : '<span class="run-icon">▶</span> Run Backport';
  stopBtn.classList.toggle("hidden", !state);
  stopBtn.disabled = false;
  stopBtn.textContent = "⏹ Stop";
  if (state) {
    runBtn.disabled = true;
  } else {
    _updateRunBtn();
  }
}

function resetLog() {
  logBody.innerHTML = "";
  _activeSpinner = null;
  _lastPatch = null;
  hideBanner();
  currentJobId = null;
}
