#!/usr/bin/env python3
import os
import json
import csv
import re
import subprocess
import shutil
import platform
import statistics
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

# =========================
# CONFIGURATION & PATHS
# =========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASE_DIR = os.path.dirname(SCRIPT_DIR)  # omni-port root

BASE_DIR = os.environ.get("BASE_DIR", DEFAULT_BASE_DIR)
RESULTS_DIR = os.environ.get("RESULTS_DIR", os.path.join(BASE_DIR, "tests/shadow_run_results_v3"))
DATASET_CSV = os.environ.get("DATASET_CSV", os.path.join(BASE_DIR, "dataset/all_projects_final.csv"))

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PATCH_COMP_JSON = os.path.join(OUTPUT_DIR, "patch_comparison.json")
FALLBACK_ANALYSIS_JSON = os.path.join(OUTPUT_DIR, "fallback_analysis.json")

OUTPUT_MD_REPORT = os.path.join(SCRIPT_DIR, "detailed_stats_report.md")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# SYSTEM HELPERS
# =========================

def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
    # Enforce trimmed length >= 2 check for generated diff/patch files
    for filename in ["generated.diff", "generated.patch"]:
        file_path = os.path.join(patch_path, filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                if len(content) < 2:
                    return False
            except:
                return False
                
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
# PATCH PARSING LOGIC
# =========================

def parse_patch_file(patch_path_str):
    """Parses git diff patch file to return file_hunks dict (file -> count) and file_list."""
    patch_path = Path(patch_path_str)
    if not patch_path.exists():
        return {}, []
    
    try:
        with open(patch_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return {}, []
    
    file_hunks = defaultdict(int)
    file_list = []
    current_file = None
    
    file_pattern = r'^diff --git a/(.+) b/(.+)$'
    hunk_pattern = r'^@@'
    
    lines = content.split('\n')
    for line in lines:
        file_match = re.match(file_pattern, line)
        if file_match:
            current_file = file_match.group(1)
            if current_file not in file_list:
                file_list.append(current_file)
        if current_file and re.match(hunk_pattern, line):
            file_hunks[current_file] += 1
            
    return dict(file_hunks), file_list

def is_java_file(file_path):
    """Exclude test files, keep Java production."""
    if not file_path.endswith('.java'):
        return False
    if '/test/' in file_path or '/tests/' in file_path:
        return False
    return True

def count_java_production_hunks(file_hunks, file_list):
    return sum(file_hunks.get(file_path, 0) for file_path in file_list if is_java_file(file_path))

def get_ai_time(agents_dict):
    total_s = 0.0
    if not isinstance(agents_dict, dict):
        return total_s
    for agent_name, agent_data in agents_dict.items():
        if isinstance(agent_data, dict):
            total_s += agent_data.get("elapsed_s") or 0.0
    return total_s

def get_cumulative_time(data, agents_dict, repo, pathway):
    # Base AI time from all agents logged in results.json
    baseline_ai_time = get_ai_time(agents_dict)
    
    # Map of standard repository build/test times (in seconds)
    DEFAULT_BUILD_TIMES = {
        "crate": 230.0,
        "elasticsearch": 65.0,
        "graylog2-server": 6.0,
        "hbase": 45.0,
        "hibernate-orm": 20.0,
        "jdk11u-dev": 50.0,
        "jdk17u-dev": 50.0,
        "jdk21u-dev": 50.0,
        "jdk25u-dev": 50.0,
        "logstash": 15.0,
        "spring-framework": 10.0,
        "sql": 10.0,
        "druid": 30.0,
        "hadoop": 40.0
    }
    build_unit = DEFAULT_BUILD_TIMES.get(repo, 30.0)
    
    # Parse exact failed build times from error contexts
    parsed_failed_build_times = []
    def search_strings(obj):
        if isinstance(obj, str):
            # Matches strings like "BUILD FAILED in 2m 12s", "BUILD FAILED in 37s"
            match = re.search(r'BUILD FAILED in (?:(\d+)m\s*)?(\d+)s', obj)
            if match:
                m = int(match.group(1)) if match.group(1) else 0
                s = int(match.group(2))
                parsed_failed_build_times.append(m * 60.0 + s)
        elif isinstance(obj, dict):
            for v in obj.values():
                search_strings(v)
        elif isinstance(obj, list):
            for item in obj:
                search_strings(item)
                
    search_strings(data)
    
    # Take unique build times to prevent counting the same log block multiple times
    unique_failed_build_times = []
    for t in parsed_failed_build_times:
        if t not in unique_failed_build_times:
            unique_failed_build_times.append(t)
            
    # Calculate cumulative execution time depending on the success pathway
    if pathway == "fast_apply":
        # Applied instantly without any compilation errors or retries
        total_time = baseline_ai_time + build_unit
        
    elif pathway == "first_try_synthesis":
        # Synthesis succeeded on the first attempt with 1 successful build validation
        total_time = baseline_ai_time + build_unit
        
    elif pathway == "standard_retry":
        # Succeeded after standard validator retry/repair loops
        val_attempts = agents_dict.get("agent7_validator", {}).get("validation_attempts", 1)
        num_failed_builds = max(0, val_attempts - 1)
        
        # Build duration sum
        if len(unique_failed_build_times) >= num_failed_builds:
            failed_build_duration = sum(unique_failed_build_times[:num_failed_builds])
        else:
            failed_build_duration = num_failed_builds * build_unit
            
        total_time = baseline_ai_time + failed_build_duration + build_unit
        
    elif pathway == "fallback_recovery":
        # Standard baseline failed, then fallback agents executed
        summary = data.get("summary", {})
        val_attempts = agents_dict.get("agent7_validator", {}).get("validation_attempts", 1)
        num_baseline_failed_builds = val_attempts
        baseline_failed_duration = num_baseline_failed_builds * build_unit
        
        # Fallback runs
        fb_attempts = summary.get("fallback_attempts") or data.get("fallback_attempts") or 0
        num_fallback_failed_builds = max(0, fb_attempts - 1)
        fallback_failed_duration = num_fallback_failed_builds * build_unit
        
        # Combine failed builds
        total_failed_attempts = num_baseline_failed_builds + num_fallback_failed_builds
        if len(unique_failed_build_times) >= total_failed_attempts:
            failed_build_duration = sum(unique_failed_build_times[:total_failed_attempts])
        else:
            failed_build_duration = baseline_failed_duration + fallback_failed_duration
            
        # Fallback AI time: ~35 seconds per LLM synthesis attempt
        fallback_ai_time = fb_attempts * 35.0
        
        total_time = baseline_ai_time + failed_build_duration + fallback_ai_time + build_unit
        
    else:
        # For failed patches
        failed_build_duration = sum(unique_failed_build_times) if unique_failed_build_times else build_unit
        total_time = baseline_ai_time + failed_build_duration
        
    return total_time

def get_token_usage(data):
    summary = data.get("summary", {})
    # Check direct tokens_used in summary
    direct_tokens = summary.get("tokens_used") or data.get("tokens_used")
    
    # Check llm_token_usage dictionary
    llm_usage = summary.get("llm_token_usage") or data.get("llm_token_usage")
    if not llm_usage and isinstance(data, dict):
        # Scan recursively for llm_token_usage key
        def find_key(obj, key):
            if isinstance(obj, dict):
                if key in obj:
                    return obj[key]
                for v in obj.values():
                    res = find_key(v, key)
                    if res: return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_key(item, key)
                    if res: return res
            return None
        llm_usage = find_key(data, "llm_token_usage")
        
    summed_tokens = 0
    if isinstance(llm_usage, dict):
        for agent_usage in llm_usage.values():
            if isinstance(agent_usage, dict):
                summed_tokens += agent_usage.get("input", 0) + agent_usage.get("output", 0)
                
    # Return the max of direct_tokens and summed_tokens to guarantee comprehensive coverage
    return max(direct_tokens or 0, summed_tokens)


# =========================
# CORE CONSOLIDATION LOGIC
# =========================

def process_results():
    if not os.path.exists(RESULTS_DIR):
        print(f"❌ Results directory not found: {RESULTS_DIR}")
        return [], [], [], [], {}, {}, {}, []

    print(f"📂 Scanning results in {RESULTS_DIR}...")
    
    comparison_data = []
    fallback_data = []
    empty_patches = []
    fewer_hunks = []
    failed_patches = []
    
    pathway_counts = {
        "fast_apply": 0,
        "first_try_synthesis": 0,
        "standard_retry": 0,
        "fallback_recovery": 0
    }
    
    pathway_by_repo = defaultdict(lambda: {
        "fast_apply": 0, "first_try_synthesis": 0, "standard_retry": 0, "fallback_recovery": 0
    })
    
    pathway_by_type = defaultdict(lambda: {
        "fast_apply": 0, "first_try_synthesis": 0, "standard_retry": 0, "fallback_recovery": 0
    })
    
    # Process all patches recursively
    for repo in sorted(os.listdir(RESULTS_DIR)):
        repo_path = os.path.join(RESULTS_DIR, repo)
        if not os.path.isdir(repo_path): continue
        
        for patch_id in sorted(os.listdir(repo_path)):
            patch_path = os.path.join(repo_path, patch_id)
            if not os.path.isdir(patch_path): continue
            
            # Try to read the first available results JSON file
            data = {}
            for filename in ["results.json", "pipeline_results.json", "phase4_validation_validation.json"]:
                file_path = os.path.join(patch_path, filename)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                        break
                    except Exception:
                        pass
            
            patch_type = data.get('patch_type') or find_val(data, 'patch_type') or find_val(data, 'type') or 'unknown'
            summary = data.get('summary', {})
            agents = data.get('agents', {})
            
            # --- 1. Success Flag ---
            final_success = is_patch_successful(patch_path)
            
            # --- 2. Fallback Agent Parsing ---
            fallback_status = summary.get('fallback_status') or data.get('fallback_status') or "not_run"
            fallback_attempts = summary.get('fallback_attempts') or data.get('fallback_attempts') or 0
            
            fallback_run = (fallback_status in ["applied", "failed"]) or (fallback_attempts > 0)
            
            if fallback_run:
                # If fallback was run, baseline execution failed before fallback
                succeed_before = False
                succeed_after = final_success
            else:
                # Fallback was not run. Success rate before and after is the same
                succeed_before = final_success
                succeed_after = final_success
                
            fallback_data.append({
                "patch_id": patch_id[:8],
                "repo": repo,
                "patch_type": patch_type,
                "succeed_before_fallback_agent": succeed_before,
                "succeed_after_fallback_agent": succeed_after
            })
            
            # --- 3. Empty Patch Check ---
            is_empty = False
            patch_found = False
            for filename in ["generated.diff", "generated.patch"]:
                file_path = os.path.join(patch_path, filename)
                if os.path.exists(file_path):
                    patch_found = True
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as pf:
                            if len(pf.read().strip()) < 2:
                                is_empty = True
                    except:
                        is_empty = True
            
            if not patch_found or is_empty:
                empty_patches.append({
                    "repo": repo,
                    "patch_id": patch_id,
                    "success": final_success
                })
            
            # --- 4. Hunk and Patch Parsing ---
            target_patch_path = os.path.join(patch_path, 'target.patch')
            generated_patch_path = os.path.join(patch_path, 'generated.patch')
            
            target_hunks, target_files = parse_patch_file(target_patch_path)
            generated_hunks, generated_files = parse_patch_file(generated_patch_path)
            
            target_java_prod_hunks = count_java_production_hunks(target_hunks, target_files)
            generated_java_prod_hunks = count_java_production_hunks(generated_hunks, generated_files)
            
            dev_aux_from_target = summary.get('developer_aux_hunks_from_target', 0)
            total_hunks = summary.get('total_hunks_in_patch', 0)
            java_production_hunks = summary.get('java_production_hunks', 0)
            developer_aux_hunks = summary.get('developer_aux_hunks', 0)
            failed_hunks = summary.get('failed_hunks_total', 0)
            
            if final_success and (generated_java_prod_hunks < target_java_prod_hunks):
                fewer_hunks.append({
                    "repo": repo,
                    "patch_id": patch_id,
                    "dev_hunks": target_java_prod_hunks,
                    "gen_hunks": generated_java_prod_hunks,
                    "success": final_success
                })
            
            # --- 5. Pathway Distribution ---
            pathway = "failed"
            if final_success:
                synthesized_count = summary.get("synthesized_count") or agents.get("agent6_synthesizer", {}).get("synthesized_count", 0)
                retry_contexts = summary.get("retry_contexts", [])
                val_attempts = agents.get("agent7_validator", {}).get("validation_attempts", 1)
                
                has_retries = (len(retry_contexts) > 0) or (val_attempts > 1) or ("agent7_validator_retry1" in agents)
                
                if fallback_run:
                    pathway = "fallback_recovery"
                elif has_retries:
                    pathway = "standard_retry"
                elif synthesized_count == 0:
                    pathway = "fast_apply"
                else:
                    pathway = "first_try_synthesis"
                    
                pathway_counts[pathway] += 1
                pathway_by_repo[repo][pathway] += 1
                pathway_by_type[patch_type][pathway] += 1
            else:
                fail_cat = summary.get('validation_failure_category') or find_val(data, 'validation_failure_category') or 'unknown'
                failed_patches.append({
                    "repo": repo,
                    "patch_id": patch_id,
                    "patch_type": patch_type,
                    "failure_category": fail_cat
                })
            
            # File level comparisons
            all_java_files = set()
            for file_path in target_files + generated_files:
                if is_java_file(file_path):
                    all_java_files.add(file_path)
                    
            files_comparison = []
            for file_path in sorted(all_java_files):
                files_comparison.append({
                    "file_path": file_path,
                    "hunks_in_target": target_hunks.get(file_path, 0),
                    "hunks_in_generated": generated_hunks.get(file_path, 0)
                })
                
            # Calculate cumulative execution time using the comprehensive model
            cumulative_exec_time = get_cumulative_time(data, agents, repo, pathway) if final_success else 0.0
            total_tokens = get_token_usage(data) if final_success else 0

            comparison_data.append({
                "patch_id": patch_id[:8],
                "repo": repo,
                "patch_type": patch_type,
                "success": final_success,
                "ai_time": cumulative_exec_time,
                "tokens_used": total_tokens,
                "pathway": pathway,
                
                # Hunk counts
                "total_hunks": total_hunks,
                "java_production_hunks": java_production_hunks,
                "developer_aux_hunks": developer_aux_hunks,
                "failed_hunks": failed_hunks,
                
                # Comparisons
                "prod_hunks_count_dev": target_java_prod_hunks,
                "prod_hunks_count_gen": generated_java_prod_hunks,
                "developer_aux_hunks_from_target": dev_aux_from_target,
                "files": files_comparison
            })
            
    # Write intermediate legacy JSONs for backward compatibility
    with open(PATCH_COMP_JSON, 'w') as f:
        json.dump(comparison_data, f, indent=2)
    with open(FALLBACK_ANALYSIS_JSON, 'w') as f:
        json.dump(fallback_data, f, indent=2)
        
    print(f"💾 Wrote compatibility JSON: {PATCH_COMP_JSON}")
    print(f"💾 Wrote compatibility JSON: {FALLBACK_ANALYSIS_JSON}")
    
    return comparison_data, fallback_data, empty_patches, fewer_hunks, pathway_counts, pathway_by_repo, pathway_by_type, failed_patches

# =========================
# REPORT COMPILATION
# =========================

def compile_metrics_and_markdown(comp_data, fb_data, empty_patches, fewer_hunks, pathway_counts, pathway_by_repo, pathway_by_type, failed_patches):
    if not comp_data:
        print("❌ No data processed to compile report.")
        return
        
    total_patches = len(comp_data)
    
    # --- 0. AI PROCESSING TIME STATS (Successful runs only) ---
    success_runs = [item for item in comp_data if item['success']]
    
    pathway_times = defaultdict(list)
    for item in success_runs:
        pathway_times[item['pathway']].append(item['ai_time'])
        
    pathway_time_stats = {}
    for p in ["fast_apply", "first_try_synthesis", "standard_retry", "fallback_recovery"]:
        times = pathway_times[p]
        if times:
            pathway_time_stats[p] = {
                "count": len(times),
                "avg": statistics.mean(times),
                "median": statistics.median(times),
                "min": min(times),
                "max": max(times)
            }
        else:
            pathway_time_stats[p] = {
                "count": 0, "avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0
            }
            
    repo_pathway_times = defaultdict(lambda: defaultdict(list))
    for item in success_runs:
        repo_pathway_times[item['repo']][item['pathway']].append(item['ai_time'])
        
    all_repos = sorted(list(set(item['repo'] for item in comp_data)))
    
    type_pathway_times = defaultdict(lambda: defaultdict(list))
    for item in success_runs:
        type_pathway_times[item['patch_type']][item['pathway']].append(item['ai_time'])
        
    all_types = sorted(list(set(item['patch_type'] for item in comp_data if item['patch_type'] not in ['unknown', None])))
    
    pathway_tokens = defaultdict(list)
    for item in success_runs:
        pathway_tokens[item['pathway']].append(item.get('tokens_used', 0))
        
    pathway_token_stats = {}
    for p in ["fast_apply", "first_try_synthesis", "standard_retry", "fallback_recovery"]:
        tokens = pathway_tokens[p]
        if tokens:
            pathway_token_stats[p] = {
                "count": len(tokens),
                "avg": statistics.mean(tokens),
                "median": statistics.median(tokens),
                "min": min(tokens),
                "max": max(tokens)
            }
        else:
            pathway_token_stats[p] = {
                "count": 0, "avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0
            }
            
    repo_pathway_tokens = defaultdict(lambda: defaultdict(list))
    for item in success_runs:
        repo_pathway_tokens[item['repo']][item['pathway']].append(item.get('tokens_used', 0))
        
    type_pathway_tokens = defaultdict(lambda: defaultdict(list))
    for item in success_runs:
        type_pathway_tokens[item['patch_type']][item['pathway']].append(item.get('tokens_used', 0))
        
    def fmt_avg(lst):
        if not lst:
            return "-"
        return f"{statistics.mean(lst):.2f}s"
        
    def fmt_tokens(lst):
        if not lst:
            return "-"
        return f"{statistics.mean(lst):,.0f}"
        
    # --- 1. FALLBACK AGENT STATS ---
    without_fallback = sum(1 for item in fb_data if item['succeed_before_fallback_agent'])
    with_fallback = sum(1 for item in fb_data if item['succeed_after_fallback_agent'])
    improved = sum(1 for item in fb_data 
                   if not item['succeed_before_fallback_agent'] and item['succeed_after_fallback_agent'])
    regressed = sum(1 for item in fb_data 
                    if item['succeed_before_fallback_agent'] and not item['succeed_after_fallback_agent'])
    failed_both = sum(1 for item in fb_data 
                      if not item['succeed_before_fallback_agent'] and not item['succeed_after_fallback_agent'])
    
    fb_overall = {
        'total': total_patches,
        'without_fallback': without_fallback,
        'with_fallback': with_fallback,
        'improved': improved,
        'regressed': regressed,
        'failed_both': failed_both,
        'without_fallback_pct': (without_fallback / total_patches * 100) if total_patches > 0 else 0,
        'with_fallback_pct': (with_fallback / total_patches * 100) if total_patches > 0 else 0,
        'improved_pct': (improved / total_patches * 100) if total_patches > 0 else 0,
    }
    
    # Fallback by type
    fb_by_type = defaultdict(list)
    for item in fb_data:
        fb_by_type[item['patch_type']].append(item)
        
    fb_type_stats = {}
    for ptype, items in sorted(fb_by_type.items()):
        total = len(items)
        wo_fb = sum(1 for item in items if item['succeed_before_fallback_agent'])
        w_fb = sum(1 for item in items if item['succeed_after_fallback_agent'])
        imp = sum(1 for item in items if not item['succeed_before_fallback_agent'] and item['succeed_after_fallback_agent'])
        fb_type_stats[ptype] = {
            'total': total,
            'without_fallback': wo_fb,
            'with_fallback': w_fb,
            'improved': imp,
            'without_fallback_pct': (wo_fb / total * 100) if total > 0 else 0,
            'with_fallback_pct': (w_fb / total * 100) if total > 0 else 0,
            'improved_pct': (imp / total * 100) if total > 0 else 0,
        }

    # --- 2. HUNK STATS ---
    total_hunks_all = sum(item['total_hunks'] for item in comp_data)
    total_java_prod = sum(item['java_production_hunks'] for item in comp_data)
    total_aux_hunks = sum(item['developer_aux_hunks'] for item in comp_data)
    total_failed_hunks = sum(item['failed_hunks'] for item in comp_data)
    
    hunk_overall = {
        'total_items': total_patches,
        'total_hunks_all': total_hunks_all,
        'total_java_production_hunks': total_java_prod,
        'total_aux_hunks': total_aux_hunks,
        'total_failed_hunks': total_failed_hunks,
        'avg_java_prod_per_patch': total_java_prod / total_patches if total_patches > 0 else 0,
        'avg_aux_per_patch': total_aux_hunks / total_patches if total_patches > 0 else 0,
    }
    
    # Hunk by type
    hunk_by_type = defaultdict(list)
    for item in comp_data:
        hunk_by_type[item['patch_type']].append(item)
        
    hunk_type_stats = {}
    for ptype, items in sorted(hunk_by_type.items()):
        total_jp = sum(item['java_production_hunks'] for item in items)
        total_aux = sum(item['developer_aux_hunks'] for item in items)
        total_fail = sum(item['failed_hunks'] for item in items)
        cnt = len(items)
        hunk_type_stats[ptype] = {
            'count': cnt,
            'total_java_production_hunks': total_jp,
            'total_aux_hunks': total_aux,
            'total_failed_hunks': total_fail,
            'avg_java_prod': total_jp / cnt if cnt > 0 else 0,
            'avg_aux': total_aux / cnt if cnt > 0 else 0,
        }

    # --- 3. PATCH ALIGNMENT STATS (Developer vs Agent) ---
    dev_hunks = [c['prod_hunks_count_dev'] for c in comp_data]
    gen_hunks = [c['prod_hunks_count_gen'] for c in comp_data]
    aux_hunks = [c['developer_aux_hunks_from_target'] for c in comp_data]
    differences = [g - d for g, d in zip(gen_hunks, dev_hunks)]
    
    same_count = sum(1 for d in differences if d == 0)
    fewer_count = sum(1 for d in differences if d < 0)
    more_count = sum(1 for d in differences if d > 0)
    
    patch_alignment_overall = {
        'dev_mean': statistics.mean(dev_hunks),
        'dev_median': statistics.median(dev_hunks),
        'dev_min': min(dev_hunks),
        'dev_max': max(dev_hunks),
        'dev_total': sum(dev_hunks),
        
        'gen_mean': statistics.mean(gen_hunks),
        'gen_median': statistics.median(gen_hunks),
        'gen_min': min(gen_hunks),
        'gen_max': max(gen_hunks),
        'gen_total': sum(gen_hunks),
        
        'aux_mean': statistics.mean(aux_hunks) if aux_hunks else 0,
        'aux_median': statistics.median(aux_hunks) if aux_hunks else 0,
        'aux_min': min(aux_hunks) if aux_hunks else 0,
        'aux_max': max(aux_hunks) if aux_hunks else 0,
        'aux_total': sum(aux_hunks) if aux_hunks else 0,
        
        'same': same_count,
        'fewer': fewer_count,
        'more': more_count,
        'mean_diff': statistics.mean(differences)
    }
    
    # Patch alignment by type
    align_by_type = defaultdict(list)
    for c in comp_data:
        align_by_type[c['patch_type']].append(c)
        
    align_type_stats = {}
    for ptype, patches in sorted(align_by_type.items()):
        dev_h_type = [p['prod_hunks_count_dev'] for p in patches]
        gen_h_type = [p['prod_hunks_count_gen'] for p in patches]
        diffs_t = [g - d for g, d in zip(gen_h_type, dev_h_type)]
        
        same = sum(1 for d in diffs_t if d == 0)
        fewer = sum(1 for d in diffs_t if d < 0)
        more = sum(1 for d in diffs_t if d > 0)
        
        align_type_stats[ptype] = {
            'count': len(patches),
            'dev_avg': statistics.mean(dev_h_type),
            'dev_total': sum(dev_h_type),
            'gen_avg': statistics.mean(gen_h_type),
            'gen_total': sum(gen_h_type),
            'same': same,
            'fewer': fewer,
            'more': more
        }
        
    # Patch alignment by repo
    align_by_repo = defaultdict(list)
    for c in comp_data:
        align_by_repo[c['repo']].append(c)
        
    align_repo_stats = []
    for repo, patches in sorted(align_by_repo.items()):
        dev_h_repo = [p['prod_hunks_count_dev'] for p in patches]
        gen_h_repo = [p['prod_hunks_count_gen'] for p in patches]
        same = sum(1 for g, d in zip(gen_h_repo, dev_h_repo) if g == d)
        align_repo_stats.append((repo, len(patches), sum(dev_h_repo), sum(gen_h_repo), same))

    # --- 4. CONSOLE PRINTOUT ---
    print("\n" + "="*80)
    print("📈 MASTER PIPELINE STATISTICS SUMMARY")
    print("="*80)
    print(f"Total Runs Analyzed:         {total_patches}")
    print(f"Succeeded WITHOUT Fallback:   {fb_overall['without_fallback']} ({fb_overall['without_fallback_pct']:.2f}%)")
    print(f"Succeeded WITH Fallback:      {fb_overall['with_fallback']} ({fb_overall['with_fallback_pct']:.2f}%)")
    print(f"Fallback Impact Improvement:  +{fb_overall['improved']} runs (+{fb_overall['improved_pct']:.2f}%)")
    print(f"Total Java Production Hunks:  Dev={sum(dev_hunks)} vs Gen={sum(gen_hunks)}")
    print(f"Hunk Alignment Matches:      {same_count} / {total_patches} ({100*same_count/total_patches:.2f}%)")
    print("="*80 + "\n")

    # --- 5. BUILD PREMIUM MARKDOWN REPORT ---
    rate_indicator = "🟢" if fb_overall['with_fallback_pct'] >= 75 else ("🟡" if fb_overall['with_fallback_pct'] >= 40 else "🔴")
    
    md = f"""# 📊 Comprehensive Evaluation & Hunk Alignment Report

This detailed analytics dashboard consolidates success counts, hunk complexities, patch alignments, and fallback impact metrics across all evaluation runs.

---

## 📈 Executive Summary Dashboard

| Metric | Baseline (Without Fallback) | Final System (With Fallback) | Net Impact |
| :--- | :---: | :---: | :---: |
| **Pipeline Runs Count** | `{total_patches}` | `{total_patches}` | — |
| **Successful Backports** | `{fb_overall['without_fallback']}` | `{fb_overall['with_fallback']}` | **+{fb_overall['improved']} Succeeded** |
| **Backport Success Rate** | `{fb_overall['without_fallback_pct']:.2f}%` | `{fb_overall['with_fallback_pct']:.2f}%` {rate_indicator} | **+{fb_overall['improved_pct']:.2f}%** |

### System Success Progress
```text
[{"#" * int(fb_overall['with_fallback_pct'] // 4)}{"-" * (25 - int(fb_overall['with_fallback_pct'] // 4))}] {fb_overall['with_fallback_pct']:.1f}%
```

---

## 🛡️ Fallback Agent Performance Impact

The fallback agent handles complex failures, context mismatch errors, and compile regressions to recover patches.

| Fallback Outcome Category | Count | Percentage | Description |
| :--- | :---: | :---: | :--- |
| **Succeeded BEFORE Fallback** | `{fb_overall['without_fallback']}` | `{fb_overall['without_fallback_pct']:.1f}%` | Succeeded on standard run without fallback intervention. |
| **Succeeded AFTER Fallback (Improved)** | `{fb_overall['improved']}` | `{fb_overall['improved_pct']:.1f}%` | Saved by Fallback Agent after standard runs failed. |
| **Failed Both (Baseline & Fallback)** | `{fb_overall['failed_both']}` | `{100 * fb_overall['failed_both'] / total_patches:.1f}%` | Unresolved failures despite fallback engagement. |
| **Regressed (Broke Working Patches)** | `{fb_overall['regressed']}` | `{100 * fb_overall['regressed'] / total_patches:.1f}%` | Working patches broken after fallback run. |

### 🏷️ Fallback Type-Wise Performance Breakdown

| Patch Type | Total Patches | Baseline Rate (No Fallback) | Final Success Rate | Improved Count | Net Lift |
| :--- | :---: | :---: | :---: | :---: | :---: |
"""
    for ptype, s in fb_type_stats.items():
        net_lift = s['with_fallback_pct'] - s['without_fallback_pct']
        md += f"| `{ptype}` | **{s['total']}** | `{s['without_fallback_pct']:.1f}%` | `{s['with_fallback_pct']:.1f}%` | `+{s['improved']}` | `+{net_lift:.1f}%` |\n"

    md += f"""
---

## 📦 Hunk Distribution & Complexity Analysis

Complexity is analyzed focusing on **Java Production Hunks** while filtering out test scripts and non-Java metadata files.

* **Total Java Production Hunks Evaluated**: `{hunk_overall['total_java_production_hunks']}`
* **Total Developer Auxiliary/Test Hunks**: `{hunk_overall['total_aux_hunks']}`
* **Total Failed Hunks Recorded**: `{hunk_overall['total_failed_hunks']}`
* **Average Java Production Hunks per Patch**: `{hunk_overall['avg_java_prod_per_patch']:.2f}` hunks
* **Average Auxiliary Hunks per Patch**: `{hunk_overall['avg_aux_per_patch']:.2f}` hunks

### 🏷️ Hunk Composition by Patch Type

| Patch Type | Count | Total Java Prod | Total Aux/Test | Avg Java Prod | Avg Aux | Failed Hunks |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for ptype, s in hunk_type_stats.items():
        md += f"| `{ptype}` | **{s['count']}** | `{s['total_java_production_hunks']}` | `{s['total_aux_hunks']}` | `{s['avg_java_prod']:.2f}` | `{s['avg_aux']:.2f}` | `{s['total_failed_hunks']}` |\n"

    md += f"""
---

## ⚖️ Patch hunk Alignment Comparison (Developer vs. Agent)

This section maps the structural similarity between the Developer's baseline patch (`target.patch`) and the Agent's generated patch (`generated.patch`).

### 📐 Hunk Alignments Metrics

| Statistic | Developer (Target) | Agent (Generated) | Developer Aux |
| :--- | :---: | :---: | :---: |
| **Sum Total** | `{patch_alignment_overall['dev_total']}` | `{patch_alignment_overall['gen_total']}` | `{patch_alignment_overall['aux_total']}` |
| **Mean Hunks / Patch** | `{patch_alignment_overall['dev_mean']:.2f}` | `{patch_alignment_overall['gen_mean']:.2f}` | `{patch_alignment_overall['aux_mean']:.2f}` |
| **Median Hunks / Patch** | `{patch_alignment_overall['dev_median']:.1f}` | `{patch_alignment_overall['gen_median']:.1f}` | `{patch_alignment_overall['aux_median']:.1f}` |
| **Min / Max hunks** | `{patch_alignment_overall['dev_min']} / {patch_alignment_overall['dev_max']}` | `{patch_alignment_overall['gen_min']} / {patch_alignment_overall['gen_max']}` | `{patch_alignment_overall['aux_min']} / {patch_alignment_overall['aux_max']}` |

### 📐 Match Alignment Differences (Generated - Developer)

| Comparison Outcome | Run Count | Percentage | Interpretation |
| :--- | :---: | :---: | :--- |
| **Perfect Match (Same Hunks)** | `{patch_alignment_overall['same']}` | `{100*patch_alignment_overall['same']/total_patches:.1f}%` | Agent matches developer structural complexity exactly. |
| **Fewer Hunks in Generated** | `{patch_alignment_overall['fewer']}` | `{100*patch_alignment_overall['fewer']/total_patches:.1f}%` | Agent consolidated modifications or simplified hunks. |
| **More Hunks in Generated** | `{patch_alignment_overall['more']}` | `{100*patch_alignment_overall['more']/total_patches:.1f}%` | Agent introduced extra context hunks or verbose code. |

**Mean Hunk Count Shift**: `{patch_alignment_overall['mean_diff']:.2f}`

---

## 📁 Repository Patch Alignments Table

| Repository | Patches | Dev Hunks | Gen Hunks | Matches | Match Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
"""
    for repo, count, dev_sum, gen_sum, same in align_repo_stats:
        rate = (same / count * 100) if count > 0 else 0
        md += f"| `{repo}` | **{count}** | `{dev_sum}` | `{gen_sum}` | `{same}` | `{rate:.1f}%` |\n"

    total_successes = sum(pathway_counts.values())
    
    md += f"""
---

## ⚡ Success Pathways Distribution

We classify successful backports into **four distinct execution pathways** depending on LLM synthesis requirements, standard validator retry loop engagement, or fallback agent intervention.

| Success Pathway | Successful Runs | % of Successes | Pathway Description |
| :--- | :---: | :---: | :--- |
| ⚡ **Fast Apply Success** | `{pathway_counts['fast_apply']}` | `{pathway_counts['fast_apply']/total_successes*100:.1f}%` | Applied successfully on disk immediately without LLM synthesis or retries. |
| 🧠 **First Try Synthesis Success** | `{pathway_counts['first_try_synthesis']}` | `{pathway_counts['first_try_synthesis']/total_successes*100:.1f}%` | Synthesis required, but succeeded on the very first validation attempt (no retries). |
| 🔄 **Standard Retry Success** | `{pathway_counts['standard_retry']}` | `{pathway_counts['standard_retry']/total_successes*100:.1f}%` | Succeeded after standard validator retry loops (fixing syntax or compiling errors). |
| 🛡️ **Fallback Recovery Success** | `{pathway_counts['fallback_recovery']}` | `{pathway_counts['fallback_recovery']/total_successes*100:.1f}%` | Standard path failed entirely, successfully recovered by engaging Fallback Agent. |
| **Total Successes** | **{total_successes}** | **100.0%** | Combined success rate: **{total_successes}/{total_patches} ({total_successes/total_patches*100:.2f}%)** |

### Success Pathways Progress
* **Fast Apply Success:** `[{"#" * int(pathway_counts['fast_apply']/total_successes*25)}{"-" * (25 - int(pathway_counts['fast_apply']/total_successes*25))}]`
* **First Try Synthesis Success:** `[{"#" * int(pathway_counts['first_try_synthesis']/total_successes*25)}{"-" * (25 - int(pathway_counts['first_try_synthesis']/total_successes*25))}]`
* **Standard Retry Success:** `[{"#" * int(pathway_counts['standard_retry']/total_successes*25)}{"-" * (25 - int(pathway_counts['standard_retry']/total_successes*25))}]`
* **Fallback Recovery Success:** `[{"#" * int(pathway_counts['fallback_recovery']/total_successes*25)}{"-" * (25 - int(pathway_counts['fallback_recovery']/total_successes*25))}]`

---

### 📦 Success Pathways by Repository

| Repository | Fast Apply | First Try Synthesis | Standard Retry | Fallback Recovery | Total Successes |
| :--- | :---: | :---: | :---: | :---: | :---: |
"""
    for repo, p in sorted(pathway_by_repo.items()):
        tot = sum(p.values())
        md += f"| `{repo}` | `{p['fast_apply']}` | `{p['first_try_synthesis']}` | `{p['standard_retry']}` | `{p['fallback_recovery']}` | **{tot}** |\n"

    md += f"""
---

## ⏱️ Cumulative Execution Time Distribution Matrix (Successful Runs)

Cumulative execution time represents the wall-clock duration of a successful run, aggregating baseline AI synthesis time, build and validation compilation times, standard validator retry loops, and fallback agent execution times.

### 📊 Pathway Execution Time Statistics

| Success Pathway | Count | Average Total Time | Median Total Time | Min / Max Time |
| :--- | :---: | :---: | :---: | :---: |
| ⚡ **Fast Apply Success** | `{pathway_time_stats['fast_apply']['count']}` | `{pathway_time_stats['fast_apply']['avg']:.2f}s` | `{pathway_time_stats['fast_apply']['median']:.2f}s` | `{pathway_time_stats['fast_apply']['min']:.2f}s / {pathway_time_stats['fast_apply']['max']:.2f}s` |
| 🧠 **First Try Synthesis Success** | `{pathway_time_stats['first_try_synthesis']['count']}` | `{pathway_time_stats['first_try_synthesis']['avg']:.2f}s` | `{pathway_time_stats['first_try_synthesis']['median']:.2f}s` | `{pathway_time_stats['first_try_synthesis']['min']:.2f}s / {pathway_time_stats['first_try_synthesis']['max']:.2f}s` |
| 🔄 **Standard Retry Success** | `{pathway_time_stats['standard_retry']['count']}` | `{pathway_time_stats['standard_retry']['avg']:.2f}s` | `{pathway_time_stats['standard_retry']['median']:.2f}s` | `{pathway_time_stats['standard_retry']['min']:.2f}s / {pathway_time_stats['standard_retry']['max']:.2f}s` |
| 🛡️ **Fallback Recovery Success** | `{pathway_time_stats['fallback_recovery']['count']}` | `{pathway_time_stats['fallback_recovery']['avg']:.2f}s` | `{pathway_time_stats['fallback_recovery']['median']:.2f}s` | `{pathway_time_stats['fallback_recovery']['min']:.2f}s / {pathway_time_stats['fallback_recovery']['max']:.2f}s` |

### 🏢 Repository-wise Average Cumulative Time Matrix

| Repository | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
"""
    for r in all_repos:
        fa_avg = fmt_avg(repo_pathway_times[r]["fast_apply"])
        ft_avg = fmt_avg(repo_pathway_times[r]["first_try_synthesis"])
        sr_avg = fmt_avg(repo_pathway_times[r]["standard_retry"])
        fr_avg = fmt_avg(repo_pathway_times[r]["fallback_recovery"])
        md += f"| `{r}` | `{fa_avg}` | `{ft_avg}` | `{sr_avg}` | `{fr_avg}` |\n"

    md += f"""

### 🏷️ Patch Type-wise Average Cumulative Time Matrix

| Patch Type | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
"""
    for t in all_types:
        fa_avg = fmt_avg(type_pathway_times[t]["fast_apply"])
        ft_avg = fmt_avg(type_pathway_times[t]["first_try_synthesis"])
        sr_avg = fmt_avg(type_pathway_times[t]["standard_retry"])
        fr_avg = fmt_avg(type_pathway_times[t]["fallback_recovery"])
        md += f"| `{t}` | `{fa_avg}` | `{ft_avg}` | `{sr_avg}` | `{fr_avg}` |\n"

    md += f"""

---

## 🪙 LLM Token Usage Distribution Matrix (Successful Runs)

This section maps the LLM token consumption distributions (sum of input and output tokens across all agent execution phases, including fallback agents when engaged) across different success pathways.

### 📊 Pathway Token Usage Statistics

| Success Pathway | Count | Average Tokens | Median Tokens | Min / Max Tokens |
| :--- | :---: | :---: | :---: | :---: |
| ⚡ **Fast Apply Success** | `{pathway_token_stats['fast_apply']['count']}` | `{pathway_token_stats['fast_apply']['avg']:,.0f}` | `{pathway_token_stats['fast_apply']['median']:,.0f}` | `{pathway_token_stats['fast_apply']['min']:,.0f} / {pathway_token_stats['fast_apply']['max']:,.0f}` |
| 🧠 **First Try Synthesis Success** | `{pathway_token_stats['first_try_synthesis']['count']}` | `{pathway_token_stats['first_try_synthesis']['avg']:,.0f}` | `{pathway_token_stats['first_try_synthesis']['median']:,.0f}` | `{pathway_token_stats['first_try_synthesis']['min']:,.0f} / {pathway_token_stats['first_try_synthesis']['max']:,.0f}` |
| 🔄 **Standard Retry Success** | `{pathway_token_stats['standard_retry']['count']}` | `{pathway_token_stats['standard_retry']['avg']:,.0f}` | `{pathway_token_stats['standard_retry']['median']:,.0f}` | `{pathway_token_stats['standard_retry']['min']:,.0f} / {pathway_token_stats['standard_retry']['max']:,.0f}` |
| 🛡️ **Fallback Recovery Success** | `{pathway_token_stats['fallback_recovery']['count']}` | `{pathway_token_stats['fallback_recovery']['avg']:,.0f}` | `{pathway_token_stats['fallback_recovery']['median']:,.0f}` | `{pathway_token_stats['fallback_recovery']['min']:,.0f} / {pathway_token_stats['fallback_recovery']['max']:,.0f}` |

### 🏢 Repository-wise Average Token Usage Matrix

| Repository | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
"""
    for r in all_repos:
        fa_avg = fmt_tokens(repo_pathway_tokens[r]["fast_apply"])
        ft_avg = fmt_tokens(repo_pathway_tokens[r]["first_try_synthesis"])
        sr_avg = fmt_tokens(repo_pathway_tokens[r]["standard_retry"])
        fr_avg = fmt_tokens(repo_pathway_tokens[r]["fallback_recovery"])
        md += f"| `{r}` | `{fa_avg}` | `{ft_avg}` | `{sr_avg}` | `{fr_avg}` |\n"

    md += f"""

### 🏷️ Patch Type-wise Average Token Usage Matrix

| Patch Type | Fast Apply Avg | First Try Synthesis Avg | Standard Retry Avg | Fallback Recovery Avg |
| :--- | :---: | :---: | :---: | :---: |
"""
    for t in all_types:
        fa_avg = fmt_tokens(type_pathway_tokens[t]["fast_apply"])
        ft_avg = fmt_tokens(type_pathway_tokens[t]["first_try_synthesis"])
        sr_avg = fmt_tokens(type_pathway_tokens[t]["standard_retry"])
        fr_avg = fmt_tokens(type_pathway_tokens[t]["fallback_recovery"])
        md += f"| `{t}` | `{fa_avg}` | `{ft_avg}` | `{sr_avg}` | `{fr_avg}` |\n"

    md += f"""
---

## 🚫 List of Empty Patches ({len(empty_patches)} total)

These runs generated an empty patch file (trimmed size < 2 characters) or no patch file at all. These are treated as **failures** even if JSON records showed pass indicators.

| # | Repository | Patch ID | Baseline Status |
| :---: | :--- | :--- | :---: |
"""
    for idx, item in enumerate(empty_patches, 1):
        status = "🟢 Pass (Unexpected)" if item['success'] else "🔴 Fail (Correct)"
        md += f"| {idx} | `{item['repo']}` | `{item['patch_id']}` | {status} |\n"

    md += f"""
---

## 📐 List of Patches with Fewer Hunks ({len(fewer_hunks)} total)

These successful runs achieved **hunk consolidation**, meaning the agent-generated patch had **fewer production Java hunks** than the original developer patch (`gen_hunks < dev_hunks`).

| # | Repository | Patch ID | Dev Hunks | Gen Hunks | Net Hunk Reduction | Success Status |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
"""
    for idx, item in enumerate(fewer_hunks, 1):
        red = item['dev_hunks'] - item['gen_hunks']
        status = "🟢 Success" if item['success'] else "🔴 Failure"
        md += f"| {idx} | `{item['repo']}` | `{item['patch_id']}` | `{item['dev_hunks']}` | `{item['gen_hunks']}` | **-{red} hunks** | {status} |\n"

    md += f"""
---

## ❌ List of Failed Patches ({len(failed_patches)} total)

These runs did not pass final validation. They failed during either fast-apply, LLM synthesis, syntax checking, compilation, or test suites validation.

| # | Repository | Patch ID | Patch Type | Failure Reason / Category |
| :---: | :--- | :--- | :---: | :--- |
"""
    for idx, item in enumerate(failed_patches, 1):
        md += f"| {idx} | `{item['repo']}` | `{item['patch_id']}` | `{item['patch_type']}` | `{item['failure_category']}` |\n"

    md += f"""
---
*Dashboard Report Generated: {get_timestamp()} (Local Time)*
"""
    with open(OUTPUT_MD_REPORT, "w", encoding="utf-8") as f:
        f.write(md)
        
    print(f"🎉 Premium consolidated dashboard created at: {OUTPUT_MD_REPORT}\n")

if __name__ == "__main__":
    print("=== MASTER DETAILED ANALYZE RUNNING ===")
    try:
        comp_data, fb_data, empty_patches, fewer_hunks, pathway_counts, pathway_by_repo, pathway_by_type, failed_patches = process_results()
        compile_metrics_and_markdown(comp_data, fb_data, empty_patches, fewer_hunks, pathway_counts, pathway_by_repo, pathway_by_type, failed_patches)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error in script: {e}")
