#!/usr/bin/env python3
"""
Phase 3a: Build full task table with importance weights + AEI coverage.

Joins the complete O*NET task universe (v30.2, 18,796 tasks) with:
- Task Ratings (freq_score, importance_score → task_weight)
- AEI mapped data (in_aei flag + collaboration/timing metrics), joined on
  (onet_code, task_id) — an exact join, since AEI release 2026-06-26
  publishes the O*NET Task ID directly. See map_economic_index.py.

task_weight = freq_score × importance_score for rated tasks.
For 29 occupations missing Task Ratings data (new in v30.2), falls back
to task_weight = 1.0 (unweighted). weight_source flags which was used.

Outputs:
- data/intermediate/onet_economic_index_task_table.csv   (one row per onet_code × task)
- data/intermediate/onet_economic_index_metrics.csv      (one row per occupation)
"""

import pandas as pd
from pathlib import Path
import sys

TASK_STATEMENTS_FILE = Path("data/input/onet_db/Task Statements.xlsx")
TASK_RATINGS_FILE = Path("data/input/onet_db/Task Ratings.xlsx")
AEI_TASKS_MAPPED_FILE = Path("data/intermediate/economic_index_tasks_mapped.csv")
OUTPUT_DIR = Path("data/intermediate")


def compute_freq_score(ratings_df):
    """
    Compute freq_score per (onet_code, task_id) from FT scale.

    FT has categories 1-7 representing frequency buckets. Each row has a
    Data Value = % of respondents who chose that category. freq_score is
    the weighted average: sum(category x pct / 100).
    """
    ft = ratings_df[ratings_df['Scale ID'] == 'FT'].copy()
    ft['weighted'] = ft['Category'] * ft['Data Value'] / 100.0
    return (
        ft.groupby(['O*NET-SOC Code', 'Task ID'])['weighted']
        .sum()
        .reset_index()
        .rename(columns={'O*NET-SOC Code': 'onet_code', 'Task ID': 'task_id', 'weighted': 'freq_score'})
    )


def compute_importance_score(ratings_df):
    """
    Compute importance_score per (onet_code, task_id) from IM scale.

    IM scale Data Value is already a mean rating on 1-5 scale.
    """
    im = ratings_df[ratings_df['Scale ID'] == 'IM'].copy()
    return (
        im.groupby(['O*NET-SOC Code', 'Task ID'])['Data Value']
        .mean()
        .reset_index()
        .rename(columns={'O*NET-SOC Code': 'onet_code', 'Task ID': 'task_id', 'Data Value': 'importance_score'})
    )


def weighted_mean(group, value_col, weight_col='task_weight'):
    w = group[weight_col]
    v = group[value_col]
    valid = v.notna() & (w > 0)
    if valid.sum() == 0:
        return float('nan')
    return (v[valid] * w[valid]).sum() / w[valid].sum()


