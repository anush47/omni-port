/* global acquireVsCodeApi */
const vscode = acquireVsCodeApi();

// ── State ────────────────────────────────────────────────────────────────────
let activeTab = "commit";
let useOtherRepo = false;
let running = false;
let currentJobId = null;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const form          = document.getElementById("backportForm");
const runBtn        = document.getElementById("runBtn");
const stopBtn       = document.getElementById("stopBtn");
const resetBtn      = document.getElementById("resetBtn");
const logPanel      = document.getElementById("logPanel");
const logBody       = document.getElementById("logBody");
const resultBanner  = document.getElementById("resultBanner");
const bannerText    = document.getElementById("bannerText");
const targetRepoFld = document.getElementById("targetRepoField");
const advancedBody  = document.getElementById("advancedBody");
const advancedToggle= document.getElementById("advancedToggle");
const chevron       = advancedToggle.querySelector(".chevron");
const statusDot          = document.getElementById("statusDot");
const targetBranchInput  = document.getElementById("targetBranch");
const targetBranchSelect = document.getElementById("targetBranchSelect");
const branchHint         = document.getElementById("branchHint");

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
    if (useOtherRepo) {
      resetBranchToInput();
    } else {
      scheduleBranchFetch();
    }
  });
});

// ── Branch auto-complete ──────────────────────────────────────────────────────
let _branchTimer = null;

function getTargetBranch() {
  return targetBranchSelect.classList.contains("hidden")
    ? targetBranchInput.value.trim()
    : targetBranchSelect.value;
}

function resetBranchToInput() {
  targetBranchSelect.classList.add("hidden");
  targetBranchSelect.required = false;
  targetBranchInput.classList.remove("hidden");
  targetBranchInput.required = true;
  branchHint.classList.add("hidden");
}

function scheduleBranchFetch() {
  if (useOtherRepo) return;
  const repo = document.getElementById("mainlineRepo").value.trim();
  if (!repo) { resetBranchToInput(); return; }
  branchHint.textContent = "Loading branches…";
  branchHint.classList.remove("hidden");
  clearTimeout(_branchTimer);
  _branchTimer = setTimeout(() => {
    vscode.postMessage({ command: "fetchBranches", repo });
  }, 500);
}

document.getElementById("mainlineRepo").addEventListener("input", scheduleBranchFetch);

// ── Health check ──────────────────────────────────────────────────────────────
function requestHealth() {
  vscode.postMessage({ command: "checkHealth" });
}

function updateStatusDot(connected, data) {
  statusDot.className = "status-dot " + (
    !connected              ? "status-error" :
    !data.api_key_configured ? "status-warn"  :
                               "status-ok"
  );

  const port = data.port ? `:${data.port}` : "";
  document.getElementById("spBackend").textContent   = connected ? `online${port}` : "offline";
  document.getElementById("spProvider").textContent  = data.provider || "—";
  document.getElementById("spFast").textContent      = data.fast_model || "—";
  document.getElementById("spBalanced").textContent  = data.balanced_model || "—";
  document.getElementById("spReasoning").textContent = data.reasoning_model || "—";
}

// Poll on load + every 20s
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
  appendLog("warn", "cancel", "Cancellation requested — waiting for current step to finish…");
});

// ── Reset button ──────────────────────────────────────────────────────────────
resetBtn.addEventListener("click", () => {
  if (!currentJobId) return;
  resetBtn.disabled = true;
  resetBtn.textContent = "Resetting…";
  vscode.postMessage({ command: "resetRepo", jobId: currentJobId });
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
    targetBranch: getTargetBranch(),
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
    case "healthStatus":
      updateStatusDot(msg.connected, msg);
      break;
    case "folderPicked":
      document.getElementById(msg.field).value = msg.path;
      if (msg.field === "mainlineRepo" && !useOtherRepo) scheduleBranchFetch();
      break;
    case "branchList": {
      const prev = getTargetBranch();
      if (!msg.branches || msg.branches.length === 0) {
        resetBranchToInput();
        branchHint.textContent = "No git branches found — enter branch name manually";
        branchHint.classList.remove("hidden");
        break;
      }
      const opts = msg.branches.map((b) => {
        const sel = b === prev ? " selected" : "";
        return `<option value="${b}"${sel}>${b}</option>`;
      });
      if (prev && !msg.branches.includes(prev)) {
        opts.unshift(`<option value="${prev}" selected>${prev}</option>`);
      }
      targetBranchSelect.innerHTML = opts.join("");
      targetBranchInput.classList.add("hidden");
      targetBranchInput.required = false;
      targetBranchSelect.classList.remove("hidden");
      targetBranchSelect.required = true;
      branchHint.classList.add("hidden");
      break;
    }
    case "jobStarted":
      currentJobId = msg.jobId;
      appendLog("info", "pipeline", "Connected to backend — pipeline starting…");
      break;
    case "log":
      handleLogEvent(msg);
      break;
    case "error":
      appendLog("error", "error", msg.message || "Unknown error");
      showBanner(false, msg.message || "Error occurred");
      setRunning(false);
      break;
    case "repoReset":
      resetBtn.disabled = false;
      resetBtn.textContent = "Reset Repository";
      appendLog("info", "reset", "Repository has been reset to its original state");
      break;
  }
});

