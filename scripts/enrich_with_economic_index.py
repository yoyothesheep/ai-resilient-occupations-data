#!/usr/bin/env python3
"""
Phase 4: Join occupation-level AEI metrics to the main enriched dataset.

Left join on onet_code — all 1,016 occupations retained.
Occupations with no AEI coverage get NaN for AEI columns.

Input:
- data/intermediate/All_Occupations_ONET_enriched.csv   (1,016 occupations)
- data/intermediate/onet_economic_index_metrics.csv      (923 occupations)

Output:
- data/intermediate/All_Occupations_ONET_enriched_aei.csv
"""

import pandas as pd
from pathlib import Path
import sys

ENRICHED_FILE = Path("data/intermediate/All_Occupations_ONET_enriched.csv")
METRICS_FILE = Path("data/intermediate/onet_economic_index_metrics.csv")
OUTPUT_FILE = Path("data/intermediate/All_Occupations_ONET_enriched_aei.csv")

AEI_COLS = [
    'total_tasks', 'aei_tasks', 'ai_task_coverage_pct',
    'weighted_automation_pct', 'weighted_augmentation_pct',
    'weighted_ai_autonomy_mean', 'weighted_speedup_factor'
]


def main():
    print("=" * 100)
    print("PHASE 4: JOIN AEI METRICS TO ENRICHED DATASET")
    print("=" * 100)

    # Load inputs
    enriched = pd.read_csv(ENRICHED_FILE)
    metrics = pd.read_csv(METRICS_FILE)

    print(f"\nEnriched dataset:  {len(enriched):,} occupations, {len(enriched.columns)} columns")
    print(f"AEI metrics:       {len(metrics):,} occupations, {len(metrics.columns)} columns")

    # Rename Code → onet_code for join
    if 'Code' in enriched.columns and 'onet_code' not in enriched.columns:
        enriched = enriched.rename(columns={'Code': 'onet_code'})

    # Drop old AEI columns if present (from a previous partial integration)
    old_aei_cols = [c for c in enriched.columns if c in AEI_COLS or c in [
        'num_tasks_measured', 'ai_task_coverage_pct', 'ai_task_success_pct',
        'weighted_task_success_pct',
        'ai_autonomy_mean', 'automation_pct', 'augmentation_pct',
        'speedup_factor', 'work_use_pct', 'ai_education_gap'
    ]]
    if old_aei_cols:
        print(f"\nDropping {len(old_aei_cols)} old AEI columns: {old_aei_cols}")
        enriched = enriched.drop(columns=old_aei_cols)

    # Left join
    result = enriched.merge(metrics[['onet_code'] + AEI_COLS], on='onet_code', how='left')

    # Audit
    matched = result['ai_task_coverage_pct'].notna().sum()
    unmatched = result['ai_task_coverage_pct'].isna().sum()
    print(f"\nJoin results:")
    print(f"  Matched (have AEI data):  {matched:,}")
    print(f"  Unmatched (NaN):          {unmatched:,}")
    assert len(result) == len(enriched), "Row count changed — join error!"
    print(f"  Total rows:               {len(result):,}  ✓ (no rows dropped)")

    # Sample spot-check
    spot = [
        ('15-1254.00', 'Web Developers'),
        ('29-1141.00', 'Registered Nurses'),
        ('15-2051.00', 'Data Scientists'),
        ('47-2061.00', 'Construction Laborers'),
    ]
    print("\nSpot-check:")
    for code, label in spot:
        row = result[result['onet_code'] == code]
        if len(row):
            r = row.iloc[0]
            cov = f"{r['ai_task_coverage_pct']:.1f}%" if pd.notna(r['ai_task_coverage_pct']) else 'NaN'
            auto = f"{r['weighted_automation_pct']:.0f}%" if pd.notna(r['weighted_automation_pct']) else 'NaN'
            aug  = f"{r['weighted_augmentation_pct']:.0f}%" if pd.notna(r['weighted_augmentation_pct']) else 'NaN'
            spd  = f"{r['weighted_speedup_factor']:.1f}x" if pd.notna(r['weighted_speedup_factor']) else 'NaN'
            print(f"  {label} ({code}): coverage={cov}  auto={auto}  aug={aug}  speedup={spd}")
        else:
            print(f"  {label} ({code}): NOT FOUND")

    # Show unmatched occupations
    if unmatched > 0:
        unmatched_list = result[result['ai_task_coverage_pct'].isna()][['onet_code', 'Occupation']].head(10)
        print(f"\nFirst {min(10, unmatched)} unmatched occupations (no AEI data):")
        for _, row in unmatched_list.iterrows():
            print(f"  {row['onet_code']}  {row['Occupation']}")

    # Save
    result.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✓ Saved: {OUTPUT_FILE}")
    print(f"  Columns: {len(result.columns)} ({len(enriched.columns)} original + {len(AEI_COLS)} AEI)")

    print("\nPhase 4 complete. Next: Phase 5 (custom next steps).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
