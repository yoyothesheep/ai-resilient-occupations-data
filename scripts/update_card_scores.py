#!/usr/bin/env python3
"""
Update JSON cards with V2 AI resilience scores and categories.
This ensures we can regenerate TSX pages without re-running the expensive LLM prompts.
"""

import json
from pathlib import Path
from loaders import load_scores, to_score
from generate_next_steps import sanitize

CARDS_DIR = Path("data/output/cards")

def main():
    print("Loading CSV scores...")
    scores = load_scores()
    
    updated = 0
    failed = 0
    
    print("Updating cards...")
    for card_file in CARDS_DIR.glob("*.json"):
        onet_code = card_file.stem
        
        # Load the existing JSON card
        try:
            with open(card_file, "r") as f:
                card_data = json.load(f)
        except json.JSONDecodeError:
            print(f"  ✗ Failed to parse JSON: {card_file}")
            failed += 1
            continue
            
        occ = scores.get(onet_code)
        if not occ:
            print(f"  ✗ No CSV row found for {onet_code}")
            failed += 1
            continue
            
        # Update V2 score and category fields
        card_data["score"] = to_score(occ)
        card_data["ai_category"] = occ.get("ai_category", "")
        card_data["exposure_filter"] = occ.get("exposure_filter", "")
        card_data["necessity_filter"] = occ.get("necessity_filter", "")
        card_data["elasticity_filter"] = occ.get("elasticity_filter", "")
        # Sync regenerated key drivers (sanitized to match generation-time style)
        kd = occ.get("key_drivers", "")
        if kd:
            card_data["keyDrivers"] = sanitize(kd)
        
        # Write back to JSON
        with open(card_file, "w", newline="", encoding="utf-8") as f:
            json.dump(card_data, f, indent=2, ensure_ascii=False)
            
        updated += 1
        
    print(f"✓ Updated {updated} cards successfully. {failed} failed.")

if __name__ == "__main__":
    import sys
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)
    main()
