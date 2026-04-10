# Test Plan

Status: **Not yet implemented.** This plan covers unit, integration, E2E, and automated E2E testing for the data pipeline and site.

---

## 1. Unit Tests

### Frontend (Vitest — already configured in site repo)

| Target | Key Cases |
|---|---|
| `getTier()` | All score boundaries: 0, 35, 45, 55, 65, 100 |
| `usageBadge()` | n=null, n<100, n≥100 |
| `getEducationIndex()` | All education level strings |
| `sortCareers()` | asc/desc/immutability (3 exist already) |
| Search filter logic | Empty query, partial match, emerging title match, no results |
| Growth label mapping | `+8%`, `-6%`, `0%`, string fallback |
| `careerPageRegistry` | Known slug present, unknown slug absent |

### Python Pipeline (pytest — not yet installed)

| Target | Key Cases |
|---|---|
| `_growth_from_string()` in `score_occupations.py` | Each GROWTH_MAP key + unknown string |
| `career_slug()` in `generate_career_pages.py` | Special chars, `&`, long titles |
| Occupation card structure | Required fields present, salary/openings have no spaces (e.g. `$112,590` not `$112, 590`) |
| `_regenerate_registry()` | Output slugs match `app/career/` dirs |
| Growth label map in `generate_next_steps.py` and `generate_industry_page.py` | Each key maps correctly, fallback to raw string |

---

## 2. Integration Tests

### Frontend (Vitest + React Testing Library)

| Target | Key Cases |
|---|---|
| `useCareerData` hook | CSV loads, parses, caches; `emergingJobTitles` populated from `Emerging Job Titles` column |
| Homepage search | Type "cybersecurity analyst" → surfaces Information Security Analysts via `emergingJobTitles` |
| Homepage filters | Wage/openings/education filters correctly reduce result set |
| Industry page | Level filter shows correct careers; sort by level is descending; sort by resilience is descending |
| Career detail page | All sections render; job titles + emerging titles merged into one list; career map shows "See full career page →" for slugs in registry |
| Tally feedback button | `data-tally-open="b58kG2"` present; `data-page` equals canonical URL |

---

## 3. E2E Tests (Playwright — not yet installed)

| Flow | Steps |
|---|---|
| Search → career page | Search "data scientist" → click result → career page loads with score/salary/growth |
| Wage filter | Set wage $80k → all results have wage ≥ $80k |
| Industry page level filter | `/industry/software-technology` → click "Senior" → only senior roles show |
| Career map link | Open career map node with existing page → "See full career page →" link navigates correctly |
| Feedback button | Click "Give feedback about our data →" → Tally popup opens |
| 404 | `/career/fake-slug` → 404 page |

---

## 4. Automated E2E (CI — not yet set up)

**Stack:** Playwright + GitHub Actions on push to `main`.

```yaml
# .github/workflows/e2e.yml
- Build Next.js (npm run build)
- Start server (next start)
- Run Playwright tests
- Upload screenshots/traces on failure
```

**Smoke suite** (every PR, ~2 min):
- Homepage loads and search works
- One career page renders (`/career/data-scientist`)
- Both industry pages render (`/industry/software-technology`, `/industry/sales-business-development`)

**Full suite** (on merge to main, ~10 min):
- All E2E flows above
- All 27 career page slugs return HTTP 200
- Both industry pages return HTTP 200

---

## Priority Order

1. Unit tests for pure functions: `getTier`, growth mapping, search filter logic
2. Integration test for `emergingJobTitles` search (regression for bug fixed Apr 2026)
3. Playwright install + smoke suite
4. CI pipeline with GitHub Actions
5. Full E2E suite

---

## Notes

- Python pipeline tests need `pytest` added to `venv`
- Playwright needs `npm install -D @playwright/test` + `npx playwright install` in site repo
- `careerPageRegistry.ts` registry-based tests should have a TODO noting they can be removed once all career pages are built (same TODO as in the registry itself)
