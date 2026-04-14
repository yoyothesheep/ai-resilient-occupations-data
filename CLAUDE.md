# AI-Resilient Occupations Data

Scoring framework for AI job resilience across 1,000+ O*NET occupations. Site: ai-proof-careers.com

## Project Structure

This repo is the **data pipeline**. The end product is the site at `../ai-resilient-occupations-site` (Next.js). Data flows one way: pipeline → site data files. Never edit site data files by hand when the root cause is in the pipeline.

```
ai-resilient-occupations-data/   ← you are here (pipeline + scores)
ai-resilient-occupations-site/   ← Next.js site (../ai-resilient-occupations-site)
```

### Full Pipeline (data → site)

**Full reference: `docs/pipeline.md`**

Two tracks:

**Track A — Baseline (run on O*NET/BLS/AEI updates):**
```bash
source venv/bin/activate
python3 scripts/enrich_onet.py        # Stage 1: enrich
python3 scripts/score_occupations.py  # Stage 2: score
python3 scripts/build_task_table.py   # Stage 3: AEI task table (can run after Stage 1)
python3 scripts/test_scoring.py       # Quick test with 3 occupations
```

**Track B — Career page enrichment (per-cluster, on demand):**
```bash
# Stage 4: Use .claude/skills/career-clusters skill to populate cluster files first, then:
# Stage 5: Generate emerging roles
python3 scripts/generate_emerging_roles.py --cluster <id>
# Stage 6: Generate emerging job title aliases
python3 scripts/generate_emerging_job_titles.py --cluster <id>
# Stage 7a: Generate occupation cards (reads emergingTitles from scores CSV)
python3 scripts/generate_next_steps.py --cluster <id> --api
# To patch only risks/opps: python3 scripts/generate_next_steps.py --cluster <id> --section risks,opportunities --api
# To recompute tasks:        python3 scripts/generate_next_steps.py --cluster <id> --section tasks
# Stage 7b: Generate adjacent/lateral roles + merge into cards (--print-prompts for no-API-key mode)
for code in <code1> <code2> ...; do python3 scripts/adjacent_roles.py --code $code --print-prompts --skip-existing; done
# Stage 7c: Merge emerging roles into cards
python3 scripts/generate_emerging_roles.py --cluster <id>
# Stage 8: Generate career + industry pages in site repo
python3 scripts/generate_career_pages.py --cluster <id>
python3 scripts/generate_industry_page.py --cluster <id>
```

Requires `ANTHROPIC_API_KEY` env var.

**Occupation cards** (`data/output/occupation_cards.jsonl`) are the bridge between pipeline and site. Each `.tsx` career page in the site embeds data from the corresponding card.

## Key Files

- `data/input/` — raw O*NET + BLS source files
- `data/intermediate/All_Occupations_ONET_enriched.csv` — enriched input for scoring
- `data/output/ai_resilience_scores.csv` — final scored dataset (all occupations)
- `data/output/occupation_cards.jsonl` — per-occupation career page data
- `data/emerging_roles/emerging_roles.csv` — AI-era career pivot roles (single source of truth)
- `data/career_clusters/` — career ladder topology (clusters, roles, branches)
- `data/top_no_degree_careers/` — curated subset: top careers requiring ≤ associate's degree
- `docs/scoring-framework.md` — full scoring methodology and rubrics
- `docs/pipeline.md` — full pipeline reference

## Scoring Summary

- **10 attributes**: A1–A8 defensive (65%), A9–A10 offensive (35%)
- **`role_resilience_score`**: 1.0–5.0
- **`final_ranking`**: 0.0–1.0 composite (score 50% + growth 30% + openings 20%)
- Special rules: ceiling cap at 2.5 if A1+A3+A4 all ≤ 2; floor at 3.0 if A9 or A10 = 5

See `docs/scoring-framework.md` for full rubric.

## Updating Source Data

See `docs/pipeline.md` — "Source Data Updates" section for full instructions on updating O*NET, BLS, and AEI data.

## Career Page Data Format

Career pages live in `../ai-resilient-occupations-site`. Use the `aeo-content-writer` skill in that repo to generate them.

**Full spec** (CareerData fields, source conventions, meta title/description templates, risks/opportunities rules, two-file requirement) is in `../ai-resilient-occupations-site/.claude/skills/aeo-content-writer/SKILL.md`.

**Before generating a career page**, run Track B pipeline for the occupation first:
1. Check cluster exists: `grep "<CODE>" data/career_clusters/cluster_roles.csv` — if missing, use `career-clusters` skill
2. Run `generate_next_steps.py --code <CODE>` to populate `occupation_cards.jsonl`
3. Run `adjacent_roles.py --code <CODE>` to add `careerCluster`
4. Run `generate_emerging_roles.py --code <CODE>` to add `emergingCareers`
5. Switch to site repo → run `aeo-content-writer` skill → run `publish-checklist` skill

---

## Working Principles

- **Always make fixes generalizable.** When fixing a data or formatting issue for one occupation, fix it in the script so it applies to all. Never patch individual records manually when the root cause is in the pipeline.
- **`docs/pipeline.md` is the source of truth for the pipeline.** When any script's interface changes (flags, order, new script), update `pipeline.md` first, then sync the Track B bash block in `CLAUDE.md` and the bash commands in `CLUSTER_EXPANSION_TRACKER.md`.

## generate_next_steps.py Workflow

`generate_next_steps.py` is interactive: it prints a prompt and reads JSON from stdin. When running it, **paste the prompt output directly into this Claude Code conversation and respond with JSON here**. Do not launch a separate Claude.ai tab or spawn an API agent. Claude Code IS Claude — respond to the prompt inline, write the JSON to `data/output/occupation_cards.jsonl` directly.

## Top No-Degree Careers Sub-Dataset

Subset filtered to `role_resilience_score ≥ 5.5` and `Top Education Level ≤ associate's`.

- Base: `data/top_no_degree_careers/ai_resilience_scores-associates-5.5.csv`
- Enriched: `data/top_no_degree_careers/ai_resilience_scores-associates-5.5-enriched.csv`
- Schema + methodology: `data/top_no_degree_careers/ENRICHMENT_INSTRUCTIONS.md`

## Third-Party Integrations (Site)

- **Tally feedback form** — form ID `b58kG2`. Embedded as a popup via `https://tally.so/widgets/embed.js` (loaded in `app/layout.tsx`). Triggered on career pages via `data-tally-open="b58kG2" data-tally-width="400"` on the feedback button in `CareerDetailPage.tsx` (between career map and sources).
- **Beehiiv email collection** — embed script loaded in `app/layout.tsx` via `https://subscribe-forms.beehiiv.com/embed.js`.
