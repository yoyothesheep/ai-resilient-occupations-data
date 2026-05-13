#!/usr/bin/env python3
"""
Calculate A11 (Observed Technical Exposure) scores for occupations.

This script parses the O*NET task table, calculates the weighted coverage
of AI Economic Index (AEI) tasks, and translates that into a 1-5 bucket.

Outputs: data/intermediate/a11_exposure_scores.csv
"""

import csv
from pathlib import Path
from loaders import load_task_table

OUTPUT_FILE = Path("data/intermediate/a11_exposure_scores.csv")

def main():
    print("Loading task table...")
    task_table = load_task_table()
    
    results = []
    
    for onet_code, tasks in task_table.items():
        total_weight = 0.0
        aei_weight = 0.0
        
        for task in tasks:
            weight = float(task.get("task_weight") or 0.0)
            total_weight += weight
            
            if task.get("in_aei") == "True":
                aei_weight += weight
                
        # Calculate weighted coverage percentage
        if total_weight > 0:
            weighted_coverage = (aei_weight / total_weight) * 100
        else:
            weighted_coverage = 0.0
            
        # Map to 1-5 bucket
        if weighted_coverage == 0:
            score = 1
        elif weighted_coverage < 20:
            score = 2
        elif weighted_coverage < 40:
            score = 3
        elif weighted_coverage < 60:
            score = 4
        else:
            score = 5
            
        results.append({
            "onet_code": onet_code,
            "weighted_coverage_pct": round(weighted_coverage, 1),
            "a11_score": score
        })
        
    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["onet_code", "weighted_coverage_pct", "a11_score"])
        writer.writeheader()
        writer.writerows(results)
        
    print(f"✓ Generated A11 scores for {len(results)} occupations: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
