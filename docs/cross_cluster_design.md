# Cross-Cluster Visibility — Design Doc

## Decision

Each role belongs to exactly **one** cluster. Management roles (SOC 11-*) go in their functional cluster (Sales Manager → `sales`, not a generic "management" cluster). Cross-cluster visibility is handled via `cluster_branches.csv` with `is_cross_family=true`.

---

## Changes Overview

| # | File | What | Why |
|---|---|---|---|
| 1 | `adjacent_roles.py` `derive_related_from_cluster` | Add outbound cross-family branch targets | Currently only iterates same-cluster members; cross-family branches are never discovered |
| 2 | `adjacent_roles.py` `derive_related_from_cluster` | Add inbound cross-family branch sources | A role should know who can transition INTO it, not just where it can go |
| 3 | `adjacent_roles.py` level resolution (L625-630) | Use target's own cluster level before Job Zone fallback | Job Zone mapping is lossy (4 levels, no level 5); cluster level is more accurate |
| 4 | `adjacent_roles.py` realistic/aspirational (L558-569) | Use Job Zone jump for cross-family, not cluster level jump | Cluster levels are relative to different ladders; comparing them is meaningless |
| 5 | `generate_career_pages.py` `build_career_cluster` | Add inbound cross-family nodes to career map | Career page should show "roles that commonly transition here" as entry points |
| 6 | `career-clusters` SKILL.md Step 1 | Add SOC 11-* keyword scan | Management roles won't appear in SOC prefix filter |
| 7 | `career-clusters` SKILL.md Step 5 | Add bidirectional note + cross-family emphasis | Document that branches are one-directional by default; bidirectional is rare |

---

## Change 1: Outbound cross-family branches in `derive_related_from_cluster`

**File:** `scripts/adjacent_roles.py`, lines 127-178

**Current behavior:** Iterates `cluster_roles[source_cluster_id]` — only same-cluster roles. Cross-family branch targets in `cluster_branches.csv` are loaded into `branch_index` but never checked because the target code isn't in the same-cluster role list.

**Fix:** After the same-cluster loop, scan `branch_index` for outbound cross-family branches from the source:

```python
    # Same-cluster candidates (existing loop — unchanged)
    for role in cluster:
        # ... existing logic ...

    # Outbound cross-family branches
    for (from_code, to_code), branch in branch_index.items():
        if from_code != source_code:
            continue
        if branch.get("is_cross_family") != "true":
            continue
        if to_code in {c[1] for c in candidates}:
            continue  # already picked up (shouldn't happen, but defensive)
        ranking = float(scores.get(to_code, {}).get("final_ranking", 0) or 0)
        candidates.append((ranking, to_code, branch["transition_type"], branch.get("notes", "")))
```

**Effect:** When processing Ad Sales Agent (41-3011), the cross-family branches to Search Marketing Strategist (13-1161.01) and Ad & Promotions Manager (11-2011.00) now appear as Method 1 candidates. They get full `fit`/`steps` generation via Claude API.

---

## Change 2: Inbound cross-family branches in `derive_related_from_cluster`

**File:** `scripts/adjacent_roles.py`, lines 127-178

**Current behavior:** No inbound lookup. If Police Officer → Probation Officer is a cross-family branch, Probation Officer's career map never shows Police Officer as an entry point.

**Fix:** After outbound cross-family scan, also scan for inbound:

```python
    # Inbound cross-family branches (roles that transition INTO source)
    for (from_code, to_code), branch in branch_index.items():
        if to_code != source_code:
            continue
        if branch.get("is_cross_family") != "true":
            continue
        if from_code in {c[1] for c in candidates}:
            continue
        ranking = float(scores.get(from_code, {}).get("final_ranking", 0) or 0)
        # Inbound = the source is the destination. Relationship from source's perspective:
        # the from_code role feeds into this role.
        candidates.append((ranking, from_code, "entry_from", branch.get("notes", "")))
```

