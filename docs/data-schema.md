# Data Schema

Defines the structure and purpose of every output file. The CSV is the scoring index. The JSONL file is the site-facing product.

## Output file strategy

- **`ai_resilience_scores.csv`** — flat index for sorting, filtering, leaderboards. No long-form text except `key_drivers`.
- **`data/output/cards/{onet_code}.json`** — one JSON file per occupation (e.g. `11-2011.00.json`). Current production format. Written by `generate_next_steps.py`, `patch_risks_opps.py`, `adjacent_roles.py`, `generate_emerging_roles.py`. Read via `scripts/cards.py`.
- **`data/emerging_roles/emerging_roles.csv`** — AI-era pivot roles. Single source of truth for emerging career suggestions per occupation.

The site never reads the CSV directly. `generate_career_pages.py` reads the per-code JSON cards and scores CSV, then writes `.tsx` files into the site repo.

---

## 1. `data/output/ai_resilience_scores.csv`

The main scoring index. One row per occupation. Used for sorting, filtering, leaderboards, and analysis. No long-form text beyond `key_drivers`.

| Column | Type | Description |
|--------|------|-------------|
| `Code` | string | O*NET occupation code (e.g. `29-2061.00`) |
| `Occupation` | string | Official O*NET occupation title |
| `altpath simple title` | string | Human-readable simplified title |
| `Job Zone` | int | O*NET Job Zone 1–5 (proxy for complexity) |
| `Data-level` | string | O*NET data reliability level |
| `Top Education Level` | string | Most common education level for this occupation |
| `Top Education Rate` | float | % of workers with that education level |
| `Median Wage` | float | BLS median annual wage (USD) |
| `Projected Growth` | string | BLS projected growth rate label |
| `Employment Change, 2024-2034` | int | Projected net employment change |
| `Projected Job Openings` | int | Projected annual job openings |
| `role_resilience_score` | float | AI resilience score, 1.0–5.0 (higher = more resilient) |
| `final_ranking` | float | Composite ranking, 0.0–1.0 (score 50% + growth 30% + openings 20%) |
| `key_drivers` | string | 2–3 sentence plain-English explanation of what drives the score. Authoritative source for `keyDrivers` in occupation cards — always used over any card-level value. |
| `Emerging Job Titles` | string | Semicolon-separated real-world job title aliases (e.g. "Growth Marketer; Digital Strategist"). Written by `generate_emerging_job_titles.py`. Consumed by `generate_next_steps.py` as `emergingTitles` in cards. |
| `url` | string | O*NET occupation detail URL |
| `altpath url` | string | Alternative path / simplified career page URL |
| `Sample Job Titles` | string | Common job titles for this occupation |
| `Job Description` | string | O*NET occupation description |
| `Education` | string | Full education breakdown string |

---

## 2. `data/output/cards/{onet_code}.json`

One JSON file per occupation (e.g. `data/output/cards/27-3043.00.json`). Written by `generate_next_steps.py` (initial card), then patched by `patch_risks_opps.py`, `adjacent_roles.py`, `generate_emerging_roles.py`. Read via `scripts/cards.py`. Consumed by `generate_career_pages.py` to produce site `.tsx` files.

