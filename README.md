# AI-Resilient Occupations Scoring

A framework for identifying which jobs are resilient to AI displacement, scored across 10 key attributes that measure both defensive protections (why AI can't take over) and offensive opportunities (how AI can amplify expertise).

Final output is [hosted at this site](https://ai-proof-careers.com).


## Project Structure

```
.
├── README.md                          # This file
├── CLAUDE.md                          # Development instructions for Claude Code
├── docs/pipeline.md                   # Full pipeline reference (stages, schemas, AEI detail)
├── requirements.txt                   # Python dependencies
├── docs/
│   ├── 10-attributes.md              # The 10 attributes that drive resilience
│   ├── scoring-framework.md          # Complete scoring rubric & calculation logic
│   ├── career_page_spec.md           # Career page component specification
│   ├── tone_guide_career_pages.md    # Tone guide for career page prose
│   └── tone_guide_key_drivers.md     # Tone guide for key drivers text
├── data/
│   ├── input/
│   │   ├── All_Occupations_ONET.csv       # O*NET occupation data (raw)
│   │   ├── Employment Projections.csv     # BLS 2024-2034 employment projections
│   │   ├── SimpleJobTitles_altPathurl_*.csv  # SOC → AltPath URL + simplified titles
│   │   ├── anthropic/                     # Anthropic Economic Index data (not committed)
│   │   └── onet_db/                       # O*NET 30.2 Database files (Excel)
│   │       ├── Occupation Data.xlsx
│   │       ├── Sample of Reported Titles.xlsx
│   │       ├── Education Training and Experience.xlsx
│   │       ├── ETE Categories.xlsx
│   │       ├── Task Statements.xlsx       # 19,636 task statements mapped to occupation codes
│   │       └── Task Ratings.xlsx          # Task importance/frequency ratings
│   ├── intermediate/
│   │   ├── All_Occupations_ONET_enriched.csv        # Enriched input for scoring
│   │   ├── onet_economic_index_task_table.csv        # 18,796 task rows + AEI metrics
│   │   └── onet_economic_index_metrics.csv           # 923 occupation-level AEI rollups
│   ├── output/
│   │   ├── ai_resilience_scores.csv       # Scored & ranked occupations (all 1,016)
│   │   └── cards/                         # Per-occupation career page data (one .json per occupation)
│   ├── career_clusters/                   # Career ladder topology
│   │   ├── clusters.csv                   # Career cluster definitions
│   │   ├── cluster_branches.csv           # From→to career transitions
│   │   └── cluster_roles.csv              # Occupation → cluster membership + level
│   ├── emerging_roles/                    # Emerging AI-era roles & job title aliases
│   │   ├── emerging_roles.csv             # AI-adjacent pivot roles per occupation
│   │   └── emerging_job_titles.csv        # Real-world title aliases for O*NET codes
│   ├── tiers_and_next_steps/              # Tier system definitions
│   └── top_no_degree_careers/             # Curated subset: top careers requiring no bachelor's
│       ├── ENRICHMENT_INSTRUCTIONS.md
│       ├── ai_resilience_scores-associates-5.5.csv
│       └── ai_resilience_scores-associates-5.5-enriched.csv
└── scripts/
    ├── enrich_onet.py                # Track A Stage 1: Enrich O*NET data
    ├── score_occupations.py          # Track A Stage 2: Score all occupations via Claude API
    ├── build_task_table.py           # Track A Stage 3: Task table + AEI metrics
    ├── cards.py                      # Shared helpers: load_cards(), save_card(), save_cards()
    ├── generate_emerging_roles.py    # Track B Stage 5: Generate emerging AI-adjacent roles
    ├── generate_emerging_job_titles.py  # Track B Stage 6: Merge job title aliases into scores CSV
    ├── generate_next_steps.py        # Track B Stage 7a: Generate occupation cards
    ├── adjacent_roles.py             # Track B Stage 7b: Add careerCluster to cards
    ├── download_onet.py              # Utility: Download & manage O*NET database versions
    ├── download_economic_index.py    # Utility: Download Anthropic Economic Index from HuggingFace
    ├── patch_task_data.py            # Utility: Patch task data in career page .tsx files
    ├── test_scoring.py               # Test: Quick test with 3 occupations
    └── test_enrichment.py            # Test: Enrichment pipeline validation
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

### Full Pipeline

The pipeline has two tracks. See `docs/pipeline.md` for full detail.

**Track A — Baseline (run on data updates):**
```bash
python3 scripts/enrich_onet.py        # Stage 1: enrich
python3 scripts/score_occupations.py  # Stage 2: score
python3 scripts/build_task_table.py   # Stage 3: AEI task table
```

**Track B — Career page enrichment (per-cluster, on demand):**
```bash
# Use .claude/skills/career-clusters skill to populate cluster files, then:
python3 scripts/generate_emerging_roles.py --cluster <id>
python3 scripts/generate_emerging_job_titles.py
python3 scripts/generate_next_steps.py --cluster <id>
python3 scripts/adjacent_roles.py --cluster <id>
```

**Output:** `data/output/cards/` is the bridge to the site repo. One JSON file per occupation (e.g. `13-2031.00.json`). Each `.tsx` career page embeds data from the corresponding card. Use `scripts/cards.py` helpers to read/write — never open these files directly in pipeline scripts.

### Input Data

- **`data/input/All_Occupations_ONET.csv`** — downloaded from [O*NET Online — All Occupations](https://www.onetonline.org/find/all)
- **`data/input/Employment Projections.csv`** — BLS 2024-2034 employment projections from [data.bls.gov](https://data.bls.gov/projections/occupationProj)
- **`data/input/SimpleJobTitles_altPathurl_*.csv`** — maps SOC codes to AltPath URLs and simplified job titles
- **`data/input/onet_db/`** — O*NET 30.2 Database files (Excel), from [onetcenter.org](https://www.onetcenter.org/database.html). Licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  - `Occupation Data.xlsx` — occupation codes, titles, and descriptions
  - `Sample of Reported Titles.xlsx` — real-world job titles mapped to occupations
  - `Education Training and Experience.xlsx` — education level requirements with survey percentages
  - `ETE Categories.xlsx` — category-to-label mapping for education levels
  - `Task Statements.xlsx` — task statements with O*NET-SOC codes; used to map AEI tasks to occupations
  - `Task Ratings.xlsx` — task importance and frequency ratings
- **`data/input/anthropic/`** — Anthropic Economic Index data (auto-downloaded from [HuggingFace](https://huggingface.co/datasets/Anthropic/EconomicIndex), release 2026-01-15). **Not committed to git.** To download:
  ```bash
  python3 scripts/download_economic_index.py
  ```
  Licensed under [CC BY](https://creativecommons.org/licenses/by/4.0/) (data) and [MIT](https://opensource.org/licenses/MIT) (code).

### Updating Source Data

**Check all sources at once:**
```bash
python3 scripts/check_data_updates.py
```
Reports update status for O*NET, Anthropic Economic Index, BLS OES wages, and BLS Employment Projections, with actionable commands for anything out of date.

**O*NET Database:**
```bash
python3 scripts/download_onet.py --check          # Check for newer version
python3 scripts/download_onet.py --version XX.Y   # Download & back up
python3 scripts/download_onet.py --sync           # Sync occupation list
```

**Anthropic Economic Index:** Download new CSV from [HuggingFace](https://huggingface.co/datasets/Anthropic/EconomicIndex) → save to `data/input/anthropic/` → update `AEI_FILE` in `scripts/build_task_table.py` → rerun Stage 3.

**BLS OES Wages:** Download `all_data_M_{YEAR}.xlsx` from [BLS](https://www.bls.gov/oes/special.requests/) → replace `data/input/all_data_M_2024.xlsx` → update path references in `scripts/enrich_onet.py` → rerun Track A.

**BLS Employment Projections:** Download from [BLS](https://www.bls.gov/emp/tables/occupational-projections-and-characteristics.htm) → replace `data/input/Employment Projections.csv` keeping column names identical → rerun Track A.

### Testing

Test the scoring pipeline with 3 sample occupations:
```bash
python3 scripts/test_scoring.py
```


## The Scoring Framework (V2)

### The 12 Attributes

**Defensive (Why AI can't take over):**
- **A1** — Physical Presence & Dexterity Required
- **A2** — Trust is the Core Product
- **A3** — Novel, Ambiguous Judgment in High-Stakes Situations
- **A4** — Legal or Ethical Accountability
- **A5** — Deep Contextual Knowledge Built Over Time
- **A6** — Political & Interpersonal Navigation
- **A7** — Creative Work with a Genuine Point of View
- **A8** — Work That Requires Being Changed by the Experience

**Offensive (How AI amplifies these roles):**
- **A9** — Expertise Underutilized Due to Administrative/Volume Constraints
- **A10** — Downstream of Bottlenecks / Manages AI Systems

**Data-Driven Baseline:**
- **A11** — Observed Technical Exposure (Derived from O*NET Auto-Enumerate Index)
- **A12** — Demand Elasticity (Calculated via `generate_elasticity_scores.py`)

### The 3 Core Filters & 4 Categories
The 12 attributes are mathematically blended into 3 core filters:
1. **Exposure Filter:** How technically exposed are the core tasks?
2. **Necessity Filter:** How badly does the job require a physical human or legal/trust relationship?
3. **Elasticity Filter:** Will making the job's core output cheaper drive massive new market demand?

Jobs are then sorted into 4 transition archetypes based on these filters:
- **Grow with AI**: High Exposure, High Demand Elasticity.
- **Will Reorganize**: High Exposure, Strong Human Necessity.
- **Less Immediate Change**: Low Exposure.
- **High Automation Risk**: High Exposure, Weak Human Necessity, Low Demand Elasticity.

### Final Ranking (0.0-1.0)
The `final_ranking` is a weighted composite that scores an occupation *within* its transition category:

`Final Rank = Necessity(35%) + Elasticity(25%) - Exposure(20%) + BLS Growth(15%) + BLS Openings(5%)`

See `docs/scoring-framework.md` for complete formulas and threshold calculation details.

## Output Format

### Main Dataset (`data/output/ai_resilience_scores.csv`)

| Column | Description |
|--------|-------------|
| `Job Zone` | O*NET Job Zone (1-5, reflects preparation level) |
| `Code` | O*NET/SOC occupation code |
| `Occupation` | Occupation title |
| `Data-level` | Indicates if row is a broad or detailed O*NET occupation |
| `url` | O*NET Online URL for the occupation |
| `Median Wage` | Wage string scraped from O*NET (e.g. "$39.27 hourly, $81,680 annual") |
| `Projected Growth` | Growth category scraped from O*NET |
| `Employment Change, 2024-2034` | Numeric BLS percent change; empty for specialty subcodes |
| `Projected Job Openings` | Projected openings 2024-2034 |
| `Education` | Top 2 education levels with survey percentages |
| `Top Education Level` | Education level with highest reporting percentage |
| `Top Education Rate` | Reporting percentage for top education level |
| `Sample Job Titles` | Real-world job titles for this occupation |
| `Job Description` | Short description of the role |
| `exposure_filter` | Calculated 1-5 filter score for Technical Exposure |
| `necessity_filter` | Calculated 1-5 filter score for Human Necessity |
| `elasticity_filter` | Calculated 1-5 filter score for Demand Elasticity |
| `ai_category` | The AI transition archetype (e.g. Grow with AI) |
| `final_ranking` | 0.0-1.0 composite ranking (higher = better) |
| `key_drivers` | 2-3 sentence explanation of the score |
| `altpath url` | AltPath.org career page URL |
| `altpath simple title` | Plain-language job title |
| `Emerging Job Titles` | Semicolon-separated real-world title aliases (e.g. "Social Media Manager; Content Strategist") |

### Occupation Cards (`data/output/cards/`)

One JSON file per occupation (e.g. `data/output/cards/13-2031.00.json`). Contains all data needed to generate a career page: score, salary, growth, task-level AI data (automation/augmentation rates from Anthropic Economic Index), adjacent roles, emerging roles, how-to-adapt guidance, and sourced quotes. Read and written via `scripts/cards.py` (`load_cards()`, `save_card()`, `save_cards()`).

### Top No-Degree Careers Subset (`data/top_no_degree_careers/`)

Filtered to `role_resilience_score >= 5.5` and `Top Education Level <= associate's`. The enriched file adds 10-year earnings projections, difficulty scores, training pathways, and job market analysis. See `data/top_no_degree_careers/ENRICHMENT_INSTRUCTIONS.md` for full schema.

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
- Francois Chollet on genuine reasoning vs. pattern matching
- Jensen Huang on "HR for AI" roles
- Satya Nadella on human-AI collaboration
- Daron Acemoglu on task boundaries & automation risk