// ── Log rendering ─────────────────────────────────────────────────────────────
function handleLogEvent(event) {
  const { phase, status, agent, message, error, validation_passed,
          repair_status, routing_decision, attempt, via, patch, category } = event;

  // Phase 0 events
  if (phase === "phase0") {
    const styles = {
      checking:     ["info",    "phase-0", message],
      applying:     ["phase0",  "phase-0", message],
      building:     ["phase0",  "phase-0", message],
      testing:      ["phase0",  "phase-0", message],
      success:      ["success", "phase-0", message],
      skipped:      ["info",    "phase-0", message],
      build_failed: ["warn",    "phase-0", message],
      test_failed:  ["warn",    "phase-0", message],
      failed:       ["warn",    "phase-0", message],
    };
    const [type, tag, text] = styles[status] || ["info", "phase-0", message || status];
    appendLog(type, tag, text);
    return;
  }

  // Setup events
  if (status === "setup") {
    appendLog("setup", "setup", message || status);
    return;
  }

  // Pipeline start
  if (status === "pipeline_start") {
    appendLog("info", "pipeline", message);
    return;
  }

  // Final complete event
  if (status === "complete") {
    setRunning(false);
    const passed = validation_passed;
    const viaLabel = via === "direct_apply" ? " (direct apply)" : " (agentic pipeline)";

    if (passed) {
      appendLog("success", "done", `✓ Backport succeeded${viaLabel}`);
      showBanner(true, `Backport complete${viaLabel} — changes are on disk`, true);
      if (patch) {
        vscode.postMessage({ command: "onComplete", jobId: currentJobId, passed: true, patch });
      }
    } else {
      appendLog("error", "done", `✗ Pipeline finished — ${error || "see errors above"}`);
      showBanner(false, `Partial changes on disk — ${error || "see log for details"}`, true);
      if (patch) {
        vscode.postMessage({ command: "onComplete", jobId: currentJobId, passed: false, patch });
      }
    }
    return;
  }

  // Cancelled
  if (status === "cancelled") {
    setRunning(false);
    appendLog("warn", "cancel", message || "Cancelled — repository reset");
    showBanner(false, "Job cancelled — repository has been reset", false);
    return;
  }

  // Error
  if (status === "error") {
    setRunning(false);
    appendLog("error", "error", message || "Unexpected error");
    showBanner(false, message || "Unexpected error", true);
    return;
  }

  // Per-agent events
  if (agent) {
    if (agent === "validator") {
      if (status === "building") {
        appendLog("info", "build", message || "Starting build…");
        return;
      }
      const passed = validation_passed;
      appendLog(
        passed ? "success" : "warn",
        "validator",
        message || (passed ? "Build and tests passed" : `Failed: ${error}`)
      );
    } else if (agent === "fallback_agent") {
      appendLog("fallback", "fallback", message || `Retry attempt ${attempt}`);
    } else if (agent === "syntax_repair") {
      const type = repair_status === "clean" ? "success"
                 : repair_status === "repaired" ? "syntax"
                 : repair_status === "failed" ? "error" : "info";
      appendLog(type, "syntax", message);
    } else if (agent === "hunk_router") {
      appendLog("info", "router", message);
    } else {
      appendLog("agent", agentShortName(agent), message);
    }
  }
}

function agentShortName(agent) {
  return {
    code_localizer:      "localizer",
    patch_classifier:    "classifier",
    fast_apply:          "fast-apply",
    namespace_adapter:   "namespace",
    structural_refactor: "structural",
    hunk_synthesizer:    "synthesizer",
    atomic_rollback:     "rollback",
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
    build:     "tag-build",
  }[type] || "tag-info";
  tagEl.className = `log-tag ${tagClass}`;
  tagEl.textContent = tag;

  const msgEl = document.createElement("span");
  msgEl.className = "log-msg";
  msgEl.textContent = text || "";

  entry.appendChild(tagEl);
  entry.appendChild(msgEl);
  logBody.appendChild(entry);
  logBody.scrollTop = logBody.scrollHeight;
}

function showBanner(success, text, showReset) {
  resultBanner.className = `banner ${success ? "success" : "failure"}`;
  bannerText.textContent = (success ? "✓ " : "✗ ") + text;
  resetBtn.classList.toggle("hidden", !showReset);
  resetBtn.disabled = false;
  resetBtn.textContent = "Reset Repository";
}

function hideBanner() {
  resultBanner.className = "banner hidden";
  resetBtn.classList.add("hidden");
}

function setRunning(state) {
  running = state;
  runBtn.disabled = state;
  runBtn.innerHTML = state
    ? '<span class="run-icon">⏳</span> Running…'
    : '<span class="run-icon">▶</span> Run Backport';
  stopBtn.classList.toggle("hidden", !state);
  stopBtn.disabled = false;
  stopBtn.textContent = "⏹ Stop";
}

function resetLog() {
  logBody.innerHTML = "";
  hideBanner();
  currentJobId = null;
}