```jsonc
{
  // Identity — from scores CSV
  "onet_code": "27-3043.00",
  "title": "Copywriter",              // altpath simple title from scores CSV
  "score": 49,                        // final_ranking × 100, rounded int
  "salary": "$72,270",                // formatted median wage
  "openings": "13,400",              // formatted projected annual openings
  "growth": "+4%",                   // formatted employment change %

  // Job titles
  "jobTitles": ["Copywriter", "Ad Agency Copywriter", ...],   // from Sample Job Titles
  "emergingTitles": ["Copywriter", "Content Writer"],          // from Emerging Job Titles in scores CSV

  // Key drivers — always sourced from key_drivers in ai_resilience_scores.csv
  // (never regenerated here; pipeline writes it during scoring)
  "keyDrivers": "2–3 sentence plain-English explanation of score drivers.",

  // Task chart intro — displayed above the task chart on career page
  "taskIntro": "...",

  // Risks section
  "risks": {
    "body": "2–3 sentences. Inline citations like [1].",
    "stat": "-21%",                          // null if no strong stat
    "statLabel": "YoY decline in freelance writing job postings on Upwork",
    "statSourceName": "Upwork",
    "statSourceTitle": "Freelance Forward 2024",
    "statSourceDate": "Oct 2024",
    "statSourceUrl": "https://..."
  },

  // Opportunities section
  "opportunities": {
    "body": "2–3 sentences. Inline citations like [1].",
    "stat": "72%",                           // null if no strong stat; must differ from risks.stat
    "statLabel": "of top-performing content teams use humans for brand voice",
    "statSourceName": "Content Marketing Institute",
    "statSourceTitle": "B2B Content Marketing 2024",
    "statSourceDate": "Oct 2024",
    "statSourceUrl": "https://..."
  },

  // How to adapt section
  "howToAdapt": {
    "alreadyIn": "3–4 sentences for someone currently in the role.",
    "thinkingOf": "3–4 sentences for someone considering entering.",
    "quotes": [
      {
        "persona": "alreadyIn",          // or "thinkingOf"
        "quote": "Real quote from named practitioner or research report.",
        "attribution": "Person Name, Organization / Report Title",
        "sourceId": "src-1"             // matches id in sources[]
      }
      // 2 quotes per persona (4 total)
    ]
  },

  // Task data — top 10 tasks by weight, for the task chart
  "taskData": [
    {
      "task": "Short label",            // display label
      "full": "Full O*NET task text.",
      "auto": 47.7,                     // automation_pct; null if no AEI data or n < 100
      "aug": null,                      // augmentation_pct; null if no AEI data or n < 100
      "success": 61.5,                  // task_success_pct; null if no AEI data
      "n": 65                           // AEI conversation count; null if no AEI data
    }
  ],

  // Career cluster — populated by adjacent_roles.py
  // Up to 6–8 related careers. Sorted by level then score.
  "careerCluster": [
    {
      "level": 3,
      "code": "27-3043.00",
      "title": "Copywriter",
      "isCurrent": true,               // true for exactly one entry (the current role)
      "score": 2.4                     // role_resilience_score from CSV
    },
    {
      "level": 4,
      "code": "11-2011.00",
      "title": "Advertising Manager",
      "isCurrent": false,
      "score": 2.5,
      "relationship": "progression",   // "progression" | "specialization" | "lateral" | "adjacent"
      "salary": "$126,960",
      "openings": "2,100",
      "growth": "-2%",
      "fit": "One Feynman-style sentence explaining the connection.",
      "steps": ["Step 1", "Step 2", "Step 3"]   // 2–3 concrete credentials or actions
      // less_trained roles (one level below current) get relationship tagged "less_trained"
    }
  ],
  // relationship values:
  //   "progression"    — step up in level (from cluster_branches or level diff)
  //   "specialization" — same level, narrower focus
  //   "lateral"        — different track, similar standing
  //   "adjacent"       — task overlap but no direct cluster path
  //   "less_trained"   — one level below current (shown for context, not recommended next step)

  // Emerging careers — populated by generate_emerging_roles.py from emerging_roles.csv
  "emergingCareers": [],   // array of emerging role objects; empty if none generated yet

  // Sources — cited in risks.body, opportunities.body, howToAdapt prose
  // stat sources (statSourceName etc.) are merged into this array by generate_career_pages.py
  "sources": [
    {
      "id": "src-1",        // referenced as [1] in body prose; "src-N" format
      "name": "Upwork",
      "title": "Freelance Forward 2024",
      "date": "Oct 2024",
      "url": "https://..."
    }
  ]
}
```

---

## 3. `data/emerging_roles/emerging_roles.csv`

Single source of truth for AI-era career pivot suggestions per occupation. Written by `generate_emerging_roles.py`. Consumed by the same script to merge `emergingCareers` into occupation cards.

| Column | Type | Description |
|--------|------|-------------|
| `onet_code` | string | Source occupation O*NET code |
| `emerging_title` | string | Title of the emerging role |
| `description` | string | 1–2 sentence role description |
| `core_tools` | string | Comma-separated key tools/platforms |
| `stat_text` | string | Supporting market stat (plain text) |
| `stat_source` | string | Stat publisher name |
| `stat_title` | string | Stat source title |
| `stat_date` | string | Stat publication date |
| `stat_url` | string | Stat source URL |
| `search_query` | string | Job board search string used to verify postings exist |
| `job_search_url` | string | URL to live job search results |
| `fit` | string | One sentence on why this role is a natural pivot |
| `steps_json` | string | JSON array of 2–3 concrete transition steps |
| `experience_level` | int | Seniority level 1–5 relative to source occupation |

---

## 4. `data/output/score_log.txt`

Human-readable log written by `score_occupations.py`. One block per occupation. Parsed by `patch_risks_opps.py` and other scripts to extract per-occupation A1–A10 attribute scores, which are not stored in the CSV.

Format per occupation block:
```
  Occupation Title (XX-XXXX.XX)
    A1 Physical Presence: 4
    A2 Trust as Core Product: 3
    ...
    A10 Downstream AI Management: 2
    → role_resilience_score: 3.2
    → final_ranking: 0.61
```

Parsed via regex in `load_a_scores()` in `patch_risks_opps.py`.

---

## 5. `data/intermediate/onet_economic_index_task_table.csv`

Full task-level table. 18,796 rows, one per O*NET task. Used to generate occupation-level metrics and task highlights in the JSON cards. Not consumed directly by the site.

