/* global acquireVsCodeApi */
const vscode = acquireVsCodeApi();

// ── State ────────────────────────────────────────────────────────────────────
let activeTab = "commit";
let useOtherRepo = false;
let running = false;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const form          = document.getElementById("backportForm");
const runBtn        = document.getElementById("runBtn");
const logPanel      = document.getElementById("logPanel");
const logBody       = document.getElementById("logBody");
const resultBanner  = document.getElementById("resultBanner");
const targetRepoFld = document.getElementById("targetRepoField");
const advancedBody  = document.getElementById("advancedBody");
const advancedToggle= document.getElementById("advancedToggle");
const chevron       = advancedToggle.querySelector(".chevron");

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activeTab = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".tab-content").forEach((el) =>
      el.classList.toggle("active", el.dataset.tab === activeTab)
    );
  });
});

// ── Repo mode toggle ──────────────────────────────────────────────────────────
document.querySelectorAll("input[name='repoMode']").forEach((radio) => {
  radio.addEventListener("change", () => {
    useOtherRepo = radio.value === "other";
    targetRepoFld.classList.toggle("hidden", !useOtherRepo);
  });
});

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

// ── Settings button ───────────────────────────────────────────────────────────
document.getElementById("settingsBtn").addEventListener("click", () => {
  vscode.postMessage({ command: "openSettings" });
});

// ── Clear log ─────────────────────────────────────────────────────────────────
document.getElementById("clearLogBtn").addEventListener("click", () => {
  logBody.innerHTML = "";
  logPanel.classList.add("hidden");
  resultBanner.classList.add("hidden");
  resultBanner.className = "banner hidden";
});

// ── Form submit ───────────────────────────────────────────────────────────────
form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (running) return;

  const data = {
    mainlineRepo: document.getElementById("mainlineRepo").value.trim(),
    commit:       activeTab === "commit" ? document.getElementById("commit").value.trim() : "",
    patchText:    activeTab === "patch"  ? document.getElementById("patchText").value.trim() : "",
    targetRepo:   document.getElementById("targetRepo").value.trim(),
    targetBranch: document.getElementById("targetBranch").value.trim(),
    buildCmd:     document.getElementById("buildCmd").value.trim(),
    testCmd:      document.getElementById("testCmd").value.trim(),
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
    case "folderPicked":
      document.getElementById(msg.field).value = msg.path;
      break;

    case "jobStarted":
      appendLog("info", "pipeline", "Agent pipeline starting…");
      break;

    case "log":
      handleLogEvent(msg);
      break;

    case "error":
      appendLog("error", "error", msg.message || "Unknown error");
      showBanner(false, msg.message || "Error occurred");
      setRunning(false);
      break;
  }
});

// ── Log rendering ─────────────────────────────────────────────────────────────
function handleLogEvent(event) {
  const { phase, status, agent, message, error, validation_passed,
          repair_status, routing_decision, attempt } = event;

  if (phase === "phase0") {
    const icons = {
      trying_direct_apply: "Trying direct apply…",
      building:            "Building…",
      testing:             "Running tests…",
      success:             "✓ Direct apply succeeded",
      failed:              `✗ ${event.reason || "Failed"}`,
      skipped:             `↷ ${event.reason || "Skipped — using agent pipeline"}`,
    };
    const isError = status === "failed";
    appendLog(isError ? "warn" : "phase0", "phase-0", icons[status] || status);
    return;
  }

  if (status === "setup" || phase === "setup") {
    appendLog("setup", "setup", message || status);
    return;
  }

  if (status === "complete") {
    const passed = event.validation_passed;
    showBanner(passed, passed ? "Backport complete — diff view opened" : (error || "Pipeline failed"));
    setRunning(false);
    if (passed) appendLog("success", "done", "✓ Validation passed");
    else appendLog("error", "done", `✗ ${error || "Validation failed"} [${event.category || ""}]`);
    return;
  }

  if (status === "diff_ready") {
    appendLog("success", "diff", message || "Opening diff…");
    return;
  }

  if (status === "pipeline_start") {
    appendLog("info", "pipeline", message || "Starting agentic pipeline…");
    return;
  }

  // Per-agent events
  if (agent) {
    const agentLabel = agentDisplayName(agent);
    if (agent === "validator") {
      const ok = validation_passed;
      appendLog(ok ? "success" : "warn", "validator",
        ok ? "✓ Build & tests passed" : `✗ ${error || "Failed"} [${event.category || ""}]`);
    } else if (agent === "fallback_agent") {
      appendLog("fallback", "fallback", `Fallback attempt ${attempt || ""}…`);
    } else if (agent === "syntax_repair") {
      const label = repair_status === "clean" ? "✓ Syntax clean"
                  : repair_status === "repaired" ? "⚙ Syntax repaired"
                  : repair_status === "failed"   ? "✗ Syntax repair failed"
                  : "Checking syntax…";
      appendLog("syntax", "syntax", label);
    } else if (agent === "hunk_router") {
      appendLog("info", "router", `Route → ${routing_decision || "?"}`);
    } else {
      appendLog("agent", agentLabel.toLowerCase(), `${agentLabel} complete`);
    }
  }
}

function agentDisplayName(agent) {
  return {
    code_localizer:      "Localizer",
    patch_classifier:    "Classifier",
    hunk_router:         "Router",
    fast_apply:          "FastApply",
    namespace_adapter:   "Namespace",
    structural_refactor: "Structural",
    hunk_synthesizer:    "Synthesizer",
    atomic_rollback:     "Rollback",
    syntax_repair:       "SyntaxRepair",
    validator:           "Validator",
    fallback_agent:      "Fallback",
  }[agent] || agent;
}

function appendLog(type, tag, text) {
  logPanel.classList.remove("hidden");

  const entry = document.createElement("div");
  entry.className = "log-entry";

  const tagEl = document.createElement("span");
  const tagClass = {
    phase0:    "tag-phase0",
    setup:     "tag-setup",
    agent:     "tag-agent",
    validator: "tag-validator",
    fallback:  "tag-fallback",
    syntax:    "tag-syntax",
    success:   "tag-success",
    error:     "tag-error",
    warn:      "tag-validator",
    info:      "tag-info",
  }[type] || "tag-info";
  tagEl.className = `log-tag ${tagClass}`;
  tagEl.textContent = tag;

  const msgEl = document.createElement("span");
  msgEl.className = "log-msg";
  msgEl.textContent = text;

  entry.appendChild(tagEl);
  entry.appendChild(msgEl);
  logBody.appendChild(entry);
  logBody.scrollTop = logBody.scrollHeight;
}

function showBanner(success, text) {
  resultBanner.className = `banner ${success ? "success" : "failure"}`;
  resultBanner.textContent = (success ? "✓ " : "✗ ") + text;
}

function setRunning(state) {
  running = state;
  runBtn.disabled = state;
  runBtn.innerHTML = state
    ? '<span class="run-icon">⏳</span> Running…'
    : '<span class="run-icon">▶</span> Run Backport';
}

function resetLog() {
  logBody.innerHTML = "";
  resultBanner.className = "banner hidden";
}
