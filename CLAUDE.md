# AI-Resilient Occupations Data

Scoring framework for AI job resilience across 1,000+ O*NET occupations. Site: ai-proof-careers.com

## Key Files

- `data/input/` — raw O*NET + BLS source files
- `data/intermediate/All_Occupations_ONET_enriched.csv` — enriched input for scoring
- `data/output/ai_resilience_scores.csv` — final scored dataset (all occupations)
- `data/top_no_degree_careers/` — curated subset: top careers requiring ≤ associate's degree
- `scripts/score_occupations.py` — Claude API scoring pipeline
- `scripts/enrich_onet.py` — enriches O*NET data (currently being refactored)
- `docs/scoring-framework.md` — full scoring methodology and rubrics

## Pipeline

```
enrich_onet.py → [data/intermediate/] → score_occupations.py → data/output/ai_resilience_scores.csv
```

**Note: `enrich_onet.py` is currently under active refactoring — do not assume it's stable.**

### Commands

```bash
source venv/bin/activate
python3 scripts/enrich_onet.py        # Step 1: enrich (refactoring in progress)
python3 scripts/score_occupations.py  # Step 2: score all occupations
python3 scripts/test_scoring.py       # Quick test with 3 occupations
```

Requires `ANTHROPIC_API_KEY` env var.

## Scoring Summary

- **10 attributes**: A1–A8 defensive (65%), A9–A10 offensive (35%)
- **`ai_proof_score`**: 1.0–5.0
- **`final_ranking`**: 0.0–1.0 composite (score 50% + growth 30% + openings 20%)
- Special rules: ceiling cap at 2.5 if A1+A3+A4 all ≤ 2; floor at 3.0 if A9 or A10 = 5

See `docs/scoring-framework.md` for full rubric.

## Top No-Degree Careers Sub-Dataset

Subset filtered to `ai_proof_score ≥ 5.5` and `Top Education Level ≤ associate's`.

- Base: `data/top_no_degree_careers/ai_resilience_scores-associates-5.5.csv`
- Enriched: `data/top_no_degree_careers/ai_resilience_scores-associates-5.5-enriched.csv`
- Schema + methodology: `data/top_no_degree_careers/ENRICHMENT_INSTRUCTIONS.md`
