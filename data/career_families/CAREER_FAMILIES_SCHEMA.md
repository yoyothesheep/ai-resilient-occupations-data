# Career Families — Schema Design

## Why This Exists

O*NET occupations aren't flat — they're points on career ladders. Without mapping them:
- E10 ROI calculations treat every occupation as an independent starting point, when careers like CNA → LPN → RN → NP share entry-level training costs
- The UI shows redundant-sounding roles (Critical Care Nurses alongside Registered Nurses) with no explanation of how they relate
- Users can't see what a career path actually looks like over time

## Benefits
- **Unified ROI calculations** — occupations in the same family share entry-level wage and training cost; mid/advanced roles only add delta cost from their branching point
- **Better user explanations** — show the full ladder, not just a single role card
- **Cleaner UI** — suppress non-canonical sub-specialties; surface them as "where this can lead"

---

## Three-File Schema

### 1. `families.csv`
Defines the family as a whole. One row per family.

| Field | Description |
|---|---|
| `family_id` | Slug identifier e.g. `nursing` |
| `family_name` | Display name e.g. `Registered Nursing` |
| `domain` | e.g. `Healthcare`, `Engineering`, `Trades` |
| `entry_onet_code` | O*NET code of the true starting role |
| `entry_occupation` | Name of the entry role |
| `entry_education` | Education required to enter |
| `entry_wage_annual` | BLS annual wage at entry level |
| `notes` | Curation context |

---

### 2. `family_roles.csv`
Defines where each occupation sits on the ladder. One row per occupation.

| Field | Description |
|---|---|
| `onet_code` | O*NET code |
| `occupation` | Name |
| `family_id` | Points to `families.csv` |
| `level` | Numeric: 1, 2, 3, 4, 5 |
| `level_type` | `progression` / `specialization` / `branch` |
| `is_canonical` | Whether to show as a primary card in UI |
| `typical_years_from_entry` | Rough ladder position in years |
| `notes` | Curation context |

Note: `branches_from` was removed from this file — that relationship lives entirely in `family_branches.csv`.

---

### 3. `family_branches.csv`
Defines every valid from→to connection between roles. One row per relationship.

| Field | Description |
|---|---|
| `from_onet_code` | The role you're coming from |
| `to_onet_code` | The role you're going to |
| `transition_type` | `progression` / `specialization` / `lateral` (see below) |
| `is_primary_path` | `true` = most common route; `false` = valid but less typical |
| `is_cross_family` | `true` = destination role belongs to a different family; subtype of `lateral` |
| `min_years_experience_before_transition` | Years in `from` role required before eligible — varies by from+to pair |
| `training_cost_usd` | Tuition + fees for the transition |
| `training_duration_years` | Length of program or certification |
| `can_work_during_training` | `true` = earnings continue during training; `false` = count as lost income |
| `notes` | Curation context |

**Transition types:**
- `progression` — moving up the ladder; includes what might be called "branching" — multiple progression paths out of one role are just multiple rows with the same `from_onet_code`
- `specialization` — same level, narrower focus, no extra cost; specializations **inherit all outbound transitions from their canonical role** automatically — only add explicit rows for specialization-specific exceptions (e.g. Critical Care RN → CRNA)
- `lateral` — peer-level track change requiring new training or certification (Firefighter → Fire Inspector)

**Many-to-many:** A role can have:
- **Multiple `from`** — Nursing Instructors reachable from NP, CNS, or RN
- **Multiple `to`** — RN progresses to NP, Midwife, CNS, Psych NP, CRNA, Instructor

---

## Nursing Example

### Family
```
family_id: nursing
entry: Nursing Assistants (CNA) — certificate, $39k
```

### Ladder
```
Nursing Assistants [L1 · progression]
│
└──► Licensed Practical Nurses [L2 · progression]  ← optional; many skip to RN directly
     │
     └──► Registered Nurses [L3 · progression · canonical]
          ├── Acute Care Nurses [L3 · specialization]
          ├── Critical Care Nurses [L3 · specialization]
          │
          ├──► Nurse Practitioners [L4 · branch]
          ├──► Nurse Midwives [L4 · branch]
          ├──► Clinical Nurse Specialists [L4 · branch]
          ├──► Adv. Practice Psychiatric Nurses [L4 · branch]
          │
          ├──► Nurse Anesthetists [L5 · branch from Critical Care Nurses]
          └──► Nursing Instructors [L5 · branch from NP or CNS or RN]
```

### Key transition notes
- **CRNA** realistically requires Critical Care RN experience — explicit row from Critical Care Nurses (specialization exception); RN → CRNA row exists but `is_primary_path=false`
- **Nursing Instructors** most commonly entered from NP or CNS; RN+Master's possible but rare — three `from` rows with different primary flags
- **LPN** is optional — CNA → RN direct is `is_primary_path=true`; CNA → LPN is `false`
- **Acute Care and Critical Care Nurses** are specializations of RN — they inherit all RN outbound transitions; Critical Care adds one explicit exception (→ CRNA)

---

## Implementation Plan

**Phase 1 — Define families**
Group occupations using: SOC code prefix + Job Zone progression + naming patterns.
Estimated ~150–200 families from 923 occupations.

**Phase 2 — Map roles**
For each occupation assign level, level_type, canonical flag, and years from entry.
The duplicates curation already underway (see `potential_duplicates.md`) is essentially Phase 1 output — "drop" decisions map to `is_canonical=false`.

**Phase 3 — Define branches**
Build `family_branches.csv` with all from→to connections and primary path flags.

**Phase 4 — Propagate to E10 ROI**

| Transition type | ROI implication |
|---|---|
| `progression` | Cumulative shared cost — each level builds on the last |
| `specialization` | Same cost as canonical parent — no additional investment |
| `lateral` | Shared entry cost + smaller delta for additional certification/training |
