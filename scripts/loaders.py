"""Shared data loaders for the occupation card pipeline.

All path constants and CSV/text loading functions live here.
Every pipeline script that reads scores, tasks, or metrics should
import from this module — never redefine loaders locally.

Functions:
    load_scores()      → dict[onet_code, row]  from ai_resilience_scores.csv
    load_task_table()  → dict[onet_code, list]  from onet_economic_index_task_table.csv
    load_occ_metrics() → dict[onet_code, row]   from onet_economic_index_metrics.csv
    load_a_scores()    → dict[onet_code, {a1..a10}]  parsed from score_log.txt
    to_score(occ)      → int | None  round(final_ranking * 100) → 0-100
    load_text(path)    → str
    get_cluster_codes(cluster_id) → list[str]
"""

import csv
import re

# ── Path constants ────────────────────────────────────────────────────────────

SCORES_CSV       = "data/output/ai_resilience_scores.csv"
TASK_TABLE       = "data/intermediate/onet_economic_index_task_table.csv"
OCC_METRICS      = "data/intermediate/onet_economic_index_metrics.csv"
SCORE_LOG        = "data/output/score_log.txt"
TONE_GUIDE       = "docs/tone_guide_career_pages.md"
CAREER_SPEC      = "docs/career_page_spec.md"
APPROVED_SOURCES = "docs/approved_sources.md"
CLUSTER_ROLES    = "data/career_clusters/cluster_roles.csv"


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_scores() -> dict:
    """Load scores CSV keyed by onet_code (the 'Code' column).

    Returns dict mapping O*NET code → row dict with all CSV columns.
    Used by nearly every pipeline script for occupation metadata, salary,
    growth, job titles, and scoring attributes.
    """
    with open(SCORES_CSV, newline="", encoding="utf-8") as f:
        return {r["Code"]: r for r in csv.DictReader(f)}


def load_task_table() -> dict:
    """Load task table keyed by onet_code → list of task rows.

    Each row has: task_id, task_text, task_weight, freq_score,
    importance_score, in_aei, automation_pct, augmentation_pct,
    task_success_pct, onet_task_count, etc.

    See docs/pipeline.md 'Task table schema' for full column list.
    """
    table: dict[str, list] = {}
    with open(TASK_TABLE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["onet_code"]
            table.setdefault(code, []).append(row)
    return table


def load_occ_metrics() -> dict:
    """Load occupation-level AEI metrics keyed by onet_code.

    Each row has: ai_task_coverage_pct, weighted_automation_pct,
    weighted_augmentation_pct, weighted_task_success_pct, etc.

    See docs/pipeline.md 'Occupation metrics schema' for full column list.
    """
    with open(OCC_METRICS, newline="", encoding="utf-8") as f:
        return {r["onet_code"]: r for r in csv.DictReader(f)}


def load_a_scores(log_path: str = SCORE_LOG) -> dict:
    """Parse score_log.txt to extract A1-A10 attribute scores per occupation.

    Returns dict: onet_code → {a1: int, ..., a10: int}.
    The score log is written by score_occupations.py (Stage 2).
    """
    a_scores: dict[str, dict] = {}
    pattern_occ = re.compile(r"^\s+(.+?)\s+\((\d{2}-\d{4}\.\d{2})\)")
    pattern_attr = re.compile(r"^\s+A(\d+)\s+.+?:\s+(\d+)")
    current_code = None

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            m = pattern_occ.match(line)
            if m:
                current_code = m.group(2)
                a_scores[current_code] = {}
                continue
            if current_code:
                m2 = pattern_attr.match(line)
                if m2:
                    a_scores[current_code][f"a{m2.group(1)}"] = int(m2.group(2))
    return a_scores


def to_score(occ: dict) -> int | None:
    """Convert an occupation row to a 0-100 AI resilience score via final_ranking."""
    val = occ.get("final_ranking")
    return round(float(val) * 100) if val else None


def load_text(path: str) -> str:
    """Read a text file and return its contents as a string."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def get_cluster_codes(cluster_id: str) -> list[str]:
    """Return deduplicated list of O*NET codes for a cluster, preserving order.

    Reads from cluster_roles.csv. Returns empty list if cluster not found.
    """
    codes = []
    with open(CLUSTER_ROLES, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("cluster_id", "").strip() == cluster_id:
                codes.append(row["onet_code"].strip())
    return list(dict.fromkeys(codes))  # deduplicate preserving order
