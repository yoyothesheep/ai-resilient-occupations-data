#!/usr/bin/env python3
"""
Phase 3b: Before/after comparison report for the AEI 2026-06-26 migration.

Compares a pre-migration backup of AEI/A11/score outputs against the current
outputs, and writes docs/AEI_MIGRATION_2026_06_26.md. This is a review gate:
no card or TSX regeneration should happen until this report has been read.

Usage:
    python3 scripts/compare_aei_migration.py <backup_dir>

<backup_dir> must contain: onet_economic_index_metrics.csv,
a11_exposure_scores.csv, ai_resilience_scores.csv (Phase 1 backup).
"""

import sys
import glob
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from loaders import to_score

OUTPUT_DOC = Path("docs/AEI_MIGRATION_2026_06_26.md")

CARDS_DIR = Path("data/output/cards")

PCTILES = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]


def load_pair(backup_dir: Path, filename: str, index_col: str):
    old = pd.read_csv(backup_dir / filename).set_index(index_col)
    new = pd.read_csv(Path("data/intermediate") / filename
                       if (Path("data/intermediate") / filename).exists()
                       else Path("data/output") / filename).set_index(index_col)
    return old, new


def fmt_pct(x):
    return f"{x:.1f}" if pd.notna(x) else "—"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/compare_aei_migration.py <backup_dir>")
        return 1
    backup_dir = Path(sys.argv[1])
    if not backup_dir.exists():
        print(f"✗ Backup dir not found: {backup_dir}")
        return 1

    lines = []
    lines.append("# AEI Migration 2026-06-26 — Before/After Comparison\n")
    lines.append(f"Backup source: `{backup_dir}`\n")

    # ── Load all four pairs ──────────────────────────────────────────────
    old_metrics = pd.read_csv(backup_dir / "onet_economic_index_metrics.csv").set_index("onet_code")
    new_metrics = pd.read_csv("data/intermediate/onet_economic_index_metrics.csv").set_index("onet_code")

    old_a11 = pd.read_csv(backup_dir / "a11_exposure_scores.csv").set_index("onet_code")
    new_a11 = pd.read_csv("data/intermediate/a11_exposure_scores.csv").set_index("onet_code")

    old_scores = pd.read_csv(backup_dir / "ai_resilience_scores.csv").set_index("Code")
    new_scores = pd.read_csv("data/output/ai_resilience_scores.csv").set_index("Code")

    # occupation title lookup (prefer new, fall back to old)
    titles = new_scores["Occupation"].to_dict()
    titles.update({k: v for k, v in old_scores["Occupation"].to_dict().items() if k not in titles})

    # total score (0-100) via to_score(), never reimplemented
    old_scores["total_score"] = old_scores.apply(lambda r: to_score(r.to_dict()), axis=1)
    new_scores["total_score"] = new_scores.apply(lambda r: to_score(r.to_dict()), axis=1)

    # ── (a) Total task coverage — career x task ──────────────────────────
    lines.append("## (a) Total task coverage — career × task\n")

    old_total_in_aei = int(old_metrics["aei_tasks"].sum())
    new_total_in_aei = int(new_metrics["aei_tasks"].sum())
    lines.append(f"- Total `in_aei` task rows: **{old_total_in_aei:,} → {new_total_in_aei:,}** "
                 f"(Δ {new_total_in_aei - old_total_in_aei:+,})\n")

    cov_join = old_metrics[["aei_tasks", "ai_task_coverage_pct"]].join(
        new_metrics[["aei_tasks", "ai_task_coverage_pct"]],
        lsuffix="_old", rsuffix="_new", how="outer"
    )
    cov_join["aei_tasks_old"] = cov_join["aei_tasks_old"].fillna(0)
    cov_join["aei_tasks_new"] = cov_join["aei_tasks_new"].fillna(0)

    n_old_covered = int((cov_join["aei_tasks_old"] > 0).sum())
    n_new_covered = int((cov_join["aei_tasks_new"] > 0).sum())
    lines.append(f"- Occupations with any AEI coverage: **{n_old_covered} → {n_new_covered}** "
                 f"(of {len(cov_join)} with a task table entry)\n")

    lost = cov_join[(cov_join["aei_tasks_old"] > 0) & (cov_join["aei_tasks_new"] == 0)]
    gained = cov_join[(cov_join["aei_tasks_old"] == 0) & (cov_join["aei_tasks_new"] > 0)]
    lines.append(f"- Occupations that **lost all** AEI coverage: **{len(lost)}**\n")
    lines.append(f"- Occupations that **gained** coverage from zero: **{len(gained)}**\n")

    if len(lost):
        lines.append("\n<details><summary>Occupations that lost all coverage</summary>\n\n")
        lines.append("| Code | Occupation |\n|---|---|\n")
        for code in lost.index:
            lines.append(f"| {code} | {titles.get(code, '?')} |\n")
        lines.append("\n</details>\n")

    if len(gained):
        lines.append("\n<details><summary>Occupations that gained coverage from zero</summary>\n\n")
        lines.append("| Code | Occupation |\n|---|---|\n")
        for code in gained.index:
            lines.append(f"| {code} | {titles.get(code, '?')} |\n")
        lines.append("\n</details>\n")

    lines.append(f"\n- Mean `ai_task_coverage_pct`: {cov_join['ai_task_coverage_pct_old'].mean():.1f}% → "
                 f"{cov_join['ai_task_coverage_pct_new'].mean():.1f}%\n")
    lines.append(f"- Median `ai_task_coverage_pct`: {cov_join['ai_task_coverage_pct_old'].median():.1f}% → "
                 f"{cov_join['ai_task_coverage_pct_new'].median():.1f}%\n")

    # ── (b) Distribution of change — A11 and total score ────────────────
    lines.append("\n## (b) Distribution of change — A11 and total score\n")

    a11_join = old_a11[["a11_score"]].join(new_a11[["a11_score"]], lsuffix="_old", rsuffix="_new", how="outer")
    a11_join["delta"] = a11_join["a11_score_new"] - a11_join["a11_score_old"]

    score_join = old_scores[["total_score"]].join(new_scores[["total_score"]], lsuffix="_old", rsuffix="_new", how="outer")
    score_join["delta"] = score_join["total_score_new"] - score_join["total_score_old"]

    for name, join, col in [("A11 (1-5)", a11_join, "a11_score"), ("Total score (0-100)", score_join, "total_score")]:
        d = join["delta"].dropna()
        lines.append(f"\n### {name}\n")
        lines.append(f"- Median before: {join[f'{col}_old'].median():.1f}  |  "
                     f"Median after: {join[f'{col}_new'].median():.1f}  |  "
                     f"Median delta: {d.median():.2f}\n")
        pct_vals = d.quantile(PCTILES)
        lines.append("\n| Percentile | " + " | ".join(f"p{int(p*100)}" for p in PCTILES) + " |\n")
        lines.append("|---|" + "---|" * len(PCTILES) + "\n")
        lines.append("| Δ | " + " | ".join(f"{pct_vals[p]:+.2f}" for p in PCTILES) + " |\n")
        up = int((d > 0).sum())
        down = int((d < 0).sum())
        same = int((d == 0).sum())
        lines.append(f"\n- Moved up: {up} ({up/len(d)*100:.1f}%)  |  "
                     f"Unchanged: {same} ({same/len(d)*100:.1f}%)  |  "
                     f"Moved down: {down} ({down/len(d)*100:.1f}%)\n")

    lines.append("\n### A11 bucket histogram\n\n| Bucket | Old | New |\n|---|---|---|\n")
    old_hist = old_a11["a11_score"].value_counts().sort_index()
    new_hist = new_a11["a11_score"].value_counts().sort_index()
    for b in range(1, 6):
        lines.append(f"| {b} | {int(old_hist.get(b, 0))} | {int(new_hist.get(b, 0))} |\n")

    lines.append("\n### ai_category transition crosstab\n\n")
    cat_join = old_scores[["ai_category"]].join(new_scores[["ai_category"]], lsuffix="_old", rsuffix="_new", how="inner")
    crosstab = pd.crosstab(cat_join["ai_category_old"], cat_join["ai_category_new"])
    lines.append(crosstab.to_markdown() + "\n")

    n_flipped = int((cat_join["ai_category_old"] != cat_join["ai_category_new"]).sum())
    flip_pct = n_flipped / len(cat_join) * 100
    lines.append(f"\n**Category changed: {n_flipped} of {len(cat_join)} ({flip_pct:.1f}%)**\n")
    if flip_pct > 30:
        lines.append("\n⚠️ **>30% of occupations flipped category — re-tune the "
                     "exposure/necessity/elasticity thresholds in `score_occupations.py` "
                     "before regenerating cards.**\n")

    # ── (c) Top 10 movers ────────────────────────────────────────────────
    lines.append("\n## (c) Top 10 movers\n")

    def top10_table(join, delta_col, old_col, new_col, unit=""):
        top = join.reindex(join[delta_col].abs().sort_values(ascending=False).index).head(10)
        out = "\n| Code | Occupation | Old | New | Δ |\n|---|---|---|---|---|\n"
        for code, row in top.iterrows():
            out += (f"| {code} | {titles.get(code, '?')} | "
                    f"{fmt_pct(row[old_col])}{unit} | {fmt_pct(row[new_col])}{unit} | "
                    f"{row[delta_col]:+.1f}{unit} |\n")
        return out

    cov_join["cov_delta"] = cov_join["ai_task_coverage_pct_new"] - cov_join["ai_task_coverage_pct_old"]
    lines.append("\n### Top 10 by task coverage change\n")
    lines.append(top10_table(cov_join, "cov_delta", "ai_task_coverage_pct_old", "ai_task_coverage_pct_new", "%"))

    lines.append("\n### Top 10 by A11 change\n")
    lines.append(top10_table(a11_join, "delta", "a11_score_old", "a11_score_new"))

    lines.append("\n### Top 10 by total score change\n")
    lines.append(top10_table(score_join, "delta", "total_score_old", "total_score_new"))

    # Published career pages
    card_codes = sorted(p.stem for p in CARDS_DIR.glob("*.json"))
    lines.append(f"\n### Published career pages ({len(card_codes)} cards) — all movers\n")
    lines.append("\n| Code | Occupation | Coverage Δ | A11 Δ | Score Δ |\n|---|---|---|---|---|\n")
    for code in card_codes:
        cov_d = cov_join["cov_delta"].get(code, float("nan"))
        a11_d = a11_join["delta"].get(code, float("nan"))
        score_d = score_join["delta"].get(code, float("nan"))
        lines.append(f"| {code} | {titles.get(code, '?')} | {fmt_pct(cov_d)}% | "
                     f"{fmt_pct(a11_d)} | {fmt_pct(score_d)} |\n")

    lines.append("\n## Review gate\n\n"
                 "Decide explicitly before Phase 4 (card/TSX regeneration):\n"
                 "- Is the coverage loss acceptable, or do the A11 bucket cutoffs need "
                 "quantile re-matching to the new distribution?\n"
                 "- If category-flip share above is >30%, re-tune "
                 "`score_occupations.py` thresholds first.\n")

    report = "".join(lines)
    OUTPUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DOC.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n✓ Saved: {OUTPUT_DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
