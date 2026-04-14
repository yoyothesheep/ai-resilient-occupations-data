#!/usr/bin/env python3
"""Orchestrate the full Track B pipeline for a cluster or single career.

Runs stages 4b–9 in order, checking prerequisites and reporting status.
Stage 4 (cluster file creation) must be done manually via the career-clusters
skill before running this script.

Usage:
    # Full cluster pipeline
    python3 scripts/build_cluster.py --cluster marketing

    # Single career (stages 5-9 for one code)
    python3 scripts/build_cluster.py --code 41-3011.00

    # Dry run — show what would run without executing
    python3 scripts/build_cluster.py --cluster marketing --dry-run

    # Skip stages that are already complete
    python3 scripts/build_cluster.py --cluster marketing --skip-existing

    # Force regenerate everything
    python3 scripts/build_cluster.py --cluster marketing --force

    # Start from a specific stage
    python3 scripts/build_cluster.py --cluster marketing --from-stage 7a

    # Use inline mode (no API key)
    python3 scripts/build_cluster.py --cluster marketing --inline
"""

import argparse
import csv
import json
import os
import subprocess
import sys

from loaders import (
    SCORES_CSV, CLUSTER_ROLES, APPROVED_SOURCES,
    get_cluster_codes, load_scores,
)

SITE_DIR = "../ai-resilient-occupations-site"
CARDS_DIR = "data/output/cards"
EMERGING_CSV = "data/emerging_roles/emerging_roles.csv"
EMERGING_TITLES_CSV = "data/emerging_roles/emerging_job_titles.csv"
CAREERS_DIR = os.path.join(SITE_DIR, "src/data/careers")


# ── Prerequisite checks ──────────────────────────────────────────────────────

def check_cluster_exists(cluster_id: str) -> bool:
    """Check that cluster files exist (Stage 4 prerequisite)."""
    codes = get_cluster_codes(cluster_id)
    if not codes:
        print(f"  ✗ No codes found for cluster '{cluster_id}' in cluster_roles.csv")
        print(f"    Fix: run the career-clusters skill first to create cluster files")
        return False
    print(f"  ✓ Cluster '{cluster_id}': {len(codes)} codes")
    return True


def check_card_complete(code: str) -> dict:
    """Check which fields a card has. Returns dict of field → bool."""
    path = os.path.join(CARDS_DIR, f"{code}.json")
    if not os.path.exists(path):
        return {}
    card = json.load(open(path))
    return {
        "title": bool(card.get("title")),
        "risks": bool(card.get("risks", {}).get("body")),
        "opportunities": bool(card.get("opportunities", {}).get("body")),
        "howToAdapt": bool(card.get("howToAdapt", {}).get("alreadyIn")),
        "quotes": len(card.get("howToAdapt", {}).get("quotes", [])) >= 2,
        "taskData": len(card.get("taskData", [])) > 0,
        "sources": len(card.get("sources", [])) > 0,
        "careerCluster": len(card.get("careerCluster", [])) > 0,
        "emergingCareers": len(card.get("emergingCareers", [])) > 0,
    }


def check_emerging_roles(code: str) -> bool:
    """Check if emerging roles exist in the CSV for this code."""
    if not os.path.exists(EMERGING_CSV):
        return False
    with open(EMERGING_CSV, newline="") as f:
        for r in csv.DictReader(f):
            if r["onet_code"] == code:
                return True
    return False


def check_tsx_exists(code: str) -> bool:
    """Check if a TSX career page exists for this code."""
    scores = load_scores()
    occ = scores.get(code, {})
    import re
    simple = occ.get("altpath simple title", "").strip()
    title = simple if simple else occ.get("Occupation", "")
    slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return os.path.exists(os.path.join(CAREERS_DIR, f"{slug}.tsx"))


# ── Stage runners ─────────────────────────────────────────────────────────────

def run_cmd(cmd: list[str], desc: str, dry_run: bool = False) -> bool:
    """Run a command, print status. Returns True on success."""
    cmd_str = " ".join(cmd)
    if dry_run:
        print(f"  [dry-run] {desc}: {cmd_str}")
        return True
    print(f"  → {desc}...")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  ✗ {desc} failed (exit {result.returncode})")
        return False
    return True


def stage_4b(cluster_id: str, inline: bool, dry_run: bool) -> bool:
    """Add industry-specific sources to approved_sources.md."""
    cmd = ["python3", "scripts/add_cluster_sources.py", "--cluster", cluster_id]
    if inline:
        cmd.append("--inline")
    return run_cmd(cmd, "Stage 4b: Add cluster sources to approved_sources.md", dry_run)


