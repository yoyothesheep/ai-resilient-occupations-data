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
    is_true(v)         → bool  tolerant parser for CSV-round-tripped boolean flags
    load_text(path)    → str
    get_cluster_codes(cluster_id) → list[str]

Constants:
    MIN_PCT_SIGNAL     → float  minimum AEI onet_task_pct for a task to carry
                          usage signal (bars, badges, model prompts). Replaces
                          the pre-2026-06-26 `onet_task_count >= 100` gate —
                          onet_task_pct == onet_task_count / 10,000 exactly in
                          the prior release, so 0.01 is a bit-for-bit continuation.
"""

import csv
import math
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

MIN_PCT_SIGNAL = 0.01  # onet_task_pct threshold; see module docstring


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
    onet_task_pct, ai_autonomy_mean, speedup_factor, etc.

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
    weighted_augmentation_pct, weighted_ai_autonomy_mean,
    weighted_speedup_factor, etc.

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
    """Convert an occupation row to a 0-100 AI resilience score via final_ranking.

    Uses round-half-up (matches JS Math.round on the site), not Python's
    round() which is round-half-to-even. final_ranking is always >= 0.
    """
    val = occ.get("final_ranking")
    return int(math.floor(float(val) * 100 + 0.5)) if val else None


def is_true(v) -> bool:
    """Tolerant boolean parser for flags that round-trip through CSV as strings.

    Accepts True, "True", "true", 1, "1". Everything else (None, "", "False",
    pandas <NA>, nullable-boolean NaN) is False. Use this instead of an exact
    string compare against "True" — a merge that produces a pandas nullable
    boolean dtype writes "1.0"/"<NA>" to CSV, which an exact compare misses
    silently (see docs/pipeline.md AEI migration notes).
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("true", "1", "1.0")


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
