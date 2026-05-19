#!/usr/bin/env python3
import os
import json
import csv
import subprocess
import shutil
import platform
from datetime import datetime
from collections import defaultdict

# =========================
# CONFIGURATION
# =========================
# Default BASE_DIR to the workspace root directory (parent of temp directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASE_DIR = os.path.dirname(SCRIPT_DIR)  # Resolves to omni-port root path

BASE_DIR = os.environ.get("BASE_DIR", DEFAULT_BASE_DIR)
RESULTS_DIR = os.environ.get("RESULTS_DIR", os.path.join(BASE_DIR, "tests/shadow_run_results_v3"))
DATASET_CSV = os.environ.get("DATASET_CSV", os.path.join(BASE_DIR, "dataset/all_projects_final.csv"))

OUTPUT_MD_FILE = os.path.join(SCRIPT_DIR, "pipeline_success_report.md")

# =========================
# SYSTEM HELPERS
# =========================

def get_timestamp():
    """Returns current local time formatted."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_system_stats():
    """Returns storage and RAM info, supporting both macOS and Linux."""
    # Storage info (Platform-independent)
    try:
        usage = shutil.disk_usage("/")
        storage_free = usage.free / (1024**3)
        storage_total = usage.total / (1024**3)
        storage_str = f"💾 **Storage:** `{storage_free:.1f}GB` free of `{storage_total:.1f}GB` ({ (storage_free / storage_total * 100):.1f}% free)"
    except Exception as e:
        storage_str = f"💾 **Storage:** Error fetching stats ({e})"
    
    # RAM info
    ram_str = "🧠 **RAM:** `Error fetching stats`"
    system_platform = platform.system()
    
    if system_platform == "Darwin":  # macOS
        try:
            # Get total memory in bytes
            total_mem = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize']).strip())
            
            # Get vm_stat details
            vm_out = subprocess.check_output(['vm_stat']).decode('utf-8').splitlines()
            page_size = 4096  # Default fallback page size
            free_pages = 0
            inactive_pages = 0
            
            for line in vm_out:
                if "page size of" in line:
                    parts = line.split()
                    for p in parts:
                        if p.isdigit():
                            page_size = int(p)
                            break
                elif "Pages free:" in line:
                    free_pages = int(line.split()[-1].replace('.', ''))
                elif "Pages inactive:" in line:
                    inactive_pages = int(line.split()[-1].replace('.', ''))
            
            # Free + inactive acts as available memory on macOS
            available_mem = (free_pages + inactive_pages) * page_size
            used_mem = total_mem - available_mem
            
            ram_used_gb = used_mem / (1024**3)
            ram_total_gb = total_mem / (1024**3)
            ram_perc = (used_mem / total_mem) * 100
            ram_str = f"🧠 **RAM:** `{ram_used_gb:.1f}GB` / `{ram_total_gb:.1f}GB` ({ram_perc:.1f}%)"
        except Exception as e:
            ram_str = f"🧠 **RAM:** `macOS RAM fetch error: {e}`"
            
    else:  # Linux / Fallback
        try:
            mem_output = subprocess.check_output(['free', '-b']).decode('utf-8').splitlines()
            mem_info = mem_output[1].split()
            total_mem = int(mem_info[1])
            used_mem = int(mem_info[2])
            
            ram_used_gb = used_mem / (1024**3)
            ram_total_gb = total_mem / (1024**3)
            ram_perc = (used_mem / total_mem) * 100
            ram_str = f"🧠 **RAM:** `{ram_used_gb:.1f}GB` / `{ram_total_gb:.1f}GB` ({ram_perc:.1f}%)"
        except Exception as e:
            ram_str = f"🧠 **RAM:** `Linux RAM fetch error: {e}`"
            
    return f"{storage_str}\n{ram_str}"

def get_tmux_logs(session_name="run", lines=3):
    """Captures last few lines of tmux pane and reverses them so latest is on top."""
    try:
        cmd = f"tmux capture-pane -pt {session_name}"
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")
        log_lines = [l for l in result.strip().split('\n') if l.strip()]
        tail = log_lines[-lines:]
        tail.reverse()
        return "\n".join(tail)
    except subprocess.CalledProcessError:
        return f"⚠️ tmux session '{session_name}' not found or active."
    except Exception as e:
        return f"⚠️ Error reading tmux logs: {str(e)}"

# =========================
# DATA HELPERS
# =========================

def find_val(data, target_key):
    if not isinstance(data, (dict, list)): return None
    if isinstance(data, dict):
        if target_key in data: return data[target_key]
        for value in data.values():
            res = find_val(value, target_key)
            if res is not None: return res
    elif isinstance(data, list):
        for item in data:
            res = find_val(item, target_key)
            if res is not None: return res
    return None

def is_patch_successful(patch_path):
    # Check if a generated patch or diff file exists and is empty / has < 2 characters
    for filename in ["generated.diff", "generated.patch"]:
        file_path = os.path.join(patch_path, filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                if len(content) < 2:
                    return False  # Treat as fail even if json says pass
            except:
                return False  # Read error counts as fail

    files_to_check = ["results.json", "phase4_validation_validation.json", "pipeline_results.json"]
    for filename in files_to_check:
        file_path = os.path.join(patch_path, filename)
        if not os.path.exists(file_path): continue
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            if any([find_val(data, "validation_passed") is True, 
                    find_val(data, "valid_backport_signal") is True, 
                    find_val(data, "backport_success") is True,
                    find_val(data, "fast_path_success") is True]):
                return True
        except: continue
    return False

# =========================
# CORE PROCESSING
# =========================

def run_pipeline():
    rows = []
    short_commit_to_type = {}
    
    if os.path.exists(DATASET_CSV):
        print(f"📖 Loaded Dataset CSV: {DATASET_CSV}")
        try:
            with open(DATASET_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    commit = (row.get("Original Commit") or row.get("commit") or "").strip().lower()
                    ptype = (row.get("Type") or row.get("type") or "").strip()
                    if commit and ptype:
                        short_commit_to_type[commit[:8]] = ptype
                        short_commit_to_type[commit] = ptype
        except Exception as e:
            print(f"⚠️ Error parsing dataset CSV: {e}")
    else:
        print(f"⚠️ Dataset CSV not found at: {DATASET_CSV}")

    if not os.path.exists(RESULTS_DIR):
        print(f"❌ Results directory not found: {RESULTS_DIR}")
        return []

    print(f"📂 Scanning Results Directory: {RESULTS_DIR}")
    for repo in sorted(os.listdir(RESULTS_DIR)):
        repo_path = os.path.join(RESULTS_DIR, repo)
        if not os.path.isdir(repo_path): continue
        for patch_id in sorted(os.listdir(repo_path)):
            patch_path = os.path.join(repo_path, patch_id)
            if not os.path.isdir(patch_path): continue

            success = is_patch_successful(patch_path)
            ptype = "Unknown"
            
            # Check for type directly inside results files or fall back to CSV
            for filename in ["results.json", "pipeline_results.json", "phase4_validation_validation.json"]:
                file_path = os.path.join(patch_path, filename)
                if not os.path.exists(file_path): continue
                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                    
                    # Direct check for patch type
                    direct_type = find_val(data, "patch_type") or find_val(data, "type")
                    if direct_type:
                        ptype = str(direct_type).strip()
                        break
                    
                    # Commit-based lookup
                    commit = (data.get("mainline_commit") or data.get("original_commit") or "").lower()
                    if commit:
                        ptype = short_commit_to_type.get(commit, short_commit_to_type.get(commit[:8], "Unknown"))
                        break
                except:
                    pass
                    
            rows.append({"Project": repo, "Type": ptype, "Success": success})
    return rows

def compute_and_generate_md(rows):
    if not rows:
        # Create empty placeholder report
        empty_msg = f"""# 📊 Pipeline Success Dashboard

