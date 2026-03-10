#!/usr/bin/env python3
"""
Fix missing 'Top Education Level' values in ai_resilience_scores.csv
by extracting from the 'Education' field when available.
"""

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "output" / "ai_resilience_scores.csv"
OUTPUT_FILE = INPUT_FILE  # Overwrite in place


def extract_top_education_level(education_str: str) -> str:
    """
    Extract the top education level from education string.

    Examples:
    - "50% Bachelor's degree | 36% Associate's degree" -> "Bachelor's degree"
    - "100% Master's degree" -> "Master's degree"
    - "57% Bachelor's degree" -> "Bachelor's degree"
    """
    if not education_str:
        return ""

    # Split by pipe if present
    parts = education_str.split("|")
    if parts:
        first_part = parts[0].strip()
        # Extract education level from percentage format
        # Format: "XX% Education Level"
        match = re.match(r"(\d+%)\s+(.*)", first_part)
        if match:
            return match.group(2).strip()

    return ""


def main():
    print(f"Loading {INPUT_FILE}...")

    rows = []
    fixed_count = 0

    with open(INPUT_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        for row in reader:
            top_ed = row.get('Top Education Level', '').strip()
            education = row.get('Education', '').strip()

            # If Top Education Level is missing but Education has data
            if not top_ed and education:
                extracted = extract_top_education_level(education)
                if extracted:
                    row['Top Education Level'] = extracted
                    fixed_count += 1
                    print(f"  Fixed: {row['Occupation']} -> {extracted}")

            rows.append(row)

    print(f"\nFixed {fixed_count} rows")
    print(f"Writing to {OUTPUT_FILE}...")

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("✓ Done!")


if __name__ == '__main__':
    main()