def stage_5(cluster_id: str, codes: list[str], inline: bool, dry_run: bool) -> bool:
    """Generate emerging roles."""
    if len(codes) == 1:
        cmd = ["python3", "scripts/generate_emerging_roles.py", "--code", codes[0]]
        if inline:
            cmd.append("--interactive")
    else:
        cmd = ["python3", "scripts/generate_emerging_roles.py", "--cluster", cluster_id]
        if inline:
            cmd.append("--print-prompts")
    return run_cmd(cmd, "Stage 5: Generate emerging roles", dry_run)


def stage_6(cluster_id: str, codes: list[str], inline: bool, dry_run: bool) -> bool:
    """Generate emerging job title aliases."""
    if len(codes) == 1:
        cmd = ["python3", "scripts/generate_emerging_job_titles.py", "--code", codes[0]]
        if inline:
            cmd.append("--interactive")
    else:
        cmd = ["python3", "scripts/generate_emerging_job_titles.py", "--cluster", cluster_id]
        if inline:
            cmd.append("--print-prompts")
    return run_cmd(cmd, "Stage 6: Generate emerging job title aliases", dry_run)


def stage_7a(cluster_id: str, codes: list[str], force: bool, inline: bool,
             dry_run: bool) -> bool:
    """Generate occupation cards."""
    if len(codes) == 1:
        cmd = ["python3", "scripts/generate_next_steps.py", "--code", codes[0]]
    else:
        cmd = ["python3", "scripts/generate_next_steps.py", "--cluster", cluster_id]
    if not inline:
        cmd.append("--api")
    # inline (no flag) = default interactive: prints prompt, reads JSON from stdin
    if force:
        cmd.append("--force")
    return run_cmd(cmd, "Stage 7a: Generate occupation cards", dry_run)


def stage_7b(codes: list[str], inline: bool, skip_existing: bool,
             dry_run: bool) -> bool:
    """Generate adjacent/lateral roles."""
    ok = True
    for code in codes:
        cmd = ["python3", "scripts/adjacent_roles.py", "--code", code]
        if inline:
            cmd.append("--interactive")
        if skip_existing:
            cmd.append("--skip-existing")
        if not run_cmd(cmd, f"Stage 7b: Adjacent roles for {code}", dry_run):
            ok = False
    return ok


def stage_7c(cluster_id: str, codes: list[str], dry_run: bool) -> bool:
    """Merge emerging roles into cards."""
    if len(codes) == 1:
        cmd = ["python3", "scripts/generate_emerging_roles.py", "--code", codes[0]]
    else:
        cmd = ["python3", "scripts/generate_emerging_roles.py", "--cluster", cluster_id]
    return run_cmd(cmd, "Stage 7c: Merge emerging roles into cards", dry_run)


def stage_8(cluster_id: str, dry_run: bool) -> bool:
    """Generate career + industry pages in site repo."""
    ok = run_cmd(
        ["python3", "scripts/generate_career_pages.py", "--cluster", cluster_id, "--force"],
        "Stage 8a: Generate career pages",
        dry_run,
    )
    ok2 = run_cmd(
        ["python3", "scripts/generate_industry_page.py", "--cluster", cluster_id, "--force"],
        "Stage 8b: Generate industry page",
        dry_run,
    )
    return ok and ok2


def stage_9(dry_run: bool) -> bool:
    """Run data integrity tests."""
    return run_cmd(
        ["python3", "-m", "pytest", "scripts/test_data_integrity.py", "-q",
         "-k", "not url_reachable and not network"],
        "Stage 9: Data integrity checks",
        dry_run,
    )


# ── Status report ─────────────────────────────────────────────────────────────

