#!/usr/bin/env python3
"""
Script to analyze fallback agent statistics from the fallback_analysis.json file.
Generates success rates and type-wise breakdowns.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


def load_analysis_data(json_file: str) -> List[Dict[str, Any]]:
    """Load the fallback analysis JSON file."""
    with open(json_file, 'r') as f:
        return json.load(f)


def calculate_statistics(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate overall statistics."""
    total = len(data)
    
    without_fallback = sum(1 for item in data if item['succeed_before_fallback_agent'])
    with_fallback = sum(1 for item in data if item['succeed_after_fallback_agent'])
    improved = sum(1 for item in data 
                   if not item['succeed_before_fallback_agent'] and item['succeed_after_fallback_agent'])
    regressed = sum(1 for item in data 
                    if item['succeed_before_fallback_agent'] and not item['succeed_after_fallback_agent'])
    failed_both = sum(1 for item in data 
                      if not item['succeed_before_fallback_agent'] and not item['succeed_after_fallback_agent'])
    
    return {
        'total': total,
        'without_fallback': without_fallback,
        'with_fallback': with_fallback,
        'improved': improved,
        'regressed': regressed,
        'failed_both': failed_both,
        'without_fallback_pct': (without_fallback / total * 100) if total > 0 else 0,
        'with_fallback_pct': (with_fallback / total * 100) if total > 0 else 0,
        'improved_pct': (improved / total * 100) if total > 0 else 0,
    }


def calculate_type_statistics(data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Calculate statistics broken down by patch type."""
    by_type = defaultdict(list)
    
    for item in data:
        patch_type = item['patch_type']
        by_type[patch_type].append(item)
    
    type_stats = {}
    for patch_type in sorted(by_type.keys()):
        items = by_type[patch_type]
        total = len(items)
        
        without_fallback = sum(1 for item in items if item['succeed_before_fallback_agent'])
        with_fallback = sum(1 for item in items if item['succeed_after_fallback_agent'])
        improved = sum(1 for item in items 
                       if not item['succeed_before_fallback_agent'] and item['succeed_after_fallback_agent'])
        
        type_stats[patch_type] = {
            'total': total,
            'without_fallback': without_fallback,
            'with_fallback': with_fallback,
            'improved': improved,
            'without_fallback_pct': (without_fallback / total * 100) if total > 0 else 0,
            'with_fallback_pct': (with_fallback / total * 100) if total > 0 else 0,
            'improved_pct': (improved / total * 100) if total > 0 else 0,
        }
    
    return type_stats


def print_overall_stats(stats: Dict[str, Any]):
    """Print overall statistics in a formatted way."""
    print("=" * 70)
    print("OVERALL STATISTICS".center(70))
    print("=" * 70)
    print()
    
    print(f"Total patches analyzed:              {stats['total']}")
    print()
    
    print("SUCCESS RATES:")
    print(f"  Succeeded WITHOUT fallback agent:  {stats['without_fallback']:3d}/{stats['total']} ({stats['without_fallback_pct']:5.1f}%)")
    print(f"  Succeeded WITH fallback agent:     {stats['with_fallback']:3d}/{stats['total']} ({stats['with_fallback_pct']:5.1f}%)")
    print()
    
    print("FALLBACK AGENT IMPACT:")
    print(f"  Improved by fallback agent:        {stats['improved']:3d}/{stats['total']} ({stats['improved_pct']:5.1f}%)")
    print(f"  Regressed (broke working patches): {stats['regressed']:3d}/{stats['total']}")
    print(f"  Failed both (before & after):      {stats['failed_both']:3d}/{stats['total']}")
    print()


def print_type_stats(type_stats: Dict[str, Dict[str, Any]]):
    """Print type-wise statistics in a formatted table."""
    print("=" * 100)
    print("TYPE-WISE BREAKDOWN".center(100))
    print("=" * 100)
    print()
    
    print(f"{'Type':<15} {'Total':>8} {'Before':>12} {'After':>12} {'Improved':>12}")
    print(f"{'':15} {'':>8} {'(% rate)':>12} {'(% rate)':>12} {'(% count)':>12}")
    print("-" * 100)
    
    for patch_type in sorted(type_stats.keys()):
        stats = type_stats[patch_type]
        print(f"{patch_type:<15} {stats['total']:>8} "
              f"{stats['without_fallback']:>3}/{stats['total']:<3} ({stats['without_fallback_pct']:>5.1f}%) "
              f"{stats['with_fallback']:>3}/{stats['total']:<3} ({stats['with_fallback_pct']:>5.1f}%) "
              f"{stats['improved']:>3}/{stats['total']:<3} ({stats['improved_pct']:>5.1f}%)")
    
    print()


def generate_json_report(stats: Dict[str, Any], type_stats: Dict[str, Dict[str, Any]]) -> str:
    """Generate a JSON report."""
    report = {
        'overall': {
            'total_patches': stats['total'],
            'succeeded_without_fallback': {
                'count': stats['without_fallback'],
                'percentage': round(stats['without_fallback_pct'], 2)
            },
            'succeeded_with_fallback': {
                'count': stats['with_fallback'],
                'percentage': round(stats['with_fallback_pct'], 2)
            },
            'improved_by_fallback': {
                'count': stats['improved'],
                'percentage': round(stats['improved_pct'], 2)
            },
            'regressed': {
                'count': stats['regressed']
            },
            'failed_both': {
                'count': stats['failed_both']
            }
        },
        'by_type': {}
    }
    
    for patch_type in sorted(type_stats.keys()):
        ts = type_stats[patch_type]
        report['by_type'][patch_type] = {
            'total': ts['total'],
            'succeeded_without_fallback': {
                'count': ts['without_fallback'],
                'percentage': round(ts['without_fallback_pct'], 2)
            },
            'succeeded_with_fallback': {
                'count': ts['with_fallback'],
                'percentage': round(ts['with_fallback_pct'], 2)
            },
            'improved_by_fallback': {
                'count': ts['improved'],
                'percentage': round(ts['improved_pct'], 2)
            }
        }
    
    return json.dumps(report, indent=2)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_fallback_stats.py <fallback_analysis.json> [output_file]")
        print("\nExample:")
        print("  python analyze_fallback_stats.py output/fallback_analysis.json output/stats_report.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Validate input file
    if not Path(input_file).exists():
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)
    
    # Load data
    print(f"Loading data from {input_file}...")
    data = load_analysis_data(input_file)
    
    # Calculate statistics
    stats = calculate_statistics(data)
    type_stats = calculate_type_statistics(data)
    
    # Print console output
    print_overall_stats(stats)
    print_type_stats(type_stats)
    
    # Generate and save JSON report if output file specified
    if output_file:
        json_report = generate_json_report(stats, type_stats)
        with open(output_file, 'w') as f:
            f.write(json_report)
        print(f"JSON report written to: {output_file}")


if __name__ == '__main__':
    main()
