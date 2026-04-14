---
name: career-clusters
description: Populate career cluster data files for a new industry group. Use when adding any new cluster to data/career_clusters/.
---

# Career Clusters Skill

Populates the three cluster CSV files for a new industry group.

## Files You Write

All three files live in `data/career_clusters/`:

1. **`clusters.csv`** — one row per cluster (append, don't overwrite)
2. **`cluster_roles.csv`** — one row per occupation in the cluster (append). **Each onet_code must appear in exactly one cluster.** Cross-cluster visibility is handled via `cluster_branches.csv` with `is_cross_family=true`, not by duplicating a role in two clusters.
3. **`cluster_branches.csv`** — one row per from→to transition (append)

Schemas are in `data/career_clusters/CAREER_CLUSTERS_SCHEMA.md`. Read it before proceeding.

---

## Step 1 — Identify Occupations

Run this to get all occupations in the target SOC group with their scores:

```bash
python3 -c "
import csv
with open('data/output/ai_resilience_scores.csv') as f:
    rows = list(csv.DictReader(f))
# Filter by SOC prefix — e.g. '43' for Office/Admin, '41' for Sales, '27' for Arts/Design
prefix = '43'
matches = [(r['Code'], r['Occupation'], r['role_resilience_score'], r['final_ranking'],
            r['Education'], r['Projected Growth'], r['Median Wage'])
           for r in rows if r['Code'].startswith(prefix)]
matches.sort(key=lambda x: float(x[2]) if x[2] else 0)
for m in matches:
    print(m)
"
```

SOC prefixes for the three target clusters:
- **Office & Administrative Support:** `43`
- **Sales & Related:** `41`
- **Arts, Design, Entertainment & Media:** `27`

---

## Step 2 — Group Into Families

Each cluster (`clusters.csv` row) is a career ladder sharing a common entry point. Grouping rules:

1. **SOC prefix** — start with same 2-digit group
2. **Job Zone progression** — entry (JZ1-2) → mid (JZ3) → senior/advanced (JZ4-5)
3. **Naming patterns** — "Clerk → Specialist → Supervisor → Manager" is one family; "Graphic Designer → Art Director" is another
4. **One canonical role per level** — if multiple similar titles exist at the same level (e.g. "Customer Service Representatives" and "Switchboard Operators"), mark the higher-volume one `is_canonical=true`, the rest `false`

For Office/Admin (43-xxxx), expected families include:
- Administrative Support (clerks → secretaries → administrative managers)
- Customer Service (reps → supervisors)
- Financial Clerks (bookkeeping clerks → billing supervisors)
- Information/Records Clerks (data entry → records manager)

For Sales (41-xxxx):
- Retail Sales (cashier → sales associate → department manager → store manager)
- B2B Sales (sales rep → account manager → sales manager)
- Insurance Sales (agent → senior agent → manager)

For Arts/Design (27-xxxx):
- Graphic Design (designer → senior designer → art director → creative director)
- Writing/Editorial (writer → editor → managing editor)
- Media/Broadcasting (camera operator → producer → director)

---

## Step 3 — Write clusters.csv

Append rows. Fields:

| Field | Notes |
|---|---|
| `cluster_id` | Kebab-case slug, e.g. `office-admin`, `retail-sales`, `graphic-design` |
| `cluster_name` | Display name, e.g. `Office Administration` |
| `domain` | One of: `Business`, `Sales`, `Creative`, `Technology`, `Healthcare`, `Public Safety`, `Transportation`, `Trades` |
| `entry_onet_code` | O*NET code of the true starting role (lowest Job Zone in family) |
| `entry_occupation` | Name of that role |
| `entry_education` | Typical entry education from enriched CSV |
| `entry_wage_annual` | Annual median wage (parse from "Median Wage" field, extract numeric) |
| `notes` | 1-2 sentences: what defines this family, any curation decisions worth noting |

---

## Step 4 — Write cluster_roles.csv

One row per occupation. Fields:

| Field | Notes |
|---|---|
| `onet_code` | From scores CSV |
| `occupation` | From scores CSV |
| `cluster_id` | Must match a row in clusters.csv |
| `level` | 1=entry, 2=mid, 3=senior, 4=lead/advanced, 5=executive |
| `is_canonical` | `true` for the primary representative at this level; `false` for specializations/variants |
| `typical_years_from_entry` | 0 for entry, rough estimate for others |
| `notes` | Why non-canonical, or anything unusual |

**Canonical selection rule:** when two roles are at the same level and one has significantly higher openings/median wage, it's canonical. When in doubt, use the broader title.

---

## Step 5 — Write cluster_branches.csv

One row per valid transition. Fields:

| Field | Notes |
|---|---|
| `from_onet_code` | Departing role |
| `to_onet_code` | Destination role |
| `transition_type` | `progression` / `specialization` / `lateral` |
| `is_primary_path` | `true` = most common route; `false` = valid but secondary |
| `is_cross_family` | `true` only if destination is in a different cluster |
| `min_years_experience_before_transition` | 0 if none required |
| `training_cost_usd` | Rough estimate; 0 for on-the-job progressions |
| `training_duration_years` | 0 for progressions with no formal training |
| `can_work_during_training` | `true` for most white-collar progressions |
| `notes` | Source of training cost, or curation reasoning |

**Specialization shortcut:** specializations inherit all outbound transitions from their canonical parent. Only add explicit rows for specialization-specific exceptions.

**Cross-family transitions:** when a role's best next move is in a different cluster (e.g. Data Entry Clerk → Medical Records Technician, or Graphic Designer → UX Designer), add a branch row with `is_cross_family=true`. The destination does not need to exist in `cluster_roles.csv` — the career page resolves it from the main scores data. Use `transition_type=lateral` for peer-level pivots, `progression` if it's a genuine step up.

---

## Step 6 — Verify

After writing all three files, run:

```bash
python3 -c "
import csv

clusters = {r['cluster_id'] for r in csv.DictReader(open('data/career_clusters/clusters.csv'))}
roles = list(csv.DictReader(open('data/career_clusters/cluster_roles.csv')))
branches = list(csv.DictReader(open('data/career_clusters/cluster_branches.csv')))
role_codes = {r['onet_code'] for r in roles}

# each onet_code must appear in exactly one cluster (one career, one cluster — transitions handled via branches)
from collections import defaultdict
code_clusters = defaultdict(list)
for r in roles:
    code_clusters[r['onet_code']].append(r['cluster_id'])
dupes = {code: cls for code, cls in code_clusters.items() if len(cls) > 1}
if dupes:
    print('BAD duplicate onet_codes (must be in exactly one cluster):', dupes)

# cluster_roles must reference valid cluster_ids
bad_clusters = [r for r in roles if r['cluster_id'] not in clusters]
if bad_clusters:
    print('BAD cluster_id refs:', [(r['onet_code'], r['cluster_id']) for r in bad_clusters])

# branch from_onet_code must always be in cluster_roles (you own the source role)
bad_from = [b for b in branches if b['from_onet_code'] not in role_codes]
if bad_from:
    print('BAD from_onet_code (must be in cluster_roles):', [b['from_onet_code'] for b in bad_from])

# branch to_onet_code only needs to be in cluster_roles if is_cross_family != true
bad_to = [b for b in branches if b['to_onet_code'] not in role_codes and b.get('is_cross_family') != 'true']
if bad_to:
    print('BAD to_onet_code (not in cluster_roles and not cross-family):', [b['to_onet_code'] for b in bad_to])

cross_family = [b for b in branches if b.get('is_cross_family') == 'true']
if not dupes and not bad_clusters and not bad_from and not bad_to:
    print(f'OK: {len(clusters)} clusters, {len(roles)} roles, {len(branches)} branches ({len(cross_family)} cross-family) — no ref errors')
"
```

---

## Reference: Existing Clusters

Currently defined in `clusters.csv`:
- `nursing` — Healthcare, entry: Nursing Assistants
- `law-enforcement` — Public Safety, entry: Police Officers
- `transit-police` — Public Safety, entry: Transit Police
- `aviation-operations` — Transportation, entry: Aircraft Service Attendants

Use these as style reference when writing new rows.

---

## Why clusters matter for adjacent_roles.py

`adjacent_roles.py` uses three matching methods in priority order:
1. **Curated cluster data** (best quality) — reads `cluster_roles.csv` + `cluster_branches.csv`. Branch `notes` are injected into the Claude prompt as ground truth for "How to make the move" steps.
2. **Jaccard task overlap** (fallback) — computed from `onet_economic_index_task_table.csv`
3. **SOC prefix similarity** (last resort)

Without a cluster entry, Method 1 produces zero candidates and adjacent roles rely entirely on task overlap and SOC similarity — lower quality, generic steps. Always populate cluster files before running `adjacent_roles.py`.

---

## After This Skill

Once cluster files are written, Track B continues:

```bash
python3 scripts/generate_emerging_roles.py --cluster <cluster_id>
python3 scripts/generate_emerging_job_titles.py
python3 scripts/generate_next_steps.py --cluster <cluster_id>
python3 scripts/adjacent_roles.py --cluster <cluster_id>
```