#!/usr/bin/env python3
"""
Script to extract hunk counts from results.json files.
Focuses on Java production hunks (excluding test files and non-Java files).
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict


def extract_hunk_info(results_json_path: str) -> Dict[str, Any]:
    """
    Extract hunk information from a results.json file.
    
    Returns dict with:
    - patch_id: original_commit (first 8 chars)
    - repo: repository name
    - patch_type: patch type
    - total_hunks: total hunks in patch
    - java_production_hunks: production Java files only (what we want)
    - developer_aux_hunks: auxiliary/test hunks
    - failed_hunks_total: hunks that failed
    - file_path: path to the results file
    """
    try:
        with open(results_json_path, 'r') as f:
            data = json.load(f)
        
        summary = data.get('summary', {})
        
        patch_id = data.get('original_commit', '')[:8]
        repo = data.get('repo', 'UNKNOWN')
        patch_type = data.get('patch_type', 'UNKNOWN')
        
        total_hunks = summary.get('total_hunks_in_patch', 0)
        java_production_hunks = summary.get('java_production_hunks', 0)
        developer_aux_hunks = summary.get('developer_aux_hunks', 0)
        failed_hunks = summary.get('failed_hunks_total', 0)
        
        return {
            'patch_id': patch_id,
            'repo': repo,
            'patch_type': patch_type,
            'total_hunks': total_hunks,
            'java_production_hunks': java_production_hunks,
            'developer_aux_hunks': developer_aux_hunks,
            'failed_hunks': failed_hunks,
            'file_path': results_json_path
        }
    
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        print(f"Error processing {results_json_path}: {e}", file=sys.stderr)
        return None


def find_results_json_files(directory: str) -> List[str]:
    """Recursively find all results.json files in the directory."""
    results_files = []
    path = Path(directory)
    
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    
    for results_file in path.rglob('results.json'):
        results_files.append(str(results_file))
    
    return sorted(results_files)


def print_detailed_report(data: List[Dict[str, Any]]):
    """Print detailed hunk information."""
    print("=" * 110)
    print("DETAILED HUNK BREAKDOWN".center(110))
    print("=" * 110)
    print()
    
    print(f"{'Type':<12} {'Patch ID':<10} {'Repo':<20} {'Total':>8} {'Java Prod':>12} {'Aux/Test':>10} {'Failed':>8}")
    print("-" * 110)
    
    for item in data:
        print(f"{item['patch_type']:<12} {item['patch_id']:<10} {item['repo']:<20} "
              f"{item['total_hunks']:>8} {item['java_production_hunks']:>12} "
              f"{item['developer_aux_hunks']:>10} {item['failed_hunks']:>8}")
    
    print()


def calculate_summary_stats(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary statistics for hunks."""
    total_items = len(data)
    
    total_hunks_all = sum(item['total_hunks'] for item in data)
    total_java_prod = sum(item['java_production_hunks'] for item in data)
    total_aux = sum(item['developer_aux_hunks'] for item in data)
    total_failed = sum(item['failed_hunks'] for item in data)
    
    return {
        'total_items': total_items,
        'total_hunks_all': total_hunks_all,
        'total_java_production_hunks': total_java_prod,
        'total_aux_hunks': total_aux,
        'total_failed_hunks': total_failed,
        'avg_java_prod_per_patch': total_java_prod / total_items if total_items > 0 else 0,
        'avg_aux_per_patch': total_aux / total_items if total_items > 0 else 0,
    }


