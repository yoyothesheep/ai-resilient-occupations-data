# AI-Resilient Occupations Scoring

A framework for identifying which jobs are resilient to AI displacement, scored across 10 key attributes that measure both defensive protections (why AI can't take over) and offensive opportunities (how AI can amplify expertise).

Final output is [hosted at this site](https://ai-proof-careers.com).


## Project Structure

```
.
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── docs/
│   ├── 10-attributes.md              # The 10 attributes that drive resilience
│   └── scoring-framework.md          # Complete scoring rubric & calculation logic
├── data/
│   ├── input/
│   │   └── All_Occupations_ONET.csv  # O*NET occupation data (raw, from external source)
│   ├── intermediate/
│   │   ├── onet_enrichment_cache.json     # Cached scrape results (resumable)
│   │   ├── onet_enrichment.csv            # Enrichment fields only
│   │   └── All_Occupations_ONET_enriched.csv # Full dataset with enrichment 
│   └── output/
│       ├── ai_resilience_scores.csv  # Scored & ranked occupations
│       └── score_log.txt             # Progress log for resuming runs
└── scripts/
    ├── score_occupations.py          # Scores via Claude API + computes final ranking
    ├── test_scoring.py               # Quick test with 3 occupations
    └── enrich_onet.py                # Scrapes wage & projection data from O*NET
```

## Quick Start

### Prerequisites

Get your API key from [Anthropic Console](https://console.anthropic.com):
1. Go to Settings → API Keys
2. Create a new API key
3. Copy it (starts with `sk-ant-v1-`)

Install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set the environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-v1-..."
```

Or add to `~/.zshrc` for persistence:
```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-v1-..."' >> ~/.zshrc
source ~/.zshrc
```

### Input Data

The initial occupation list CSV is downloaded from [O*NET Online — All Occupations](https://www.onetonline.org/find/all) and stored in `data/input/`.

### Enrich Input Data

**Required before scoring.** Scrape wage, growth, and job opening data from O*NET Online (run once, ~17 min):

```bash
python3 scripts/enrich_onet.py
```

**Output files created in `data/intermediate/`:**
- `All_Occupations_ONET_enriched.csv` — full dataset (all original columns + enrichment)
  - `Median Wage` — e.g. "$39.27 hourly, $81,680 annual"
  - `Projected Growth` — e.g. "Faster than average (5% to 6%)"
  - `Projected Job Openings` — e.g. "124,200"
  - `Education` — top 2 required education levels with percentages
- `onet_enrichment.csv` — enrichment fields only (for reference)
- `onet_enrichment_cache.json` — scraping cache (allows resuming if interrupted)

**Note:** Military occupations (55-xxxx codes) have no wage or projection data on O*NET.

### Score & Rank All Occupations

**Prerequisite:** Run enrichment step first (see above).

```bash
python3 scripts/score_occupations.py
```

This will:
1. Load all occupations from `data/intermediate/All_Occupations_ONET_enriched.csv` (enriched dataset)
2. Batch them (10 per batch by default)
3. Score each batch via Claude API (scores all 10 attributes + calculates `ai_proof_score`)
4. Compute composite `final_ranking` from score + growth + openings
5. Write results to `data/output/ai_resilience_scores.csv`, sorted by ranking

**If interrupted, just run again** — it resumes from where it left off.

**Implementation Note:** This project uses the [Anthropic Claude API](https://www.anthropic.com/api) to parallelize scoring across occupation batches. Batching 10 occupations per API call reduces latency and improves throughput compared to single-occupation requests. Scoring ~1,000 occupations typically completes in 3–4 hours with built-in rate limiting (2s sleep between batches). The API also enables resumable processing — the script maintains a cache of scored occupations and skips them on subsequent runs.

### Testing (Optional)

**Prerequisite:** Run enrichment step first (see above).

Test the scoring pipeline with 3 sample occupations using real Claude API:
```bash
python3 scripts/test_scoring.py
```

This runs a quick end-to-end test:
1. Loads the first 3 occupations from the enriched dataset
2. Scores them via Claude API with full 10-attribute evaluation
3. Computes final rankings
4. Outputs results to `data/output/test_scores.csv`

Use this to validate the pipeline before running the full dataset.


## The Scoring Framework

### 10 Attributes

**Defensive (65% weight):** Why AI can't take over
- **A1** — Physical Presence & Dexterity Required
- **A2** — Trust is the Core Product
- **A3** — Novel, Ambiguous Judgment in High-Stakes Situations
- **A4** — Legal or Ethical Accountability
- **A5** — Deep Contextual Knowledge Built Over Time
- **A6** — Political & Interpersonal Navigation
- **A7** — Creative Work with a Genuine Point of View
- **A8** — Work That Requires Being Changed by the Experience

**Offensive (35% weight):** How AI amplifies these roles
- **A9** — Expertise Underutilized Due to Administrative/Volume Constraints
- **A10** — Downstream of Bottlenecks / Manages AI Systems

### AI-Proof Score (1.0–5.0)

```
Defensive Score = weighted average of A1–A8 (with attribute-specific weights)
Offensive Score = average of A9–A10
ai_proof_score  = (Defensive × 0.65) + (Offensive × 0.35)
```

**Special Rules:**
- **Ceiling Rule:** If A1 + A3 + A4 all ≤ 2, cap score at 2.5
- **Floor Rule:** If A9 or A10 scores 5, minimum score is 3.0

### Final Ranking (0.0–1.0)

The `final_ranking` is a weighted composite that combines the AI-proof score with labor market signals:

| Input | Weight | Normalization |
|-------|--------|---------------|
| `ai_proof_score` | 50% | Linear scale: `(score - 1) / 4` |
| `Projected Growth` | 30% | Ordinal: Decline=0, Little/none=0.2, Slower=0.4, Average=0.6, Faster=0.8, Much faster=1.0 |
| `Projected Job Openings` | 20% | Log-transform + min-max scale |

See `docs/scoring-framework.md` for complete rubrics and calculation details.

## Output Format

The CSV output includes:
- `Median Wage` — wage data from O*NET
- `Projected Growth` — BLS growth rate category
- `Projected Job Openings` — projected openings (2024–2034)
- `ai_proof_score` — 1.0–5.0 AI resilience rating
- `final_ranking` — 0.0–1.0 composite ranking (higher = better)
- `key_drivers` — 2–3 sentence explanation of the score

## Configuration

Edit `scripts/score_occupations.py` to adjust:
- `BATCH_SIZE` — occupations per API call (default: 10)
- `SLEEP_SEC` — delay between batches (default: 2s)
- `START_BATCH` — resume from a specific batch number
- `MODEL` — Claude model to use (default: claude-opus-4-6)

## References

Framework synthesized from:
- Andrew Ng on task automation & institutional knowledge
- Yann LeCun on trust in human relationships
- François Chollet on genuine reasoning vs. pattern matching
- Jensen Huang on "HR for AI" roles
- Satya Nadella on human-AI collaboration
- Daron Acemoglu on task boundaries & automation risk
