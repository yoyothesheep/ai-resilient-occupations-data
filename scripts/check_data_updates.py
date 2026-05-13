#!/usr/bin/env python3
"""
Check all pipeline data sources for available updates.

Sources checked:
  - O*NET Database        (download_onet.py)
  - Anthropic Economic Index  (HuggingFace)
  - BLS OES Wages         (bls.gov)
  - BLS Employment Projections (bls.gov)

Usage:
    python3 scripts/check_data_updates.py
"""

import re
import sys
import urllib.request
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
AEI_DIR = ROOT / "data" / "input" / "anthropic"
BLS_OES_PATH = ROOT / "data" / "input" / "all_data_M_2024.xlsx"

ONET_CURRENT = "30.2"  # keep in sync with download_onet.py CURRENT_VERSION
AEI_HF_URL = "https://huggingface.co/datasets/Anthropic/EconomicIndex/tree/main"

BLS_OES_YEAR_CURRENT = 2024
BLS_OES_BASE_URL = "https://www.bls.gov/oes/special.requests/all_data_M_{year}.xlsx"
BLS_PROJ_URL = "https://www.bls.gov/emp/tables/occupational-projections-and-characteristics.htm"
BLS_PROJ_CURRENT_CYCLE = "2024-2034"


# ── Helpers ────────────────────────────────────────────────────────────────────

def head_ok(url: str, timeout: int = 10) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def fetch_text(url: str, timeout: int = 15) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ── Checks ─────────────────────────────────────────────────────────────────────

def check_onet() -> dict:
    candidates = ["30.3", "30.2", "30.1", "29.3"]
    latest = None
    for v in candidates:
        major, minor = v.split(".")
        url = f"https://www.onetcenter.org/dl_files/database/db_{major}_{minor}_excel.zip"
        if head_ok(url):
            latest = v
            break

    current_ok = head_ok(
        f"https://www.onetcenter.org/dl_files/database/db_{ONET_CURRENT.replace('.', '_')}_excel.zip"
        .replace("_", f"_{ONET_CURRENT.split('.')[0]}_", 1)
    )

    if latest is None:
        return {"status": "error", "message": "Could not reach O*NET server"}

    up_to_date = latest == ONET_CURRENT
    return {
        "status": "ok" if up_to_date else "update",
        "current": ONET_CURRENT,
        "latest": latest,
        "action": None if up_to_date else f"python3 scripts/download_onet.py --version {latest} && python3 scripts/download_onet.py --sync",
    }


def check_aei() -> dict:
    """Check HuggingFace for newer AEI releases than what's recorded in download_economic_index.py."""
    # Read current release from download script
    dl_script = Path(__file__).parent / "download_economic_index.py"
    current_release = None
    if dl_script.exists():
        text = dl_script.read_text()
        m = re.search(r'RELEASE\s*=\s*"(release_\d{4}_\d{2}_\d{2})"', text)
        if m:
            current_release = m.group(1)

    # Scrape HuggingFace for available release folders
    html = fetch_text(AEI_HF_URL)
    if html is None:
        return {"status": "error", "message": "Could not reach HuggingFace"}

    # Release folders look like: release_YYYY_MM_DD
    releases = sorted(set(re.findall(r"release_\d{4}_\d{2}_\d{2}", html)))
    latest_release = releases[-1] if releases else None

    up_to_date = (latest_release is None) or (latest_release == current_release)

    # Find latest local data file for display
    local_files = sorted(AEI_DIR.glob("aei_raw_*.csv")) if AEI_DIR.exists() else []
    latest_local = local_files[-1].name if local_files else "none"

    result = {
        "status": "ok" if up_to_date else "update",
        "current": f"{current_release} ({latest_local})" if current_release else latest_local,
        "latest": latest_release or "unknown",
    }
    if not up_to_date:
        result["action"] = (
            f"1. Download new CSV from HuggingFace ({latest_release})\n"
            "   → save to data/input/anthropic/\n"
            "   2. Update RELEASE in scripts/download_economic_index.py\n"
            "   3. Update AEI_FILE in scripts/build_task_table.py\n"
            "   4. Rerun Stage 3: python3 scripts/build_task_table.py"
        )
    return result


