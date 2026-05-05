"""
Backport API routes.

POST /api/backport          — start a job (returns job_id immediately)
GET  /api/backport/{id}/stream — SSE stream of agent progress events
GET  /api/backport/{id}/result — final patch text (when complete)
POST /api/backport/{id}/apply  — apply the patch to disk
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/backport")

# ── In-memory job store ────────────────────────────────────────────────────────
# Each job: {"status": str, "queue": asyncio.Queue, "patch": str|None, "error": str|None}
_jobs: dict[str, dict[str, Any]] = {}


# ── Request/Response models ────────────────────────────────────────────────────

class BackportRequest(BaseModel):
    mainline_repo: str
    commit: str | None = None          # git commit SHA in mainline_repo
    patch_text: str | None = None      # raw diff (alternative to commit)
    target_repo: str | None = None     # if None → same repo as mainline_repo
    target_branch: str = "main"
    build_cmd: str | None = None
    test_cmd: str | None = None
    max_retries: int = 3


class BackportResponse(BaseModel):
    job_id: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _git_show(repo_path: str, commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, "show", commit],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git show failed: {result.stderr[:500]}")
    return result.stdout


def _git_checkout(repo_path: str, ref: str) -> None:
    result = subprocess.run(
        ["git", "-C", repo_path, "checkout", ref],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git checkout {ref} failed: {result.stderr[:500]}")


def _capture_diff(repo_path: str) -> str:
    subprocess.run(["git", "-C", repo_path, "add", "--", "."], capture_output=True)
    for artifact in ("build/", "target/", "build_shared/", "JTwork/", "JTreport/"):
        subprocess.run(["git", "-C", repo_path, "reset", "HEAD", "--", artifact], capture_output=True)
    result = subprocess.run(
        ["git", "-C", repo_path, "diff", "--cached"],
        capture_output=True, text=True,
    )
    return result.stdout


def _rollback_direct_apply(repo_path: str) -> None:
    subprocess.run(
        ["git", "-C", repo_path, "checkout", "HEAD", "--", "."],
        capture_output=True,
    )


def _try_direct_apply(patch_text: str, repo_path: str, build_cmd: str | None,
                      test_cmd: str | None, emit) -> bool:
    """Phase 0: try git apply + build + test directly. Returns True on full success."""
    emit({"phase": "phase0", "status": "trying_direct_apply"})

    check = subprocess.run(
        ["git", "-C", repo_path, "apply", "--check", "-"],
        input=patch_text.encode(), capture_output=True,
    )
    if check.returncode != 0:
        emit({"phase": "phase0", "status": "skipped",
              "reason": "patch does not apply cleanly to target"})
        return False

    subprocess.run(
        ["git", "-C", repo_path, "apply", "-"],
        input=patch_text.encode(), check=True,
    )

    if build_cmd:
        emit({"phase": "phase0", "status": "building"})
        build_ok = subprocess.run(build_cmd, shell=True, cwd=repo_path).returncode == 0
    else:
        build_ok = True  # no build cmd — assume ok, let agents handle validation

    if not build_ok:
        _rollback_direct_apply(repo_path)
        emit({"phase": "phase0", "status": "failed", "reason": "build failed after direct apply"})
        return False

    if test_cmd:
        emit({"phase": "phase0", "status": "testing"})
        test_ok = subprocess.run(test_cmd, shell=True, cwd=repo_path).returncode == 0
    else:
        test_ok = True

    if not test_ok:
        _rollback_direct_apply(repo_path)
        emit({"phase": "phase0", "status": "failed", "reason": "tests failed after direct apply"})
        return False

    emit({"phase": "phase0", "status": "success"})
    return True


def _run_pipeline(job_id: str, req: BackportRequest, loop: asyncio.AbstractEventLoop) -> None:
    """Background thread: runs phase 0 then the agentic graph."""
    job = _jobs[job_id]
    queue: asyncio.Queue = job["queue"]

    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        # ── Resolve inputs ─────────────────────────────────────────────────────
        if req.patch_text:
            patch_text = req.patch_text
        elif req.commit:
            emit({"status": "setup", "message": f"Extracting patch from {req.commit[:8]}..."})
            patch_text = _git_show(req.mainline_repo, req.commit)
        else:
            raise ValueError("Either commit or patch_text must be provided")

        target_repo = req.target_repo if req.target_repo else req.mainline_repo
        same_repo = (target_repo == req.mainline_repo)

        # ── Prepare repo ───────────────────────────────────────────────────────
        emit({"status": "setup", "message": f"Checking out {req.target_branch}..."})
        _git_checkout(target_repo, req.target_branch)

        # ── Phase 0: direct apply ──────────────────────────────────────────────
        direct_ok = _try_direct_apply(patch_text, target_repo, req.build_cmd, req.test_cmd, emit)
        if direct_ok:
            patch = _capture_diff(target_repo)
            job["patch"] = patch
            job["status"] = "complete"
            emit({"status": "complete", "validation_passed": True, "via": "direct_apply"})
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            return

        # ── Phase 1: agentic pipeline ──────────────────────────────────────────
        emit({"status": "pipeline_start", "message": "Starting agentic backport pipeline..."})

        # Import here so the heavy graph is only loaded when a job actually starts
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
            "skip_test": (req.test_cmd is None and req.build_cmd is None),
            "clean_state": True,
            "tokens_used": 0,
            "llm_token_usage": {},
            "wall_clock_time": 0.0,
            "status": "started",
            "custom_build_cmd": req.build_cmd,
            "custom_test_cmd": req.test_cmd,
        }

        graph = build_graph()

        # Stream updates node-by-node; accumulate into final_state
        final_state = dict(initial_state)
        for chunk in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                final_state.update(node_output)

                event: dict[str, Any] = {"agent": node_name, "status": "running"}
                if node_name == "validator":
                    event["validation_passed"] = node_output.get("validation_passed", False)
                    event["error"] = node_output.get("validation_error_context", "")
                    event["category"] = node_output.get("validation_failure_category", "")
                elif node_name == "fallback_agent":
                    event["attempt"] = node_output.get("fallback_attempts", 0)
                    event["fallback_status"] = node_output.get("fallback_status", "")
                elif node_name == "syntax_repair":
                    event["repair_status"] = node_output.get("syntax_repair_status", "")
                elif node_name == "hunk_router":
                    event["routing_decision"] = node_output.get("routing_decision", "")
                emit(event)

        if final_state.get("validation_passed"):
            patch = _capture_diff(target_repo)
            job["patch"] = patch
            job["status"] = "complete"
            emit({"status": "complete", "validation_passed": True, "via": "agentic"})
        else:
            job["status"] = "failed"
            job["error"] = final_state.get("validation_error_context", "Pipeline failed")
            emit({
                "status": "complete",
                "validation_passed": False,
                "error": job["error"],
                "category": final_state.get("validation_failure_category", ""),
            })

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        emit({"status": "error", "message": str(exc)})

    finally:
        asyncio.run_coroutine_threadsafe(queue.put(None), loop)  # sentinel


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=BackportResponse)
async def start_backport(req: BackportRequest):
    job_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    _jobs[job_id] = {
        "status": "running",
        "queue": asyncio.Queue(),
        "patch": None,
        "error": None,
    }
    thread = threading.Thread(target=_run_pipeline, args=(job_id, req, loop), daemon=True)
    thread.start()
    return BackportResponse(job_id=job_id)


@router.get("/{job_id}/stream")
async def stream_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    queue: asyncio.Queue = job["queue"]

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
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if job["status"] == "running":
        raise HTTPException(status_code=202, detail="Job still running")
    if job["status"] == "failed":
        raise HTTPException(status_code=422, detail=job.get("error", "Pipeline failed"))
    return {"patch": job["patch"]}


@router.post("/{job_id}/apply")
async def apply_patch(job_id: str):
    """Apply the generated patch to disk (already done by pipeline — just returns confirmation)."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if job["status"] != "complete" or not job.get("patch"):
        raise HTTPException(status_code=409, detail="No patch available")
    return {"applied": True, "patch_size": len(job["patch"])}