Internal relationship type `entry_from` — means "people commonly enter this role from X." Used only to flag `isEntryPoint: true` on the JSONL node.

**Prompt:** No new prompt needed. The existing `build_prompt` is called with `source_occ=from_role, target_occ=current_role, rel_type=branch["transition_type"]` (lateral/progression from the branch row). The prompt reads "You are helping someone who works as a {from_role} understand how they could move into a {current_role} role" — exactly the right framing for an entry point.

**Downstream impact:**
- `adjacent_roles.py` merge logic (L609-648): `entry_from` nodes get `isAdjacent=true` and `isEntryPoint=true` in the JSONL node.
- Career page rendering: nodes with `isEntryPoint=true` render with a visual indicator (e.g. "Common entry point" badge). This is a site-side change, not pipeline.
- `REL_TYPE_CONTEXT` dict: no new entry needed — the branch's `transition_type` (lateral/progression) is used for the prompt, not `entry_from`.

**JSONL node shape for entry_from:**
```json
{
  "code": "33-3051.00",
  "title": "Police Officer",
  "level": 3,
  "isAdjacent": true,
  "isEntryPoint": true,
  "relationship": "entry_from",
  "fit": "Your patrol experience and investigative skills...",
  "steps": ["...", "..."],
  "salary": "$76,290",
  "openings": "37,500",
  "growth": "+3%"
}
```

---

## Change 3: Cross-cluster level resolution

**File:** `scripts/adjacent_roles.py`, lines 625-630

**Current:**
```python
if in_same_cluster:
    resolved_level = int(target_cluster["level"])
else:
    resolved_level = job_zone_to_level(target_occ_data, code)
```

**Problem:** `job_zone_to_level` maps 5 Job Zones to 4 levels. Level 5 (executive) is never assigned. A JZ3 role always gets level 2, even if its own cluster puts it at level 3.

**Fix:**
```python
if in_same_cluster:
    resolved_level = int(target_cluster["level"])
else:
    # Cross-cluster: use target's own cluster level if it has one
    target_entry = role_index.get(code)
    if target_entry:
        resolved_level = int(target_entry["level"])
    else:
        resolved_level = job_zone_to_level(target_occ_data, code)
```

`role_index` is still `onet_code → single dict` (no multi-cluster change needed), so this is a direct lookup.

---

## Change 4: Realistic/aspirational for cross-family transitions

**File:** `scripts/adjacent_roles.py`, lines 556-574

**Current:** Computes `level_jump = target_cluster_level - source_cluster_level`. For cross-family, these are in different reference frames.

**Fix:** Detect cross-family and use only Job Zone jump:

```python
# Determine if this is a cross-family transition
is_cross_family = branch_index.get((source_code, target_code), {}).get("is_cross_family") == "true"

if is_cross_family:
    # Cross-cluster: cluster levels aren't comparable. Use Job Zone only.
    effective_level_jump = zone_jump
else:
    effective_level_jump = level_jump

if training_duration <= 1.0 and effective_level_jump <= 1 and zone_jump <= 1:
    transition_category = "realistic"
else:
    transition_category = "aspirational"
```

For `entry_from` relationships (inbound), the branch lookup is reversed — `(target_code, source_code)`:

```python
branch_key = (source_code, target_code)
if not branch_index.get(branch_key):
    branch_key = (target_code, source_code)  # inbound cross-family
is_cross_family = branch_index.get(branch_key, {}).get("is_cross_family") == "true"
```

---

## Change 5: Inbound cross-family nodes in `build_career_cluster`

**File:** `scripts/generate_career_pages.py`, lines 259-320

**Current:** Section 2 (lines 292-307) adds adjacent nodes from the JSONL `careerCluster` array — but only those with `fit` data. Inbound cross-family nodes have `isEntryPoint=true` and `fit` data (added by Change 2), so they already flow through.