def check_bls_oes() -> dict:
    """Check if a newer BLS OES all_data file exists."""
    next_year = BLS_OES_YEAR_CURRENT + 1
    next_url = BLS_OES_BASE_URL.format(year=next_year)
    newer_exists = head_ok(next_url)

    if newer_exists:
        return {
            "status": "update",
            "current": f"all_data_M_{BLS_OES_YEAR_CURRENT}.xlsx",
            "latest": f"all_data_M_{next_year}.xlsx",
            "action": (
                f"wget '{next_url}' -O data/input/all_data_M_{next_year}.xlsx\n"
                f"   Then update BLS_OES_PATH references in scripts/enrich_onet.py and rerun Track A."
            ),
        }
    return {
        "status": "ok",
        "current": f"all_data_M_{BLS_OES_YEAR_CURRENT}.xlsx",
        "latest": f"all_data_M_{BLS_OES_YEAR_CURRENT}.xlsx (current)",
    }


def check_bls_projections() -> dict:
    """Check BLS projections page for a newer cycle."""
    # Parse current cycle years to look for newer ones
    m = re.match(r"(\d{4})-(\d{4})", BLS_PROJ_CURRENT_CYCLE)
    if not m:
        return {"status": "error", "message": "Invalid BLS_PROJ_CURRENT_CYCLE format"}
    start_year = int(m.group(1))

    # Check if a newer cycle's CSV would exist (next cycle starts one year later)
    next_start = start_year + 1
    next_end = int(m.group(2)) + 1
    next_cycle = f"{next_start}-{next_end}"

    # Try fetching the page; BLS sometimes blocks bots
    html = fetch_text(BLS_PROJ_URL)
    if html is None:
        # Fallback: note the current cycle and prompt manual check
        return {
            "status": "ok",
            "current": BLS_PROJ_CURRENT_CYCLE,
            "latest": f"{BLS_PROJ_CURRENT_CYCLE} (manual check needed — BLS blocked automated request)",
        }

    normalize = lambda s: re.sub(r"[–\-]", "-", s)
    cycles = sorted(set(re.findall(r"20\d\d[–\-]20\d\d", html)))
    cycles_norm = [normalize(c) for c in cycles]
    current_norm = normalize(BLS_PROJ_CURRENT_CYCLE)
    next_norm = normalize(next_cycle)

    newer = [c for c in cycles_norm if c > current_norm]

    if newer:
        latest = newer[-1]
        return {
            "status": "update",
            "current": BLS_PROJ_CURRENT_CYCLE,
            "latest": latest,
            "action": (
                f"Download new projections CSV from BLS ({latest})\n"
                "   → replace data/input/Employment Projections.csv (keep column names)\n"
                "   → rerun Track A"
            ),
        }
    return {
        "status": "ok",
        "current": BLS_PROJ_CURRENT_CYCLE,
        "latest": f"{BLS_PROJ_CURRENT_CYCLE} (current)",
    }


# ── Report ─────────────────────────────────────────────────────────────────────

STATUS_ICON = {"ok": "✓", "update": "↑", "error": "?"}

def print_result(name: str, result: dict):
    icon = STATUS_ICON.get(result["status"], "?")
    current = result.get("current", "")
    latest = result.get("latest", result.get("latest_release", ""))
    message = result.get("message", "")

    if result["status"] == "ok":
        print(f"  {icon}  {name:<30} up to date  ({current})")
    elif result["status"] == "update":
        print(f"  {icon}  {name:<30} UPDATE AVAILABLE")
        if current:
            print(f"       current : {current}")
        if latest:
            print(f"       latest  : {latest}")
        if result.get("latest_data_end"):
            print(f"       data end: {result['latest_data_end']}")
        if result.get("action"):
            print(f"       action  : {result['action']}")
    else:
        print(f"  {icon}  {name:<30} ERROR: {message}")


def main():
    print("Checking data source updates...\n")

    checks = [
        ("O*NET Database",              check_onet),
        ("Anthropic Economic Index",    check_aei),
        ("BLS OES Wages",               check_bls_oes),
        ("BLS Employment Projections",  check_bls_projections),
    ]

    any_update = False
    for name, fn in checks:
        print(f"  Checking {name}...", end=" ", flush=True)
        result = fn()
        print()
        print_result(name, result)
        print()
        if result["status"] == "update":
            any_update = True

    if not any_update:
        print("All sources are up to date.")
    else:
        print("After downloading updates, rerun the relevant pipeline stages (see docs/pipeline.md).")


if __name__ == "__main__":
    main()