def main():
    print("=" * 100)
    print("PHASE 3a: BUILD TASK TABLE WITH IMPORTANCE WEIGHTS + AEI COVERAGE")
    print("=" * 100)

    # --- Load inputs ---
    print("\nLoading inputs...")
    statements = pd.read_excel(TASK_STATEMENTS_FILE, usecols=['O*NET-SOC Code', 'Task ID', 'Task'])
    statements.columns = ['onet_code', 'task_id', 'task_text']
    statements['task_id'] = statements['task_id'].astype('Int64').astype('string')
    print(f"  Task statements: {len(statements):,} rows, {statements['onet_code'].nunique():,} occupations")

    ratings = pd.read_excel(TASK_RATINGS_FILE)
    print(f"  Task ratings: {len(ratings):,} rows, {ratings['O*NET-SOC Code'].nunique():,} occupations")

    aei_mapped = pd.read_csv(AEI_TASKS_MAPPED_FILE, dtype={'task_id': 'string'})
    aei_mapped = aei_mapped[aei_mapped['onet_code'].notna() & (aei_mapped['match_type'] != 'unmatched')].copy()
    print(f"  AEI tasks (mapped): {len(aei_mapped):,} rows, {aei_mapped['onet_code'].nunique():,} occupations")

    # --- Compute weights ---
    print("\nComputing task weights...")
    freq = compute_freq_score(ratings)
    importance = compute_importance_score(ratings)
    freq['task_id'] = freq['task_id'].astype('Int64').astype('string')
    importance['task_id'] = importance['task_id'].astype('Int64').astype('string')

    # --- Build base task table ---
    print("\nBuilding task table...")
    task_table = statements.copy()
    task_table = task_table.merge(freq, on=['onet_code', 'task_id'], how='left')
    task_table = task_table.merge(importance, on=['onet_code', 'task_id'], how='left')

    # task_weight: rated where available, mean fallback otherwise
    # For occupations missing some or all Task Ratings data, fall back to the
    # mean rated task_weight for that occupation. If no rated tasks exist for
    # the occupation at all, fall back to the global mean rated task_weight.
    rated_mask = task_table['freq_score'].notna() & task_table['importance_score'].notna()
    task_table['task_weight'] = task_table['freq_score'] * task_table['importance_score']
    task_table['weight_source'] = 'rated'
    task_table.loc[~rated_mask, 'weight_source'] = 'mean_fallback'

    # Compute per-occupation mean of rated tasks, fall back to global mean
    occ_mean = (
        task_table[rated_mask]
        .groupby('onet_code')['task_weight']
        .mean()
        .rename('occ_mean_weight')
    )
    global_mean = task_table.loc[rated_mask, 'task_weight'].mean()
    task_table = task_table.join(occ_mean, on='onet_code')
    fallback_weight = task_table['occ_mean_weight'].fillna(global_mean)
    task_table.loc[~rated_mask, 'task_weight'] = fallback_weight[~rated_mask]
    task_table = task_table.drop(columns='occ_mean_weight')

    n_fallback = (~rated_mask).sum()
    n_fallback_occs = task_table.loc[~rated_mask, 'onet_code'].nunique()
    print(f"  Total rows: {len(task_table):,}")
    print(f"  Rated rows: {rated_mask.sum():,}")
    print(f"  Mean fallback: {n_fallback:,} rows across {n_fallback_occs} occupations (global mean: {global_mean:.2f})")

    # --- Join AEI metrics ---
    print("\nJoining AEI metrics...")
    aei_metrics = aei_mapped[[
        'onet_code', 'task_id', 'match_type', 'onet_task_pct',
        'automation_pct', 'augmentation_pct', 'ai_autonomy_mean', 'speedup_factor'
    ]].drop_duplicates(subset=['onet_code', 'task_id'])

    task_table = task_table.merge(aei_metrics, on=['onet_code', 'task_id'], how='left')
    task_table['in_aei'] = task_table['match_type'].notna().astype(bool)
    assert task_table['in_aei'].dtype == bool

    aei_count = task_table['in_aei'].sum()
    print(f"  Tasks in AEI: {aei_count:,} of {len(task_table):,} ({aei_count/len(task_table)*100:.1f}%)")

    # --- Save task table ---
    col_order = [
        'onet_code', 'task_id', 'task_text',
        'freq_score', 'importance_score', 'task_weight', 'weight_source',
        'in_aei', 'match_type',
        'onet_task_pct',
        'automation_pct', 'augmentation_pct',
        'ai_autonomy_mean', 'speedup_factor'
    ]
    task_table = task_table[col_order]
    task_table_path = OUTPUT_DIR / "onet_economic_index_task_table.csv"
    task_table.to_csv(task_table_path, index=False)
    print(f"\n✓ Saved task table: {task_table_path}")

    # --- Build occupation-level metrics ---
    print("\nBuilding occupation-level metrics...")

    coverage = (
        task_table.groupby('onet_code')
        .agg(total_tasks=('task_id', 'count'), aei_tasks=('in_aei', 'sum'))
        .reset_index()
    )
    coverage['ai_task_coverage_pct'] = (coverage['aei_tasks'] / coverage['total_tasks'] * 100).round(1)

    aei_only = task_table[task_table['in_aei']].copy()
    rollup_rows = []
    for onet_code, group in aei_only.groupby('onet_code'):
        rollup_rows.append({
            'onet_code': onet_code,
            'weighted_automation_pct': weighted_mean(group, 'automation_pct'),
            'weighted_augmentation_pct': weighted_mean(group, 'augmentation_pct'),
            'weighted_ai_autonomy_mean': weighted_mean(group, 'ai_autonomy_mean'),
            'weighted_speedup_factor': weighted_mean(group, 'speedup_factor'),
        })
    rollups = pd.DataFrame(rollup_rows)
    metrics = coverage.merge(rollups, on='onet_code', how='left')

    metrics_path = OUTPUT_DIR / "onet_economic_index_metrics.csv"
    metrics.to_csv(metrics_path, index=False)
    print(f"✓ Saved occupation metrics: {metrics_path}")
    print(f"  Occupations: {len(metrics):,}")

    # --- Audit ---
    print("\n--- AUDIT ---")
    print(f"Task table rows:         {len(task_table):,}")
    print(f"Occupations:             {task_table['onet_code'].nunique():,}")
    print(f"weight_source=rated:        {(task_table['weight_source']=='rated').sum():,}")
    print(f"weight_source=mean_fallback:{(task_table['weight_source']=='mean_fallback').sum():,}")
    print(f"task_weight null:        {task_table['task_weight'].isna().sum():,}  (should be 0)")
    print(f"in_aei=True:             {task_table['in_aei'].sum():,}")
    assert task_table['task_weight'].isna().sum() == 0, "Unexpected null task_weights!"
    assert (metrics['ai_task_coverage_pct'] <= 100).all(), "Coverage > 100% found!"
    print(f"Coverage ≤ 100%:         ✓")

    print("\nCoverage spot-check:")
    spot = [
        ('15-1254.00', 'Web Developers'),
        ('29-1141.00', 'Registered Nurses'),
        ('47-2061.00', 'Construction Laborers'),
        ('15-2051.00', 'Data Scientists'),
        ('29-1211.00', 'Anesthesiologists'),
    ]
    for code, label in spot:
        row = metrics[metrics['onet_code'] == code]
        if len(row):
            r = row.iloc[0]
            ws = task_table[task_table['onet_code']==code]['weight_source'].iloc[0]
            auto = f"{r['weighted_automation_pct']:.0f}%" if pd.notna(r['weighted_automation_pct']) else 'n/a'
            aug  = f"{r['weighted_augmentation_pct']:.0f}%" if pd.notna(r['weighted_augmentation_pct']) else 'n/a'
            print(f"  {label} ({code}) [{ws}]: "
                  f"{int(r['aei_tasks'])}/{int(r['total_tasks'])} tasks={r['ai_task_coverage_pct']:.1f}%  "
                  f"auto={auto}  aug={aug}")
        else:
            print(f"  {label} ({code}): NOT FOUND")

    print("\nTop 5 tasks by task_weight (rated only):")
    rated_top = task_table[task_table['weight_source']=='rated'].nlargest(5, 'task_weight')
    for _, row in rated_top.iterrows():
        print(f"  [{row['task_weight']:.1f}]  {row['task_text'][:75]}")

    print("\nPhase 3a complete. Next: Phase 3b (occupation-level rollups).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
