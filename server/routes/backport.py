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
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from src.tools.build_systems import run_build, run_tests

router = APIRouter(prefix="/api/backport")

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

    emit({"phase": "phase0", "status": "testing",
          "message": "Build passed — running targeted tests…"})
    test_res = run_tests(repo_path, project, test_cmd=test_cmd)

    if cancel.is_set():
        return False

    if not test_res.success:
        emit({"phase": "phase0", "status": "test_failed",
              "message": "Tests failed after direct apply — switching to agentic pipeline",
              "detail": test_res.output[-1000:] if test_res.output else ""})
        return False

    emit({"phase": "phase0", "status": "success",
          "message": "Patch applied, built, and tested successfully — no LLM agents needed"})
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
        emit({"status": "setup",
              "message": f"Checking out target branch '{req.target_branch}'…"})
        _git_checkout(target_repo, req.target_branch)

        if cancel.is_set():
            raise InterruptedError("Cancelled before Phase 0")

        # ── Phase 0 ────────────────────────────────────────────────────────────
        direct_ok = _try_direct_apply(
            patch_text, target_repo, req.build_cmd, req.test_cmd, cancel, emit
        )

        if cancel.is_set():
            raise InterruptedError("Cancelled during Phase 0")

        if direct_ok:
            finish(_capture_diff(target_repo), passed=True, via="direct_apply")
            return

        # ── Phase 1: agentic pipeline ──────────────────────────────────────────
        emit({"status": "pipeline_start",
              "message": "Starting agentic backport pipeline (Agents 1–9)…"})

        from src.core.graph import build_graph
        from src.tools.patch_parser import parse_unified_diff

        initial_state = {
            "patch_content": patch_text,
            "target_repo_path": target_repo,
            "worktree_path": target_repo,
            "target_branch": req.target_branch,
            "hunks": parse_unified_diff(patch_text),
            "developer_aux_hunks": [],
            "applied_hunks": [],
            "adapted_hunks": [],
            "refactored_hunks": [],
            "synthesized_hunks": [],
            "failed_hunks": [],
            "processed_hunk_indices": [],
            "structural_escalation_indices": [],
            "file_operations": [],
            "target_patch_changed_files": [],
            "target_patch_file_entries": [],
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
            "validation_results": {},
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
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

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
