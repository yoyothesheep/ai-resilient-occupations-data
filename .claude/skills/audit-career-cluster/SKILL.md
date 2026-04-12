---
name: audit-career-cluster
description: Audit and visualize a career cluster's roles and transitions. Generates an ASCII tree diagram and level summary table, appends to CAREER_CLUSTERS_AUDIT.md, and runs referential integrity checks.
---

# Audit Career Cluster Skill

Generates a visual audit of a career cluster and appends it to `data/career_clusters/CAREER_CLUSTERS_AUDIT.md`.

## Input

Cluster ID (e.g., `marketing`, `finance`, `design`). Must already exist in `clusters.csv`, `cluster_roles.csv`, and `cluster_branches.csv`.

## Step 1 — Gather Data

Read these files and filter to the target cluster:

```bash
python3 -c "
import csv

CLUSTER = '<cluster_id>'

# Cluster metadata
with open('data/career_clusters/clusters.csv') as f:
    cluster = [r for r in csv.DictReader(f) if r['cluster_id'] == CLUSTER][0]

# Roles in this cluster
with open('data/career_clusters/cluster_roles.csv') as f:
    roles = [r for r in csv.DictReader(f) if r['cluster_id'] == CLUSTER]
    roles.sort(key=lambda r: (int(r['level']), r['onet_code']))

# Branches where from_onet_code is in this cluster's roles
role_codes = {r['onet_code'] for r in roles}
with open('data/career_clusters/cluster_branches.csv') as f:
    branches = [b for b in csv.DictReader(f) if b['from_onet_code'] in role_codes]

print(f'Cluster: {cluster[\"cluster_name\"]} ({CLUSTER})')
print(f'Entry: {cluster[\"entry_occupation\"]} ({cluster[\"entry_onet_code\"]})')
print(f'Roles: {len(roles)}, Branches: {len(branches)}')
print()
for r in roles:
    print(f'  L{r[\"level\"]} {\"★\" if r[\"is_canonical\"]==\"true\" else \" \"} {r[\"onet_code\"]} {r[\"occupation\"]} — {r[\"notes\"]}')
print()
for b in branches:
    print(f'  {b[\"from_onet_code\"]} → {b[\"to_onet_code\"]} ({b[\"transition_type\"]}) {\"PRIMARY\" if b[\"is_primary_path\"]==\"true\" else \"\"} | {b[\"notes\"][:80]}')
"
```

## Step 2 — Build ASCII Tree

Create an ASCII tree diagram following this format from existing audits:

```
[L1] Role Name                        XX-XXXX.XX  ★ entry
      │
      ├──→ [L2] Next Role             XX-XXXX.XX  ★ progression | cert name | $cost | duration
      │         │
      │         └──→ [L5] Destination  XX-XXXX.XX  ★ progression | Xyr exp | $cost | duration
      │
      └──→ [L3] Branch Role           XX-XXXX.XX  lateral | description | $cost | duration
```

Rules:
- Entry points start at the left margin with `[L1]`
- Alternate entries get their own tree root
- `★` marks canonical roles
- Each edge shows: transition type, key requirement, cost, duration (from branch data)
- Specialization branches and parallel tracks get their own sub-trees
- Cross-family transitions are noted but not expanded

## Step 3 — Build Level Summary Table

```markdown
| Level | Role | O*NET | Yrs from Entry | Primary Path? |
|-------|------|-------|---------------|---------------|
| 1 | Entry Role | XX-XXXX.XX | 0 | ✓ entry |
| 2 | Mid Role | XX-XXXX.XX | 2 | ✓ canonical |
```

## Step 4 — Build Transition Reference Table

```markdown
| From | To | Type | Primary? | Min Exp | Cost | Duration | Work During? |
|------|----|------|----------|---------|------|----------|--------------|
| Entry → | Mid | progression | ✓ | 2yr | $1.5k | 6mo | ✓ |
```

## Step 5 — Append to CAREER_CLUSTERS_AUDIT.md

Add a new section under the appropriate domain heading (`## Healthcare`, `## Public Safety`, `## Business`, etc.). Format:

```markdown
### Cluster Display Name (`cluster_id`)

**Entry:** Entry Occupation (code) — education | $wage/yr

[ASCII tree from Step 2]

**Level summary:**

[Table from Step 3]

**Transition reference:**

[Table from Step 4]
```

If the domain heading doesn't exist yet, create it.

## Step 6 — Run Integrity Check

Run the verify script to confirm no referential integrity errors:

```bash
python3 -c "
import csv

clusters = {r['cluster_id'] for r in csv.DictReader(open('data/career_clusters/clusters.csv'))}
roles = list(csv.DictReader(open('data/career_clusters/cluster_roles.csv')))
branches = list(csv.DictReader(open('data/career_clusters/cluster_branches.csv')))
role_codes = {r['onet_code'] for r in roles}

bad_clusters = [r for r in roles if r['cluster_id'] not in clusters]
if bad_clusters:
    print('BAD cluster_id refs:', [(r['onet_code'], r['cluster_id']) for r in bad_clusters])

bad_from = [b for b in branches if b['from_onet_code'] not in role_codes]
if bad_from:
    print('BAD from_onet_code:', [b['from_onet_code'] for b in bad_from])

bad_to = [b for b in branches if b['to_onet_code'] not in role_codes and b.get('is_cross_family') != 'true']
if bad_to:
    print('BAD to_onet_code:', [b['to_onet_code'] for b in bad_to])

cross_family = [b for b in branches if b.get('is_cross_family') == 'true']
if not bad_clusters and not bad_from and not bad_to:
    print(f'OK: {len(clusters)} clusters, {len(roles)} roles, {len(branches)} branches ({len(cross_family)} cross-family)')
"
```

Report any errors. If errors are only in OTHER clusters (not the one being audited), note them but don't block.

## Reference

See existing audits in `data/career_clusters/CAREER_CLUSTERS_AUDIT.md` for formatting examples (nursing, law-enforcement, marketing).