def print_status(cluster_id: str, codes: list[str]):
    """Print a status report for all codes in the cluster."""
    scores = load_scores()
    print(f"\n{'='*70}")
    print(f"Cluster '{cluster_id}' — {len(codes)} codes")
    print(f"{'='*70}")
    print(f"{'Code':<14} {'Title':<30} {'Card':<6} {'R/O':<4} {'Adpt':<5} {'Qts':<4} {'Adj':<4} {'Emrg':<5} {'TSX':<4}")
    print("-" * 70)

    incomplete = []
    for code in codes:
        occ = scores.get(code, {})
        title = (occ.get("altpath simple title") or occ.get("Occupation", "?"))[:28]
        status = check_card_complete(code)

        if not status:
            print(f"{code:<14} {title:<30} {'—':^6} {'—':^4} {'—':^5} {'—':^4} {'—':^4} {'—':^5} {'—':^4}")
            incomplete.append((code, "no card"))
            continue

        card = "✓" if status.get("title") else "✗"
        ro = "✓" if status.get("risks") and status.get("opportunities") else "✗"
        adapt = "✓" if status.get("howToAdapt") else "✗"
        qts = "✓" if status.get("quotes") else "✗"
        adj = "✓" if status.get("careerCluster") else "✗"
        emrg = "✓" if status.get("emergingCareers") else "✗"
        tsx = "✓" if check_tsx_exists(code) else "✗"

        print(f"{code:<14} {title:<30} {card:^6} {ro:^4} {adapt:^5} {qts:^4} {adj:^4} {emrg:^5} {tsx:^4}")

        missing = [k for k, v in status.items() if not v]
        if missing:
            incomplete.append((code, ", ".join(missing)))

    if incomplete:
        print(f"\n{len(incomplete)} codes need work:")
        for code, reason in incomplete:
            print(f"  {code}: {reason}")
    else:
        print(f"\n✓ All {len(codes)} codes complete")

    return incomplete


# ── Stages list ───────────────────────────────────────────────────────────────

STAGES = ["4b", "5", "6", "7a", "7b", "7c", "8", "9"]


def stage_index(stage: str) -> int:
    return STAGES.index(stage)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run Track B pipeline for a cluster or single career"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cluster", help="Cluster ID (e.g. marketing)")
    group.add_argument("--code", help="Single O*NET code")
    group.add_argument("--status", metavar="CLUSTER",
                       help="Print status report only, no execution")

    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without executing")
    parser.add_argument("--force", action="store_true",
                        help="Force regenerate all stages")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip already-complete stages where possible")
    parser.add_argument("--inline", action="store_true",
                        help="Use inline/print-prompt mode (no API key needed)")
    parser.add_argument("--from-stage", choices=STAGES,
                        help="Start from this stage (skip earlier stages)")
    args = parser.parse_args()

    # Status-only mode
    if args.status:
        codes = get_cluster_codes(args.status)
        if not codes:
            print(f"No codes found for cluster '{args.status}'")
            sys.exit(1)
        print_status(args.status, codes)
        return

    # Resolve cluster and codes
    if args.code:
        # Find which cluster this code belongs to
        cluster_id = None
        with open(CLUSTER_ROLES, newline="") as f:
            for r in csv.DictReader(f):
                if r["onet_code"] == args.code:
                    cluster_id = r["cluster_id"]
                    break
        if not cluster_id:
            print(f"Code {args.code} not found in any cluster")
            sys.exit(1)
        codes = [args.code]
        print(f"Single code mode: {args.code} (cluster: {cluster_id})")
    else:
        cluster_id = args.cluster
        if not check_cluster_exists(cluster_id):
            sys.exit(1)
        codes = get_cluster_codes(cluster_id)

    # Print current status
    incomplete = print_status(cluster_id, codes)

    if args.dry_run:
        print("\n[DRY RUN MODE — showing what would execute]\n")

    # Determine starting stage
    start = stage_index(args.from_stage) if args.from_stage else 0

    print(f"\n{'='*70}")
    print(f"Running stages {STAGES[start]}–9")
    print(f"{'='*70}\n")

    # Run stages in order
    ok = True

    if start <= stage_index("4b"):
        ok = stage_4b(cluster_id, args.inline, args.dry_run) and ok

    if start <= stage_index("5") and ok:
        ok = stage_5(cluster_id, codes, args.inline, args.dry_run) and ok

    if start <= stage_index("6") and ok:
        ok = stage_6(cluster_id, codes, args.inline, args.dry_run) and ok

    if start <= stage_index("7a") and ok:
        ok = stage_7a(cluster_id, codes, args.force, args.inline, args.dry_run) and ok

    if start <= stage_index("7b") and ok:
        ok = stage_7b(codes, args.inline, args.skip_existing, args.dry_run) and ok

    if start <= stage_index("7c") and ok:
        ok = stage_7c(cluster_id, codes, args.dry_run) and ok

    if start <= stage_index("8") and ok:
        ok = stage_8(cluster_id, args.dry_run) and ok

    if start <= stage_index("9") and ok:
        ok = stage_9(args.dry_run) and ok

    # Final status
    print(f"\n{'='*70}")
    if ok:
        print("✓ Pipeline complete")
    else:
        print("✗ Pipeline finished with errors — check output above")
    print_status(cluster_id, codes)


if __name__ == "__main__":
    main()