def calculate_type_stats(data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Calculate statistics by patch type."""
    by_type = defaultdict(list)
    
    for item in data:
        by_type[item['patch_type']].append(item)
    
    type_stats = {}
    for patch_type in sorted(by_type.keys()):
        items = by_type[patch_type]
        
        total_java_prod = sum(item['java_production_hunks'] for item in items)
        total_aux = sum(item['developer_aux_hunks'] for item in items)
        total_failed = sum(item['failed_hunks'] for item in items)
        count = len(items)
        
        type_stats[patch_type] = {
            'count': count,
            'total_java_production_hunks': total_java_prod,
            'total_aux_hunks': total_aux,
            'total_failed_hunks': total_failed,
            'avg_java_prod': total_java_prod / count if count > 0 else 0,
            'avg_aux': total_aux / count if count > 0 else 0,
        }
    
    return type_stats


def print_summary_stats(stats: Dict[str, Any], type_stats: Dict[str, Dict[str, Any]]):
    """Print summary statistics."""
    print("=" * 110)
    print("SUMMARY STATISTICS - HUNK COUNTS".center(110))
    print("=" * 110)
    print()
    
    print("OVERALL:")
    print(f"  Total patches analyzed:           {stats['total_items']}")
    print(f"  Total hunks (all types):          {stats['total_hunks_all']}")
    print(f"  Total Java production hunks:      {stats['total_java_production_hunks']}")
    print(f"  Total auxiliary/test hunks:       {stats['total_aux_hunks']}")
    print(f"  Total failed hunks:               {stats['total_failed_hunks']}")
    print()
    print(f"  Average Java prod hunks/patch:    {stats['avg_java_prod_per_patch']:.2f}")
    print(f"  Average auxiliary hunks/patch:    {stats['avg_aux_per_patch']:.2f}")
    print()
    
    print("=" * 110)
    print("TYPE-WISE HUNK STATISTICS".center(110))
    print("=" * 110)
    print()
    
    print(f"{'Type':<12} {'Count':>8} {'Total Java Prod':>18} {'Total Aux/Test':>16} {'Avg Java Prod':>15} {'Avg Aux':>10}")
    print("-" * 110)
    
    for patch_type in sorted(type_stats.keys()):
        ts = type_stats[patch_type]
        print(f"{patch_type:<12} {ts['count']:>8} {ts['total_java_production_hunks']:>18} "
              f"{ts['total_aux_hunks']:>16} {ts['avg_java_prod']:>15.2f} {ts['avg_aux']:>10.2f}")
    
    print()


def generate_csv_output(data: List[Dict[str, Any]], output_file: str):
    """Generate CSV output with hunk information."""
    import csv
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'patch_id', 'repo', 'patch_type', 'total_hunks', 
            'java_production_hunks', 'developer_aux_hunks', 'failed_hunks'
        ])
        writer.writeheader()
        
        for item in data:
            writer.writerow({
                'patch_id': item['patch_id'],
                'repo': item['repo'],
                'patch_type': item['patch_type'],
                'total_hunks': item['total_hunks'],
                'java_production_hunks': item['java_production_hunks'],
                'developer_aux_hunks': item['developer_aux_hunks'],
                'failed_hunks': item['failed_hunks']
            })


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_hunk_counts.py <input_directory> [csv_output_file]")
        print("\nExample:")
        print("  python extract_hunk_counts.py tests/shadow_run_results_v3")
        print("  python extract_hunk_counts.py tests/shadow_run_results_v3 output/hunk_counts.csv")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    csv_output = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Validate input directory
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Find all results.json files
    print(f"Searching for results.json files in {input_dir}...")
    results_files = find_results_json_files(input_dir)
    
    if not results_files:
        print(f"No results.json files found in {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(results_files)} results.json file(s)\n")
    
    # Extract hunk information
    hunk_data = []
    failed_count = 0
    
    for results_file in results_files:
        hunk_info = extract_hunk_info(results_file)
        if hunk_info:
            hunk_data.append(hunk_info)
        else:
            failed_count += 1
    
    # Print detailed report
    print_detailed_report(hunk_data)
    
    # Calculate and print statistics
    summary_stats = calculate_summary_stats(hunk_data)
    type_stats = calculate_type_stats(hunk_data)
    print_summary_stats(summary_stats, type_stats)
    
    # Generate CSV if requested
    if csv_output:
        os.makedirs(os.path.dirname(csv_output) if os.path.dirname(csv_output) else '.', exist_ok=True)
        generate_csv_output(hunk_data, csv_output)
        print(f"CSV output written to: {csv_output}\n")
    
    print(f"Successfully processed: {len(hunk_data)}")
    print(f"Failed to parse: {failed_count}")


if __name__ == '__main__':
    main()
