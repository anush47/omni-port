#!/usr/bin/env python3
"""
Extract and compare production hunks from developer patch (target.patch) 
vs generated patch (generated.patch) at file level.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
import sys


def find_results_json_files(base_dir):
    """Recursively find all results.json files."""
    return sorted(base_dir.rglob("results.json"))


def parse_patch_file(patch_path):
    """
    Parse a git diff patch file and return:
    - file_hunks: dict mapping file_path -> count of hunks
    - file_list: list of all files in the patch
    """
    if not patch_path.exists():
        return {}, []
    
    try:
        with open(patch_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {patch_path}: {e}", file=sys.stderr)
        return {}, []
    
    file_hunks = defaultdict(int)
    file_list = []
    current_file = None
    
    # Pattern to match: diff --git a/path b/path
    file_pattern = r'^diff --git a/(.+) b/(.+)$'
    # Pattern to match hunk header: @@ ... @@
    hunk_pattern = r'^@@'
    
    lines = content.split('\n')
    for line in lines:
        # Check if this is a new file marker
        file_match = re.match(file_pattern, line)
        if file_match:
            current_file = file_match.group(1)
            if current_file not in file_list:
                file_list.append(current_file)
        
        # Check if this is a hunk marker
        if current_file and re.match(hunk_pattern, line):
            file_hunks[current_file] += 1
    
    return dict(file_hunks), file_list


def is_java_file(file_path):
    """Check if file is a Java production file (exclude test files)."""
    if not file_path.endswith('.java'):
        return False
    # Exclude test files
    if '/test/' in file_path or '/tests/' in file_path:
        return False
    return True


def count_java_production_hunks(file_hunks, file_list):
    """Count hunks only from Java production files."""
    total = 0
    for file_path in file_list:
        if is_java_file(file_path):
            total += file_hunks.get(file_path, 0)
    return total


def extract_patch_comparison(result_json_path):
    """
    Extract patch comparison data from a single patch directory.
    Returns dict with comparison data or None if processing fails.
    """
    try:
        with open(result_json_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {result_json_path}: {e}", file=sys.stderr)
        return None
    
    # Get basic info
    patch_id = result_json_path.parent.name
    repo = data.get('repo', 'unknown')
    patch_type = data.get('patch_type', 'unknown')
    
    # Get developer_aux_hunks_from_target from summary
    summary = data.get('summary', {})
    dev_aux_from_target = summary.get('developer_aux_hunks_from_target', 0)
    
    # Parse patches
    patch_dir = result_json_path.parent
    target_patch_path = patch_dir / 'target.patch'
    generated_patch_path = patch_dir / 'generated.patch'
    
    target_hunks, target_files = parse_patch_file(target_patch_path)
    generated_hunks, generated_files = parse_patch_file(generated_patch_path)
    
    # Count Java production hunks
    target_java_prod_hunks = count_java_production_hunks(target_hunks, target_files)
    generated_java_prod_hunks = count_java_production_hunks(generated_hunks, generated_files)
    
    # Build file-level comparison for Java production files only
    files_comparison = []
    all_java_files = set()
    
    # Collect all Java production files from both patches
    for file_path in target_files:
        if is_java_file(file_path):
            all_java_files.add(file_path)
    for file_path in generated_files:
        if is_java_file(file_path):
            all_java_files.add(file_path)
    
    # Build comparison for each file
    for file_path in sorted(all_java_files):
        files_comparison.append({
            "file_path": file_path,
            "hunks_in_target": target_hunks.get(file_path, 0),
            "hunks_in_generated": generated_hunks.get(file_path, 0)
        })
    
    return {
        "patch_id": patch_id,
        "repo": repo,
        "patch_type": patch_type,
        "prod_hunks_count_dev": target_java_prod_hunks,
        "prod_hunks_count_gen": generated_java_prod_hunks,
        "developer_aux_hunks_from_target": dev_aux_from_target,
        "files": files_comparison
    }


def main():
    base_dir = Path('tests/shadow_run_results_v3')
    output_file = Path('output/patch_comparison.json')
    
    if not base_dir.exists():
        print(f"Error: {base_dir} does not exist")
        sys.exit(1)
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    results_json_files = find_results_json_files(base_dir)
    print(f"Found {len(results_json_files)} patches")
    
    all_comparisons = []
    failed = []
    
    for i, result_json_path in enumerate(results_json_files, 1):
        if i % 50 == 0:
            print(f"Processing {i}/{len(results_json_files)}...", file=sys.stderr)
        
        comparison = extract_patch_comparison(result_json_path)
        if comparison:
            all_comparisons.append(comparison)
        else:
            failed.append(str(result_json_path))
    
    # Write output
    with open(output_file, 'w') as f:
        json.dump(all_comparisons, f, indent=2)
    
    print(f"\nProcessed: {len(all_comparisons)}/{len(results_json_files)} patches")
    print(f"Output: {output_file}")
    
    if failed:
        print(f"Failed: {len(failed)} patches")
        for path in failed[:5]:
            print(f"  - {path}")
        if len(failed) > 5:
            print(f"  ... and {len(failed) - 5} more")


if __name__ == '__main__':
    main()