**However:** The level resolution at line 301 needs the same fix as Change 3:
```python
if adj_level is None and adj_code in cluster_roles:
    adj_level = int(cluster_roles[adj_code]["level"])
```
This is already correct — it uses the target's own cluster level. No change needed here.

**What IS needed:** Pass `isEntryPoint` through to `build_cluster_node` so the TSX can render it. Currently `build_cluster_node` (line 167) doesn't emit `isEntryPoint`.

```python
def build_cluster_node(node: dict, is_current: bool = False, is_emerging: bool = False) -> str:
    # ... existing fields ...
    if node.get("isEntryPoint"):
        parts.append(f'isEntryPoint: true')
```

**Site-side rendering** (out of scope for this doc, but noting the contract):
- `isEntryPoint: true` nodes render with a "Common entry point" indicator
- They appear at the appropriate level in the career map
- They link to their own career page

---

## Change 6: Management role discovery in skill

**File:** `.claude/skills/career-clusters/SKILL.md`, Step 1

Add after the SOC prefix filter block:

```python
# Also scan management roles (SOC 11-*) relevant to this cluster
mgmt_keywords = ['Sales', 'Marketing']  # ← customize per cluster domain
mgmt = [(r['Code'], r['Occupation'], r['role_resilience_score'], r['final_ranking'],
         r['Education'], r['Projected Growth'], r['Median Wage'])
        for r in rows if r['Code'].startswith('11')
        and any(kw.lower() in r['Occupation'].lower() for kw in mgmt_keywords)]
print(f"\n--- Management roles (SOC 11-*) matching {mgmt_keywords} ---")
for m in mgmt:
    print(m)
```

Update the instruction text to say: "Include management roles (SOC 11-*) whose titles match the cluster domain. These go in the functional cluster at level 4 or 5, not in a separate management cluster."

---

## Change 7: Skill documentation updates

**File:** `.claude/skills/career-clusters/SKILL.md`, Step 5

Add to the cross-family section:

> **Directionality:** Each branch row is one-directional (from → to). Bidirectional cross-family transitions (A → B and B → A) are valid but should be extremely rare — most career shifts have a clear "from" and "to" direction. If both directions are genuinely common, add two rows.

> **Entry points:** Cross-family branches where `to_onet_code` is in this cluster represent inbound career paths. These are valuable — they show users "here's where people commonly enter this field from." Always add these when a clear feeder pattern exists (e.g., Patrol Officer → Transit Police, Ad Sales → Marketing).

---

## Files touched summary

| File | Lines changed | Type |
|---|---|---|
| `scripts/adjacent_roles.py` | ~40 lines added/modified in 4 locations | Code |
| `scripts/generate_career_pages.py` | ~5 lines in `build_cluster_node` | Code |
| `.claude/skills/career-clusters/SKILL.md` | Step 1 + Step 5 text | Skill |

No schema changes. No new files. No site-side changes (those are a separate task).

---

## Testing

### Referential integrity (automated)

Run the existing Step 6 verification script after any cluster_roles/cluster_branches edit. No changes needed to the script.

### Golden Dataset 1: Ad Sales Agent (41-3011) — outbound cross-family

Existing cross-family branches:
- `41-3011.00 → 13-1161.01` (Search Marketing Strategist, lateral, cross-family)
- `41-3011.00 → 11-2011.00` (Ad & Promotions Manager, progression, cross-family)

**Pipeline:**
```bash
# 1. Adjacent roles — should now pick up cross-family targets via Method 1
python3 scripts/adjacent_roles.py --code 41-3011.00 --print-prompts

# Verify output includes:
#   Method 1 (cluster): N roles  ← should include 13-1161.01 and 11-2011.00
#   → Search Marketing Strategist (13-1161.01) [lateral]
#   → Ad & Promotions Manager (11-2011.00) [progression]
```