⚠️ **No execution results were found.**
- Please verify your `RESULTS_DIR` path: `{RESULTS_DIR}`
- Check if your datasets and pipeline evaluations have run successfully.

---
*Report Generated: {get_timestamp()}*
"""
        with open(OUTPUT_MD_FILE, "w", encoding="utf-8") as f:
            f.write(empty_msg)
        print(f"⚠️ Saved empty report to: {OUTPUT_MD_FILE}")
        return

    stats_repo = defaultdict(lambda: {"total": 0, "success": 0})
    stats_type = defaultdict(lambda: {"total": 0, "success": 0})
    breakdown = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    totals = {"total": 0, "success": 0}

    for r in rows:
        repo, typ, ok = r["Project"], r["Type"], r["Success"]
        totals["total"] += 1
        stats_repo[repo]["total"] += 1
        stats_type[typ]["total"] += 1
        breakdown[repo][typ][1] += 1
        if ok:
            totals["success"] += 1
            stats_repo[repo]["success"] += 1
            stats_type[typ]["success"] += 1
            breakdown[repo][typ][0] += 1

    success_rate = (totals['success'] / totals['total'] * 100) if totals['total'] > 0 else 0
    
    # Choose status indicator color
    if success_rate >= 75:
        rate_indicator = "🟢"
    elif success_rate >= 40:
        rate_indicator = "🟡"
    else:
        rate_indicator = "🔴"

    # 1. Print Summary to Console
    print("\n" + "="*50)
    print("📋 PIPELINE SUMMARY")
    print("="*50)
    print(f"Total Runs:   {totals['total']}")
    print(f"Successes:    {totals['success']}")
    print(f"Success Rate: {success_rate:.2f}% {rate_indicator}")
    print("="*50 + "\n")

    # 2. Build Markdown Document Content
    md = f"""# 📊 Pipeline Success & Execution Report

