"""
Backport API routes.

POST   /api/backport              — start a job (returns job_id immediately)
GET    /api/backport/{id}/stream  — SSE stream of agent progress + final patch
GET    /api/backport/{id}/result  — re-download final patch after completion
POST   /api/backport/{id}/cancel  — cancel running job and reset repo
POST   /api/backport/{id}/reset   — reset repo to clean HEAD (user-triggered)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from src.tools.build_systems import run_build, run_tests
from src.agents.agent1_localizer import _is_test_file, _is_auto_generated_java_file

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_PHASE0_CACHE_DIR = _PROJECT_ROOT / "tests" / "phase0_cache"

router = APIRouter(prefix="/backport")

# ── In-memory job store ────────────────────────────────────────────────────────
_jobs: dict[str, dict[str, Any]] = {}

# Human-readable names for agent nodes
_AGENT_LABELS: dict[str, str] = {
    "code_localizer":      "Localizing changed code in target repository",
    "patch_classifier":    "Classifying patch complexity",
    "hunk_router":         "Deciding processing strategy",
    "fast_apply":          "Fast-applying hunks (exact match)",
    "namespace_adapter":   "Adapting namespaces and imports",
    "structural_refactor": "Handling structural refactoring",
    "hunk_synthesizer":    "Synthesizing code changes with LLM",
    "atomic_rollback":     "Rolling back partially-failed files",
    "syntax_repair":       "Checking and repairing Java syntax",
    "validator":           "Building project and running tests",
    "fallback_agent":      "Retrying failed hunks with context",
}


# ── Request/Response models ────────────────────────────────────────────────────

class BackportRequest(BaseModel):
    mainline_repo: str
    commit: str | None = None
    patch_text: str | None = None
    target_repo: str | None = None
    target_branch: str = "main"
    # Shadow-mode fields: when backport_commit is provided the pipeline checks out
    # backport_commit~1 (matching the shadow script) instead of target_branch HEAD.
    backport_commit: str | None = None  # SHA of the developer's backport commit
    evaluate_mode: bool = False          # True → extract developer aux hunks + load phase0 baseline
    project: str | None = None          # project name for phase0 cache lookup (auto-derived if absent)
    build_cmd: str | None = None
    test_cmd: str | None = None
    max_retries: int = 3


class BackportResponse(BaseModel):
    job_id: str


# ── Git helpers ────────────────────────────────────────────────────────────────

def _git_show(repo_path: str, commit: str) -> str:
    r = subprocess.run(["git", "-C", repo_path, "show", commit],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"git show failed: {r.stderr[:500]}")
    return r.stdout


def _git_checkout(repo_path: str, ref: str) -> None:
    r = subprocess.run(["git", "-C", repo_path, "checkout", ref],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"git checkout {ref} failed: {r.stderr[:500]}")


def _capture_diff(repo_path: str) -> str:
    """Stage all changes (excluding build artifacts) and return the unified diff."""
    subprocess.run(["git", "-C", repo_path, "add", "--", "."], capture_output=True)
    for artifact in ("build/", "target/", "build_shared/", "JTwork/", "JTreport/"):
        subprocess.run(["git", "-C", repo_path, "reset", "HEAD", "--", artifact],
                       capture_output=True)
    r = subprocess.run(["git", "-C", repo_path, "diff", "--cached"],
                       capture_output=True, text=True)
    # Unstage after capturing so the working tree stays modified but HEAD is clean
    subprocess.run(["git", "-C", repo_path, "reset", "HEAD"], capture_output=True)
    return r.stdout


def _reset_repo(repo_path: str) -> None:
    """Hard-reset: unstage, restore tracked files, remove untracked files."""
    subprocess.run(["git", "-C", repo_path, "reset", "HEAD"], capture_output=True)
    subprocess.run(["git", "-C", repo_path, "checkout", "HEAD", "--", "."], capture_output=True)
    subprocess.run(["git", "-C", repo_path, "clean", "-fd"], capture_output=True)


# ── Shadow-mode helpers ────────────────────────────────────────────────────────

def _load_phase0_cache(project: str, backport_commit: str) -> dict | None:
    key = f"{project.strip().lower()}_{backport_commit[:16]}.json"
    path = _PHASE0_CACHE_DIR / key
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _extract_file_entries_from_patch(patch_text: str) -> list[tuple[str, str]]:
    """Return (status, filepath) pairs from a unified diff patch."""
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    src_path = tgt_path = ""
    is_added = is_deleted = is_rename = False

    def _norm(p: str) -> str:
        p = p.strip().replace("\\", "/")
        while p.startswith("a/") or p.startswith("b/"):
            p = p[2:]
        return "" if p in ("/dev/null", "dev/null") else p

    def _flush() -> None:
        nonlocal src_path, tgt_path, is_added, is_deleted, is_rename
        fp = tgt_path or src_path
        if fp and fp not in seen:
            seen.add(fp)
            status = "A" if is_added else "D" if is_deleted else "R" if is_rename else "M"
            entries.append((status, fp))
        src_path = tgt_path = ""
        is_added = is_deleted = is_rename = False

    for line in (patch_text or "").splitlines():
        if line.startswith("diff --git "):
            _flush()
        elif line.startswith("new file mode"):
            is_added = True
        elif line.startswith("deleted file mode"):
            is_deleted = True
        elif line.startswith("rename from ") or line.startswith("rename to "):
            is_rename = True
        elif line.startswith("--- "):
            src_path = _norm(line[4:].split("\t")[0])
        elif line.startswith("+++ "):
            tgt_path = _norm(line[4:].split("\t")[0])
    _flush()
    return entries


def _build_aux_hunks_from_target_patch(target_patch: str) -> list[dict]:
    """
    Extract aux-file sections (test Java, non-Java, auto-generated) from the
    developer's backport patch with line numbers preserved for git-apply.
    Production-Java hunks are skipped — they go through the LLM pipeline.
    """
    if not target_patch.strip():
        return []

    def _norm(p: str) -> str:
        p = p.strip().replace("\\", "/")
        while p.startswith("a/") or p.startswith("b/"):
            p = p[2:]
        return "" if p in ("/dev/null", "dev/null") else p

    sections: list[str] = []
    buf: list[str] = []
    for line in target_patch.splitlines(keepends=True):
        if line.startswith("diff --git ") and buf:
            sections.append("".join(buf))
            buf = []
        buf.append(line)
    if buf:
        sections.append("".join(buf))

    result: list[dict] = []
    for section in sections:
        if not section.strip():
            continue
        src_path = tgt_path = ""
        is_added = is_deleted = is_rename = False
        for line in section.splitlines():
            if line.startswith("--- "):
                src_path = _norm(line[4:].split("\t")[0])
            elif line.startswith("+++ "):
                tgt_path = _norm(line[4:].split("\t")[0])
            elif line.startswith("new file mode"):
                is_added = True
            elif line.startswith("deleted file mode"):
                is_deleted = True
            elif line.startswith("rename from ") or line.startswith("rename to "):
                is_rename = True
            if src_path and tgt_path:
                break

        file_path = tgt_path or src_path
        if not file_path:
            continue

        is_java = file_path.lower().endswith(".java")
        if is_java and not _is_test_file(file_path) and not _is_auto_generated_java_file(file_path):
            continue  # production Java — LLM pipeline handles this

        op = ("ADDED" if is_added else "DELETED" if is_deleted else
              "RENAMED" if (is_rename or (src_path and tgt_path and src_path != tgt_path))
              else "MODIFIED")
        result.append({
            "file_path": file_path,
            "raw_patch": section,
            "hunk_text": "",
            "file_operation": op,
            "insertion_line": 0,
            "intent_verified": True,
            "old_target_file": src_path if op == "RENAMED" else None,
        })
    return result


# ── Phase 0 ────────────────────────────────────────────────────────────────────

def _try_direct_apply(patch_text: str, repo_path: str, build_cmd: str | None,
                      test_cmd: str | None, cancel: threading.Event, emit) -> bool:
    """
    Try git apply → build → test using the same build_systems as Agent 7.
    Returns True only if all three succeed. On failure, changes are left on disk.
    """
    emit({"phase": "phase0", "status": "checking",
          "message": "Checking whether patch applies cleanly to target…"})

    check = subprocess.run(
        ["git", "-C", repo_path, "apply", "--check", "-"],
        input=patch_text.encode(), capture_output=True,
    )
    if check.returncode != 0:
        emit({"phase": "phase0", "status": "skipped",
              "message": "Patch context doesn't match target — switching to agentic pipeline"})
        return False

    emit({"phase": "phase0", "status": "applying",
          "message": "Patch applies cleanly — applying to target repository…"})
    subprocess.run(["git", "-C", repo_path, "apply", "-"],
                   input=patch_text.encode(), check=True)

    if cancel.is_set():
        return False

    project = os.path.basename(repo_path.rstrip("/"))

    emit({"phase": "phase0", "status": "building",
          "message": f"Building {project} (Docker/Gradle/Maven auto-detected)…"})
    build_res = run_build(repo_path, project, build_cmd=build_cmd)

    if cancel.is_set():
        return False

    if not build_res.success:
        emit({"phase": "phase0", "status": "build_failed",
              "message": "Build failed after direct apply — switching to agentic pipeline",
              "detail": build_res.output[-1000:] if build_res.output else ""})
        return False

    # Run tests only when the patch touches test files.
    # Pass those exact entries via file_entries so detect_test_targets uses
    # --files-json (reliable) instead of --worktree (misses git-applied changes).
    patch_entries = _extract_file_entries_from_patch(patch_text)
    test_entries = [(s, f) for s, f in patch_entries if _is_test_file(f)]

    if test_entries or test_cmd:
        emit({"phase": "phase0", "status": "testing",
              "message": "Build passed — running targeted tests…"})
        test_res = run_tests(repo_path, project, test_cmd=test_cmd,
                             file_entries=test_entries or None)

        if cancel.is_set():
            return False

        if not test_res.success:
            emit({"phase": "phase0", "status": "test_failed",
                  "message": "Tests failed after direct apply — switching to agentic pipeline",
                  "detail": test_res.output[-1000:] if test_res.output else ""})
            return False

    emit({"phase": "phase0", "status": "success",
          "message": "Patch applied and built successfully — no LLM agents needed"})
    return True


# ── Pipeline thread ────────────────────────────────────────────────────────────

def _run_pipeline(job_id: str, req: BackportRequest, loop: asyncio.AbstractEventLoop) -> None:
    job = _jobs[job_id]
    queue: asyncio.Queue = job["queue"]
    cancel: threading.Event = job["cancel"]

    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    def finish(patch: str, passed: bool, via: str, error: str = "", category: str = "") -> None:
        job["patch"] = patch
        job["status"] = "complete" if passed else "failed"
        job["error"] = error
        emit({
            "status": "complete",
            "validation_passed": passed,
            "via": via,
            "patch": patch,
            "error": error,
            "category": category,
            "message": (
                "Backport complete — changes are on disk. Review the diff, then commit or reset."
                if passed else
                f"Pipeline finished with errors — partial changes are on disk. "
                f"Review what changed or reset to start fresh. Error: {error}"
            ),
        })

    try:
        # ── Resolve patch ──────────────────────────────────────────────────────
        if req.patch_text:
            patch_text = req.patch_text
        elif req.commit:
            emit({"status": "setup",
                  "message": f"Extracting patch from mainline commit {req.commit[:8]}…"})
            patch_text = _git_show(req.mainline_repo, req.commit)
        else:
            raise ValueError("Either commit or patch_text must be provided")

        target_repo = req.target_repo or req.mainline_repo
        job["target_repo"] = target_repo

        # ── Checkout ───────────────────────────────────────────────────────────
        # When backport_commit is provided (shadow mode), check out the state
        # immediately before that commit so the mainline patch context matches.
        if req.backport_commit:
            checkout_ref = f"{req.backport_commit}~1"
            emit({"status": "setup",
                  "message": f"Checking out {checkout_ref} (shadow mode)…"})
        else:
            checkout_ref = req.target_branch
            emit({"status": "setup",
                  "message": f"Checking out target branch '{checkout_ref}'…"})
        _git_checkout(target_repo, checkout_ref)

        if cancel.is_set():
            raise InterruptedError("Cancelled before Phase 0")

        # ── Phase 0 ────────────────────────────────────────────────────────────
        # Always try direct apply first — for TYPE-I shadow commits the mainline
        # patch applies cleanly to backport_commit~1 and no agentic work is needed.
        developer_aux_hunks: list = []
        target_patch_file_entries: list = []
        validation_results: dict = {}

        direct_ok = _try_direct_apply(
            patch_text, target_repo, req.build_cmd, req.test_cmd, cancel, emit
        )
        if cancel.is_set():
            raise InterruptedError("Cancelled during Phase 0")
        if direct_ok:
            finish(_capture_diff(target_repo), passed=True, via="direct_apply")
            return

        # Direct apply failed — reset repo so agentic pipeline starts from clean state.
        emit({"status": "setup", "message": "Resetting repository for agentic pipeline…"})
        _reset_repo(target_repo)
        _git_checkout(target_repo, checkout_ref)

        # Fall through to agentic pipeline.
        # In evaluate_mode extract developer aux hunks (test/non-Java) for Agent 7.
        if req.backport_commit and req.evaluate_mode:
            emit({"status": "setup",
                  "message": f"Extracting developer hunks from backport commit {req.backport_commit[:8]}…"})
            target_patch_text = _git_show(target_repo, req.backport_commit)
            developer_aux_hunks = _build_aux_hunks_from_target_patch(target_patch_text)
            target_patch_file_entries = _extract_file_entries_from_patch(target_patch_text)
            emit({"status": "setup",
                  "message": f"Extracted {len(developer_aux_hunks)} developer aux hunk(s) from backport commit"})

            project = req.project or os.path.basename(target_repo.rstrip("/\\")).lower()
            cached_baseline = _load_phase0_cache(project, req.backport_commit)
            if cached_baseline:
                validation_results = {"phase_0_baseline_test_result": cached_baseline}
                emit({"status": "setup",
                      "message": f"Loaded phase 0 baseline from cache ({project}/{req.backport_commit[:8]})"})
            else:
                emit({"status": "setup",
                      "message": "No phase 0 baseline cache found — skipping baseline"})

        if cancel.is_set():
            raise InterruptedError("Cancelled before agentic pipeline")

        # ── Phase 1: agentic pipeline ──────────────────────────────────────────
        emit({"status": "pipeline_start",
              "message": "Starting agentic backport pipeline (Agents 1–9)…"})

        from src.core.graph import build_graph
        from src.tools.patch_parser import parse_unified_diff

        target_patch_changed_files = [fp for _, fp in target_patch_file_entries]

        initial_state = {
            "patch_content": patch_text,
            "target_repo_path": target_repo,
            "worktree_path": target_repo,
            "target_branch": checkout_ref,
            "hunks": parse_unified_diff(patch_text),
            "developer_aux_hunks": developer_aux_hunks,
            "applied_hunks": [],
            "adapted_hunks": [],
            "refactored_hunks": [],
            "synthesized_hunks": [],
            "failed_hunks": [],
            "processed_hunk_indices": [],
            "structural_escalation_indices": [],
            "file_operations": [],
            "target_patch_changed_files": target_patch_changed_files,
            "target_patch_file_entries": target_patch_file_entries,
            "retry_contexts": [],
            "localization_results": [],
            "classification": None,
            "routing_decision": "",
            "synthesis_status": "",
            "syntax_repair_status": "skipped",
            "syntax_repair_attempts": 0,
            "syntax_repair_log": [],
            "fallback_status": "not_run",
            "fallback_attempts": 0,
            "hunk_descriptions": [],
            "validation_passed": False,
            "validation_attempts": 0,
            "validation_error_context": "",
            "validation_failure_category": "",
            "validation_retry_files": [],
            "validation_results": validation_results,
            "synthesized_hunks_pre_applied": False,
            "current_attempt": 1,
            "max_retries": req.max_retries,
            "skip_test": False,
            "clean_state": True,
            "tokens_used": 0,
            "llm_token_usage": {},
            "wall_clock_time": 0.0,
            "status": "started",
            "custom_build_cmd": req.build_cmd,
            "custom_test_cmd": req.test_cmd,
        }

        graph = build_graph()
        final_state = dict(initial_state)

        for chunk in graph.stream(initial_state, stream_mode="updates"):
            if cancel.is_set():
                raise InterruptedError("Cancelled during agentic pipeline")

            for node_name, node_output in chunk.items():
                final_state.update(node_output)
                label = _AGENT_LABELS.get(node_name, node_name)
                event: dict[str, Any] = {"agent": node_name, "message": label}

                if node_name == "validator":
                    passed = node_output.get("validation_passed", False)
                    error = node_output.get("validation_error_context", "")
                    category = node_output.get("validation_failure_category", "")
                    event["validation_passed"] = passed
                    event["error"] = error
                    event["category"] = category
                    event["message"] = (
                        "Build and tests passed" if passed
                        else f"Build/test failed [{category}]: {error[:120]}"
                    )
                elif node_name == "fallback_agent":
                    attempt = node_output.get("fallback_attempts", 0)
                    event["attempt"] = attempt
                    event["message"] = f"Retry attempt {attempt} — re-synthesizing failed hunks"
                elif node_name == "syntax_repair":
                    rs = node_output.get("syntax_repair_status", "")
                    event["repair_status"] = rs
                    event["message"] = {
                        "clean":    "Syntax check passed — no errors found",
                        "repaired": "Syntax errors detected and automatically fixed",
                        "failed":   "Syntax errors could not be repaired — escalating to fallback",
                        "skipped":  "Syntax check skipped (no hunks to check)",
                    }.get(rs, label)
                    emit(event)
                    if rs != "failed":
                        emit({"agent": "validator", "status": "building",
                              "message": "Starting build — this may take several minutes…"})
                    continue
                elif node_name == "hunk_router":
                    rd = node_output.get("routing_decision", "")
                    event["routing_decision"] = rd
                    event["message"] = f"Strategy selected: {rd.replace('_', ' ')}"

                emit(event)

        passed = final_state.get("validation_passed", False)
        finish(
            patch=_capture_diff(target_repo),
            passed=passed,
            via="agentic",
            error=final_state.get("validation_error_context", ""),
            category=final_state.get("validation_failure_category", ""),
        )

    except InterruptedError:
        _reset_repo(job.get("target_repo", ""))
        job["status"] = "cancelled"
        emit({"status": "cancelled",
              "message": "Job cancelled — repository has been reset to its original state"})

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        emit({"status": "error",
              "message": f"Unexpected error: {exc}"})

    finally:
        asyncio.run_coroutine_threadsafe(queue.put(None), loop)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=BackportResponse)
async def start_backport(req: BackportRequest):
    job_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    _jobs[job_id] = {
        "status": "running",
        "queue": asyncio.Queue(),
        "cancel": threading.Event(),
        "patch": None,
        "error": None,
        "target_repo": req.target_repo or req.mainline_repo,
    }
    threading.Thread(target=_run_pipeline, args=(job_id, req, loop), daemon=True).start()
    return BackportResponse(job_id=job_id)


@router.get("/{job_id}/stream")
async def stream_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    queue: asyncio.Queue = _jobs[job_id]["queue"]

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20.0)
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{job_id}/result")
async def get_result(job_id: str):
    """Re-download the patch after the stream has ended."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if job["status"] == "running":
        raise HTTPException(status_code=202, detail="Job still running")
    patch = job.get("patch") or ""
    return Response(
        content=patch,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="backport-{job_id[:8]}.patch"'},
    )


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job and reset the repository."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if job["status"] != "running":
        raise HTTPException(status_code=409, detail=f"Job is not running (status: {job['status']})")
    job["cancel"].set()
    return {"cancelled": True, "message": "Cancellation requested — repository will be reset"}


@router.post("/{job_id}/reset")
async def reset_repo(job_id: str):
    """Reset the target repository to HEAD (user-triggered, safe to call any time)."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if job["status"] == "running":
        raise HTTPException(status_code=409, detail="Job is still running — cancel it first")
    target_repo = job.get("target_repo", "")
    if not target_repo:
        raise HTTPException(status_code=400, detail="No target repository recorded for this job")
    _reset_repo(target_repo)
    return {"reset": True, "repo": target_repo,
            "message": "Repository reset to HEAD — all applied changes have been removed"}
