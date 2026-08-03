#!/usr/bin/env python3
"""
Download Anthropic Economic Index 2026-06-26 release data.

Source: https://huggingface.co/datasets/Anthropic/EconomicIndex
Release: 2026-06-26

Note: this release moved the data files from `{RELEASE}/data/intermediate/`
to `{RELEASE}/data/` and renamed them from `aei_raw_*` to `aei_*`.
"""

import os
from pathlib import Path
from huggingface_hub import hf_hub_url
import urllib.request

# Configuration
REPO_ID = "Anthropic/EconomicIndex"
RELEASE = "release_2026_06_26"
DATA_DIR = Path(__file__).parent.parent / "data" / "input" / "anthropic"

# Files to download
FILES_TO_DOWNLOAD = [
    "aei_claude_ai_2026-06-26.csv",
]

def download_file(repo_id, filename, local_path):
    """Download a file from HuggingFace using direct URL."""
    url = hf_hub_url(
        repo_id=repo_id,
        repo_type="dataset",
        filename=filename
    )

    print(f"URL: {url}")

    try:
        urllib.request.urlretrieve(url, local_path)
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"✓ Downloaded: {local_path.name} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def download_economic_index():
    """Download EconomicIndex files from HuggingFace."""

    # Ensure directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading Anthropic Economic Index {RELEASE}")
    print(f"Destination: {DATA_DIR}")
    print("=" * 70)

    for filename in FILES_TO_DOWNLOAD:
        filepath = f"{RELEASE}/data/{filename}"
        local_path = DATA_DIR / filename

        # Skip if already exists
        if local_path.exists():
            size_mb = local_path.stat().st_size / (1024 * 1024)
            print(f"✓ Already exists: {filename} ({size_mb:.1f} MB)\n")
            continue

        print(f"Downloading: {filename}")
        if download_file(REPO_ID, filepath, local_path):
            print()
        else:
            return False

    print("=" * 70)
    print("Download complete!")

    # List downloaded files
    files = list(DATA_DIR.glob("aei_*.csv"))
    print(f"\nFiles in {DATA_DIR}:")
    for f in sorted(files):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  - {f.name} ({size_mb:.1f} MB)")

    return True

if __name__ == "__main__":
    success = download_economic_index()
    exit(0 if success else 1)
