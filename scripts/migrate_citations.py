#!/usr/bin/env python3
"""
Migrate all card JSONs from src-N citation format to [Name, Date] / sourceUrl format.

For each data/output/cards/*.json:
  1. Convert [N] in body text → [sources[N-1].name, sources[N-1].date]
  2. Convert quote sourceId → sourceUrl using sources[] lookup
     - If sourceId matches and attribution agrees → use that source's url
     - If sourceId matches but attribution disagrees (collision) → try matching
       attribution text against known sources or emit a warning
  3. Remove id field from sources[] entries

Run: python3 scripts/migrate_citations.py [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

CARDS_DIR = Path("data/output/cards")

# Well-known sources that appear in quote attributions but may lack URLs in cards.
# Keyed by lowercase substring of the attribution text.
KNOWN_SOURCES: dict[str, dict] = {
    "world economic forum": {
        "name": "World Economic Forum",
        "title": "Future of Jobs Report 2025",
        "date": "Jan 2025",
        "url": "https://www.weforum.org/reports/the-future-of-jobs-report-2025/",
    },
    "wef future of jobs": {
        "name": "World Economic Forum",
        "title": "Future of Jobs Report 2025",
        "date": "Jan 2025",
        "url": "https://www.weforum.org/reports/the-future-of-jobs-report-2025/",
    },
    "future of jobs report 2025": {
        "name": "World Economic Forum",
        "title": "Future of Jobs Report 2025",
        "date": "Jan 2025",
        "url": "https://www.weforum.org/reports/the-future-of-jobs-report-2025/",
    },
    "mckinsey": {
        "name": "McKinsey Global Institute",
        "title": "The economic potential of generative AI",
        "date": "Jun 2023",
        "url": "https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights/the-economic-potential-of-generative-ai",
    },
    "edelman trust barometer": {
        "name": "Edelman",
        "title": "Trust Barometer 2025",
        "date": "Jan 2025",
        "url": "https://www.edelman.com/trust/2025/trust-barometer",
    },
}


def source_name_matches_attribution(source_name: str, attribution: str) -> bool:
    """Rough check: does the source name appear in the attribution text?"""
    name_lower = source_name.lower()
    attr_lower = attribution.lower()
    # Accept if any word of 4+ chars from name appears in attribution
    for word in name_lower.split():
        if len(word) >= 4 and word in attr_lower:
            return True
    return False


def find_known_source(attribution: str) -> dict | None:
    """Try to match attribution against KNOWN_SOURCES."""
    attr_lower = attribution.lower()
    for key, src in KNOWN_SOURCES.items():
        if key in attr_lower:
            return src
    return None


def migrate_card(card: dict, dry_run: bool = False) -> tuple[dict, list[str]]:
    """Migrate a single card. Returns (updated_card, warnings)."""
    warnings = []
    code = card.get("onet_code", "?")
    sources = card.get("sources", [])

    # Build id→source map (1-indexed for [N] body citations)
    id_map: dict[str, dict] = {}
    for s in sources:
        sid = s.get("id", "")
        if sid:
            id_map[sid] = s

    # ── 1. Convert [N] in body text ──────────────────────────────────────────

    def replace_numeric_citation(text: str) -> str:
        def replace(m):
            n = int(m.group(1))
            src = sources[n - 1] if n <= len(sources) else None
            if src:
                name = src.get("name", "")
                date = src.get("date", "")
                if name:
                    return f"[{name}, {date}]" if date else f"[{name}]"
            warnings.append(f"{code}: body text [{n}] has no matching source (only {len(sources)} sources)")
            return m.group(0)
        return re.sub(r'\[(\d+)\]', replace, text)

    body_fields = [
        ("risks", "body"),
        ("opportunities", "body"),
        ("howToAdapt", "alreadyIn"),
        ("howToAdapt", "thinkingOf"),
    ]
    for section, field in body_fields:
        sec = card.get(section)
        if isinstance(sec, dict) and isinstance(sec.get(field), str):
            sec[field] = replace_numeric_citation(sec[field])

    # ── 2. Convert quote sourceId → sourceUrl, and populate sourceDate ──────

    # Build url→date map from sources[] for date lookup
    url_to_date = {s.get("url"): s.get("date", "") for s in sources if s.get("url")}

    quotes = (card.get("howToAdapt") or {}).get("quotes", [])
    for q in quotes:
        attribution = q.get("attribution", "")

        if "sourceUrl" in q:
            # Already migrated — just add sourceDate if missing
            if not q.get("sourceDate"):
                src_url = q.get("sourceUrl", "")
                date = url_to_date.get(src_url, "")
                if not date:
                    # Try KNOWN_SOURCES
                    known = find_known_source(attribution)
                    if known:
                        date = known.get("date", "")
                if date:
                    q["sourceDate"] = date
            continue

        src_id = q.pop("sourceId", None)
        if not src_id:
            continue

        # Parse the index from "src-N"
        m = re.match(r'^src-(\d+)$', src_id)
        if m:
            idx = int(m.group(1)) - 1
            matched_src = sources[idx] if idx < len(sources) else None
        else:
            matched_src = id_map.get(src_id)

        def _set_url_and_date(src_dict: dict):
            q["sourceUrl"] = src_dict.get("url", "")
            q["sourceDate"] = src_dict.get("date", "")

        if matched_src and source_name_matches_attribution(matched_src.get("name", ""), attribution):
            _set_url_and_date(matched_src)
        else:
            known = find_known_source(attribution)
            if known:
                existing_urls = {s.get("url") for s in sources}
                if known["url"] not in existing_urls:
                    sources.append({k: v for k, v in known.items()})
                    url_to_date[known["url"]] = known.get("date", "")
                q["sourceUrl"] = known["url"]
                q["sourceDate"] = known.get("date", "")
                if matched_src:
                    warnings.append(
                        f"{code}: quote sourceId '{src_id}' ('{matched_src.get('name')}') "
                        f"didn't match attribution '{attribution[:60]}' — resolved via KNOWN_SOURCES"
                    )
            else:
                q["sourceUrl"] = ""
                q["sourceDate"] = ""
                warnings.append(
                    f"{code}: quote attribution '{attribution[:60]}' could not be resolved — "
                    f"sourceUrl left blank (renders as plain text, no link)"
                )

    # ── 3. Remove id field from sources[] ───────────────────────────────────

    for s in sources:
        s.pop("id", None)

    return card, warnings


def main():
    parser = argparse.ArgumentParser(description="Migrate card JSONs to new citation format")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    args = parser.parse_args()

    card_files = sorted(CARDS_DIR.glob("*.json"))
    if not card_files:
        print(f"No card files found in {CARDS_DIR}")
        sys.exit(1)

    all_warnings: list[str] = []
    migrated = 0
    skipped = 0

    for path in card_files:
        with open(path, encoding="utf-8") as f:
            card = json.load(f)

        card, warnings = migrate_card(card, dry_run=args.dry_run)
        all_warnings.extend(warnings)

        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(card, f, indent=2, ensure_ascii=False)
                f.write("\n")
            migrated += 1
        else:
            skipped += 1

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Processed {migrated + skipped} cards")
    if all_warnings:
        print(f"\n⚠  {len(all_warnings)} warnings (cards needing manual review):\n")
        for w in all_warnings:
            print(f"  • {w}")
    else:
        print("✓ No warnings — all citations resolved cleanly")


if __name__ == "__main__":
    main()
