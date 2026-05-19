#!/usr/bin/env python3
"""
Analyze patch comparison data and generate statistics.
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
import statistics


def main():
    comparison_file = Path('output/patch_comparison.json')
    
    if not comparison_file.exists():
        print(f"Error: {comparison_file} not found")
        return
    
    with open(comparison_file, 'r') as f:
        comparisons = json.load(f)
    
    print(f"\n{'='*80}")
    print("PATCH COMPARISON ANALYSIS")
    print(f"{'='*80}\n")
    
    total_patches = len(comparisons)
    print(f"Total patches analyzed: {total_patches}")
    
    # Overall statistics
    dev_hunks = [c['prod_hunks_count_dev'] for c in comparisons]
    gen_hunks = [c['prod_hunks_count_gen'] for c in comparisons]
    aux_hunks = [c['developer_aux_hunks_from_target'] for c in comparisons]
    
    print(f"\nDeveloper Patch (target.patch) - Production hunks:")
    print(f"  Mean: {statistics.mean(dev_hunks):.2f}")
    print(f"  Median: {statistics.median(dev_hunks):.1f}")
    print(f"  Min: {min(dev_hunks)}, Max: {max(dev_hunks)}")
    print(f"  Total: {sum(dev_hunks)}")
    
    print(f"\nGenerated Patch - Production hunks:")
    print(f"  Mean: {statistics.mean(gen_hunks):.2f}")
    print(f"  Median: {statistics.median(gen_hunks):.1f}")
    print(f"  Min: {min(gen_hunks)}, Max: {max(gen_hunks)}")
    print(f"  Total: {sum(gen_hunks)}")
    
    print(f"\nDeveloper Auxiliary hunks (from target):")
    print(f"  Mean: {statistics.mean(aux_hunks):.2f}")
    print(f"  Median: {statistics.median(aux_hunks):.1f}")
    print(f"  Min: {min(aux_hunks)}, Max: {max(aux_hunks)}")
    print(f"  Total: {sum(aux_hunks)}")
    
    # Calculate difference
    differences = [gen - dev for gen, dev in zip(gen_hunks, dev_hunks)]
    diff_summary = Counter(d for d in differences)
    
    print(f"\nPatch differences (generated - developer):")
    same_count = len([d for d in differences if d == 0])
    fewer_count = len([d for d in differences if d < 0])
    more_count = len([d for d in differences if d > 0])
    
    print(f"  Same hunks: {same_count} ({100*same_count/total_patches:.1f}%)")
    print(f"  Fewer hunks in generated: {fewer_count} ({100*fewer_count/total_patches:.1f}%)")
    print(f"  More hunks in generated: {more_count} ({100*more_count/total_patches:.1f}%)")
    print(f"  Mean difference: {statistics.mean(differences):.2f}")
    
    # By patch type
    print(f"\n{'='*80}")
    print("BY PATCH TYPE")
    print(f"{'='*80}\n")
    
    by_type = defaultdict(list)
    for c in comparisons:
        by_type[c['patch_type']].append(c)
    
    for patch_type in sorted(by_type.keys()):
        patches = by_type[patch_type]
        print(f"{patch_type} ({len(patches)} patches):")
        
        dev_hunks_type = [p['prod_hunks_count_dev'] for p in patches]
        gen_hunks_type = [p['prod_hunks_count_gen'] for p in patches]
        diffs_type = [g - d for g, d in zip(gen_hunks_type, dev_hunks_type)]
        
        same = len([d for d in diffs_type if d == 0])
        fewer = len([d for d in diffs_type if d < 0])
        more = len([d for d in diffs_type if d > 0])
        
        print(f"  Dev hunks: avg {statistics.mean(dev_hunks_type):.2f}, total {sum(dev_hunks_type)}")
        print(f"  Gen hunks: avg {statistics.mean(gen_hunks_type):.2f}, total {sum(gen_hunks_type)}")
        print(f"  Match: {same} | Fewer: {fewer} | More: {more}")
        print()
    
    # By repo  
    print(f"{'='*80}")
    print("BY REPOSITORY")
    print(f"{'='*80}\n")
    
    by_repo = defaultdict(list)
    for c in comparisons:
        by_repo[c['repo']].append(c)
    
    repo_stats = []
    for repo in sorted(by_repo.keys()):
        patches = by_repo[repo]
        dev_hunks_repo = [p['prod_hunks_count_dev'] for p in patches]
        gen_hunks_repo = [p['prod_hunks_count_gen'] for p in patches]
        
        same = len([g - d for g, d in zip(gen_hunks_repo, dev_hunks_repo) if g == d])
        repo_stats.append((repo, len(patches), sum(dev_hunks_repo), sum(gen_hunks_repo), same))
    
    print(f"{'Repo':<25} {'Patches':>8} {'Dev':>8} {'Gen':>8} {'Match':>8}")
    print(f"{'-'*60}")
    for repo, count, dev_sum, gen_sum, same in repo_stats:
        print(f"{repo:<25} {count:>8} {dev_sum:>8} {gen_sum:>8} {same:>8}")
    
    print(f"\n{'='*80}")
    print(f"Output saved to: {comparison_file}")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