This report compiles the latest evaluation run success statistics across repositories and patch types.

---

## 📈 Executive Summary

| Metrics | Value |
| :--- | :--- |
| **Total Pipeline Runs** | `{totals['total']}` |
| **Successful Runs** | `{totals['success']}` |
| **Overall Success Rate** | `{success_rate:.2f}%` {rate_indicator} |

### Success Rate Progress
```text
[{"#" * int(success_rate // 4)}{"-" * (25 - int(success_rate // 4))}] {success_rate:.1f}%
```

---

## 📦 Repository Breakdown

| Repository Name | Total Runs | Successes | Success Rate |
| :--- | :---: | :---: | :---: |
"""
    for repo, s in sorted(stats_repo.items()):
        repo_rate = (s['success'] / s['total'] * 100) if s['total'] > 0 else 0
        md += f"| `{repo}` | **{s['total']}** | `{s['success']}` | `{repo_rate:.2f}%` |\n"

    md += """
---

## 🏷️ Patch Type Breakdown

| Patch Type | Total Runs | Successes | Success Rate |
| :--- | :---: | :---: | :---: |
"""
    for t, s in sorted(stats_type.items()):
        type_rate = (s['success'] / s['total'] * 100) if s['total'] > 0 else 0
        md += f"| `{t}` | **{s['total']}** | `{s['success']}` | `{type_rate:.2f}%` |\n"

    md += """
---

## 📌 Repository × Patch Type Breakdown

"""
    for repo, types in sorted(breakdown.items()):
        md += f"### 📁 `{repo}`\n"
        md += "| Patch Type | Success / Total | Rate | Status |\n"
        md += "| :--- | :---: | :---: | :---: |\n"
        for t, counts in sorted(types.items()):
            sub_rate = (counts[0] / counts[1] * 100) if counts[1] > 0 else 0
            indicator = "🟢" if sub_rate >= 75 else ("🟡" if sub_rate >= 40 else "🔴")
            md += f"| `{t}` | `{counts[0]}/{counts[1]}` | `{sub_rate:.1f}%` | {indicator} |\n"
        md += "\n"

    md += """---

## 🖥️ System Status

"""
    md += get_system_stats().replace("\n", "\n\n") + "\n\n"

    md += """---

## 📜 Latest Execution Logs (tmux: run)

```text
"""
    md += get_tmux_logs("run", 5) + "\n"
    md += "```\n\n"

    md += f"---\n*Report Generated: {get_timestamp()} (Local Time)*\n"

    # Write to temp folder
    with open(OUTPUT_MD_FILE, "w", encoding="utf-8") as f:
        f.write(md)
        
    print(f"🎉 Success counts report beautifully created at: {OUTPUT_MD_FILE}\n")

if __name__ == "__main__":
    print("=== PIPELINE ANALYZE RUNNING ===")
    try:
        data = run_pipeline()
        compute_and_generate_md(data)
    except Exception as e:
        print(f"❌ Error in script execution: {e}")