| Column | Type | Description |
|--------|------|-------------|
| `onet_code` | string | O*NET occupation code |
| `task_id` | string | O*NET task identifier |
| `task_text` | string | Full task description |
| `freq_score` | float | Frequency score from O*NET Task Ratings (FT scale, weighted avg) |
| `importance_score` | float | Importance score from O*NET Task Ratings (IM scale, 1–5) |
| `task_weight` | float | `freq_score × importance_score`; fallback = occupation mean (global mean 16.97) |
| `weight_source` | string | `rated` or `mean_fallback` |
| `in_aei` | bool | Whether this task matched an AEI task |
| `match_type` | string | `exact`, `fuzzy`, or null |
| `onet_task_count` | int | Number of AEI conversations matching this task (n=) |
| `onet_task_pct` | float | % of AEI conversations for this occupation matching this task |
| `automation_pct` | float | % of matching conversations classified as automation |
| `augmentation_pct` | float | % of matching conversations classified as augmentation |
| `task_success_pct` | float | % of matching conversations where task was completed |
| `ai_autonomy_mean` | float | Mean AI autonomy rating (1–5) across matching conversations |
| `speedup_factor` | float | `(human_only_time_hours × 60) / human_with_ai_time_minutes` |

---

## 6. `data/intermediate/onet_economic_index_metrics.csv`

Occupation-level AEI rollups. 923 occupations. Weighted means over AEI-matched tasks only.

| Column | Type | Description |
|--------|------|-------------|
| `onet_code` | string | O*NET occupation code |
| `total_tasks` | int | Total O*NET tasks for this occupation |
| `aei_tasks` | int | Number of tasks matched to AEI |
| `ai_task_coverage_pct` | float | `aei_tasks / total_tasks × 100` |
| `weighted_automation_pct` | float | Weighted mean automation % across AEI tasks |
| `weighted_augmentation_pct` | float | Weighted mean augmentation % across AEI tasks |
| `weighted_task_success_pct` | float | Weighted mean task success % across AEI tasks |
| `weighted_ai_autonomy_mean` | float | Weighted mean AI autonomy score across AEI tasks |
| `weighted_speedup_factor` | float | Weighted mean speedup factor across AEI tasks |

---

## 7. Career Cluster Files (`data/career_clusters/`)

Three CSV files define the career ladder topology used to populate career pages.

### `clusters.csv`
One row per cluster.

| Column | Type | Description |
|--------|------|-------------|
| `cluster_id` | string | Slug identifier, e.g. `marketing` |
| `cluster_name` | string | Display name, e.g. `Marketing & Growth` |
| `industry_slug` | string | URL slug for the industry page |
| `industry_display_name` | string | Display name for the industry page |

### `cluster_roles.csv`
One row per occupation. **Invariant: each `onet_code` must appear in exactly one cluster.** Cross-cluster visibility is handled via `cluster_branches.csv` with `is_cross_family=true`, never by listing a role in two clusters.

| Column | Type | Description |
|--------|------|-------------|
| `onet_code` | string | O*NET code — unique across the entire file |
| `occupation` | string | O*NET occupation title |
| `cluster_id` | string | FK → `clusters.csv` |
| `level` | int | Career level 1–5 (1=entry, 5=principal) |
| `is_canonical` | bool | Whether this is a primary/representative role in the cluster |
| `typical_years_from_entry` | int | Typical years experience to reach this level |
| `notes` | string | Context injected into Claude prompt for adjacent-role generation |

### `cluster_branches.csv`
One row per from→to career transition.

| Column | Type | Description |
|--------|------|-------------|
| `from_onet_code` | string | Source role — must exist in `cluster_roles.csv` |
| `to_onet_code` | string | Target role — must exist in `cluster_roles.csv` unless `is_cross_family=true` |
| `transition_type` | string | `progression` (step up) or `lateral` (peer-level pivot) |
| `is_cross_family` | bool | True when target is in a different cluster |
| `notes` | string | Ground truth for "how to make the move" steps in adjacent-role generation |

**Design rule:** when a role's best next move is in a different cluster, use a cross-family branch rather than duplicating the role. The integrity check in `.claude/skills/career-clusters/SKILL.md` enforces the uniqueness constraint.

---

## Notes

- **Low data confidence**: set `low_data_confidence: true` in JSON when `ai_task_coverage_pct < 20%`. The site should display a caveat for these occupations.
- **Null AEI metrics**: 343 occupations have no AEI coverage at all (not in O*NET v30.2 task match). Their AEI fields will be null in both CSV and JSON.
- **A-scores source**: parsed from `data/output/score_log.txt` during Phase 5 JSON generation. Not currently in the scored CSV.
- **task_weight fallback**: 845 tasks across 86 occupations had no Task Ratings in O*NET v30.2. These use occupation mean weight (global mean 16.97 for fully-unrated occupations). Tracked via `weight_source = mean_fallback`.