**Check:**
- [ ] Both cross-family targets appear in Method 1 output (not just Methods 2/3)
- [ ] `notes` from cluster_branches.csv appear in the prompt (training guidance)
- [ ] After full run: JSONL card for 41-3011.00 has both targets with `isAdjacent: true`

### Golden Dataset 2: Search Marketing Strategist (13-1161.01) — inbound cross-family

The branch `41-3011.00 → 13-1161.01` means Ad Sales Agent feeds into Search Marketing Strategist.

**Pipeline:**
```bash
python3 scripts/adjacent_roles.py --code 13-1161.01 --print-prompts

# Verify output includes:
#   → Advertising Sales Agents (41-3011.00) [entry_from]
```

**Check:**
- [ ] 41-3011.00 appears as `entry_from` relationship
- [ ] JSONL card for 13-1161.01 has node with `isEntryPoint: true, isAdjacent: true`
- [ ] Level for 41-3011.00 uses its own cluster level (from sales cluster), not Job Zone fallback
- [ ] `fit` text describes "your ad sales background gives you..." (inbound perspective)

### Golden Dataset 3: Police Officer (33-3051) — bidirectional + management

Existing branches:
- `33-3051.00 → 33-3052.00` (Transit Police, lateral, cross-family)
- `33-3051.00 → 21-1092.00` (Probation Officer, lateral, cross-family)

**Pipeline:**
```bash
# From Police Officer: outbound cross-family
python3 scripts/adjacent_roles.py --code 33-3051.00 --print-prompts
# Should include Transit Police + Probation Officer via Method 1

# From Transit Police: inbound cross-family
python3 scripts/adjacent_roles.py --code 33-3052.00 --print-prompts
# Should include Police Officer as entry_from

# From Probation Officer: inbound cross-family
python3 scripts/adjacent_roles.py --code 21-1092.00 --print-prompts
# Should include Police Officer as entry_from
```

**Check:**
- [ ] Police Officer's card shows Transit Police + Probation Officer as outbound adjacents
- [ ] Transit Police's card shows Police Officer as `isEntryPoint: true`
- [ ] Probation Officer's card shows Police Officer as `isEntryPoint: true`
- [ ] Realistic/aspirational classification uses Job Zone jump (not cluster level) for all cross-family pairs

### Golden Dataset 4: Nursing (regression — no cross-family branches)

```bash
# Snapshot
cp data/output/occupation_cards.jsonl /tmp/cards_before.jsonl

# Re-run
python3 scripts/adjacent_roles.py --code 29-1141.00 --print-prompts --skip-existing

# Diff
diff <(grep "29-1141.00" /tmp/cards_before.jsonl) \
     <(grep "29-1141.00" data/output/occupation_cards.jsonl)
# Expected: empty (no change)
```

**Check:**
- [ ] No regression — same candidates, same order
- [ ] Cross-family scan finds nothing (nursing has no cross-family branches)
- [ ] `load_cluster_data()` returns same structure (single dict per code)

### End-to-end: Career page + industry page

After running adjacent_roles for golden datasets 1-3 with `--api` (not `--print-prompts`):

```bash
# Generate career pages
python3 scripts/generate_career_pages.py --code 41-3011.00 --force
python3 scripts/generate_career_pages.py --code 13-1161.01 --force

# Generate industry pages
python3 scripts/generate_industry_page.py --cluster sales --force
```

**Human audit:**
- [ ] Ad Sales Agent career page: career map shows Search Marketing Strategist + Ad & Promotions Manager as adjacent nodes with fit/steps
- [ ] Search Marketing Strategist career page: career map shows Ad Sales Agent as entry point node with fit/steps
- [ ] Sales industry page: lists Ad Sales Agent, links work
- [ ] Dev server (`npm run dev`): navigate to both career pages, verify career map renders correctly, all links resolve
- [ ] Entry point nodes are visually distinguishable from outbound adjacent nodes (site-side, verify after site changes)
