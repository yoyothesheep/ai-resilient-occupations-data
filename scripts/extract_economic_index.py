#!/usr/bin/env python3
"""
Phase 2a: Extract O*NET task data + collaboration/timing metrics from EconomicIndex (global level).

Release 2026-06-26 schema: date_start,date_end,geo_id,geo_level,category_name,
hierarchy_level,metric_id,value,node_name,node_external_id.

`node_external_id` at hierarchy_level 0 is the O*NET numeric Task ID, enabling
an exact join to Task Statements.xlsx (see map_economic_index.py) instead of
the old fuzzy text match.

Two monthly periods are published (2026-04-01, 2026-05-01); we use May only.

No task_success or conversation-count metric exists in this release — dropped.

Outputs:
- data/intermediate/economic_index_tasks_raw.csv
  One row per O*NET task (by task_id) with usage pct and collaboration/timing metrics.
"""

import pandas as pd
from pathlib import Path
import sys

INPUT_FILE = Path("data/input/anthropic/aei_claude_ai_2026-06-26.csv")
OUTPUT_DIR = Path("data/intermediate")
PERIOD = "2026-05-01"

METRIC_RENAME = {
    "pct": "onet_task_pct",
    "collaboration_bucket_automation_pct": "automation_pct",
    "collaboration_bucket_augmentation_pct": "augmentation_pct",
    "ai_autonomy_mean": "ai_autonomy_mean",
    "human_only_time_mean": "human_only_time",
    "human_with_ai_time_mean": "human_with_ai_time",
}


def main():
    print("=" * 100)
    print("PHASE 2a: EXTRACT ECONOMICINDEX TASKS (GLOBAL, ONET, TASK-LEVEL)")
    print("=" * 100)

    print("\nLoading raw data...")
    df = pd.read_csv(
        INPUT_FILE,
        usecols=["date_start", "geo_level", "category_name", "hierarchy_level",
                 "metric_id", "value", "node_name", "node_external_id"],
        dtype={"node_external_id": "string"},
    )
    print(f"  Total rows: {len(df):,}")

    base = df[
        (df["geo_level"] == "global") &
        (df["category_name"] == "onet") &
        (df["hierarchy_level"] == 0) &
        (df["date_start"] == PERIOD) &
        (df["metric_id"].isin(METRIC_RENAME.keys()))
    ].copy()

    assert len(base) > 0, (
        f"Filter produced zero rows — check geo_level/category_name/hierarchy_level/"
        f"date_start values against the actual file (PERIOD={PERIOD!r})"
    )
    print(f"  Filtered to global onet task-level rows for {PERIOD}: {len(base):,}")

    wide = base.pivot_table(
        index=["node_external_id", "node_name"],
        columns="metric_id",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide = wide.rename(columns={"node_external_id": "task_id", "node_name": "task_text"})
    wide = wide.rename(columns=METRIC_RENAME)

    # Exclude non-task rows and rows with no task id
    wide = wide[wide["task_id"].notna()]
    wide = wide[~wide["task_text"].isin(["none", "not_classified"])].copy()

    assert wide["task_id"].is_unique, "Duplicate task_id in extracted AEI data"

    # Unit correction: human_only_time in hours, human_with_ai_time in minutes
    if "human_only_time" in wide.columns and "human_with_ai_time" in wide.columns:
        wide["speedup_factor"] = (
            wide["human_only_time"] * 60
        ) / wide["human_with_ai_time"].replace(0, float("nan"))
    else:
        wide["speedup_factor"] = float("nan")

    cols = ["task_id", "task_text", "onet_task_pct", "automation_pct",
            "augmentation_pct", "ai_autonomy_mean", "speedup_factor"]
    for c in cols:
        if c not in wide.columns:
            wide[c] = float("nan")
    result = wide[cols].copy()

    pct_sum = result["onet_task_pct"].sum()
    combined = (result["automation_pct"].fillna(0) + result["augmentation_pct"].fillna(0))
    over_100 = (combined > 100.01).sum()
    assert over_100 == 0, f"{over_100} tasks have automation_pct + augmentation_pct > 100"

    print(f"\nFinal dataset: {len(result):,} tasks")
    print(f"  onet_task_pct sum:        {pct_sum:.2f}")
    print(f"  With collaboration data:  {result['automation_pct'].notna().sum():,}")
    print(f"  With ai_autonomy data:    {result['ai_autonomy_mean'].notna().sum():,}")
    print(f"  With speedup_factor data: {result['speedup_factor'].notna().sum():,}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "economic_index_tasks_raw.csv"
    result.to_csv(output_file, index=False)
    print(f"\n✓ Saved: {output_file}")
    print(f"  Columns: {list(result.columns)}")

    print("\nTop 10 tasks by usage:")
    for _, row in result.nlargest(10, "onet_task_pct").iterrows():
        if pd.notna(row["automation_pct"]):
            print(f"  [{row['onet_task_pct']:>6.2f}%]  auto={row['automation_pct']:.0f}%  "
                  f"aug={row['augmentation_pct']:.0f}%  {row['task_text'][:60]}")
        else:
            print(f"  [{row['onet_task_pct']:>6.2f}%]  (no collab data)  {row['task_text'][:60]}")

    print("\nPhase 2a complete. Next: Phase 2b (map tasks to O*NET occupations).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
