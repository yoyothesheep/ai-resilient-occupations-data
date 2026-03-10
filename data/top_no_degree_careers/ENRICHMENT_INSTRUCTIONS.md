# Career CSV Enrichment Instructions

## Source File
`ai_resilience_scores-associates-5.5.csv` — 77 career rows with columns: Job Zone, Code, Occupation, url, Median Wage, Projected Growth, Employment Change, Projected Job Openings, Top Education Level, Sample Job Titles, Job Description, ai_proof_score, final_ranking, key_drivers

## Output File
`ai_resilience_scores-associates-5.5-enriched.csv` — same columns plus new columns below.

---

## New Columns — Machine-Readable Inputs

These columns feed the `calc_e10()` Python function.

### Median Annual Wage ($)
Parsed from the original "Median Wage" string (e.g. `"$49.50 hourly, $102,950 annual"` → `102950`). Clean integer, no `$` or commas.

### Calculation Type
`ladder` or `linear`. Determines which formula `calc_e10()` uses.

- **ladder** — government salary schedules, union step increases, trade apprenticeships, or careers with distinct promotion milestones (e.g., police patrol → sergeant, apprentice → journeyman)
- **linear** — careers with gradual, unstructured wage growth over time

### Year 1 Income ($)
First-year earnings in the career pathway (not the median). For careers with paid training (police, fire, ATC, trades apprenticeships), this is academy/apprentice pay. For careers requiring upfront education (dental hygienist, sonographer), this is first-year salary after completing training.

### Unpaid Training Years
Number of full-time, unpaid training/school years before earning begins. Integer (0, 1, or 2).

**Rules:**
- Set Yr1 ($) through Yr(N) ($) = `0` where N = unpaid training years
- Shift all earning years forward by N (e.g., if 2yr school, Yr3 ($) = first-year salary)
- All tuition/program costs go into **Training Cost ($)** — do NOT subtract them from Yr columns
- If training is paid (apprenticeships, academies) or done while working (on-the-job, part-time certs), do NOT set any years to $0

**Choosing the shortest path:** When a career has multiple entry paths (e.g., associate degree vs. certificate, formal program vs. OJT), use the **shortest path to earning** for the Yr columns. Note the chosen path in the **10-Year Net Earnings Calculation Model** field. Examples:
- Dental Assistants: OJT available in many states → 0 unpaid years (not 1yr for the certificate program)
- Forensic Science Techs: certificate path (6–12 mo) → 1 unpaid year (not 2yr for the associate)
- Computer Systems Analysts: start in IT support with certs → 0 unpaid years (not 2yr for the associate)

### Training Cost ($)
Total out-of-pocket cost to enter the career. Use the most common/affordable pathway:
- Paid apprenticeships/academies: $0
- Certifications only: cost of cert program + exam fees
- Associate degrees: community college tuition (in-state)
- Does NOT include opportunity cost of foregone earnings during training

### Yr1 $ through Yr10 $
10 individual columns with the salary used for each year of the 10-year calculation.

- **Unpaid training years**: Set to `0` for any years spent in full-time unpaid school/training. Earning years shift forward accordingly. For example, a 2-year associate degree career: Yr1=$0, Yr2=$0, Yr3=first-year salary, Yr4–Yr10=subsequent years.
- **Ladder careers**: Manually set each earning year based on step/promotion research. When a promotion has a range of expected timing (e.g., "3–10 years to make Sergeant"), use the midpoint (e.g., Year 6.5 → round to Year 7).
- **Linear careers**: Earning years auto-filled by `calc_e10()` using linear interpolation from Year 1 Income to Median Annual Wage (same progression rate, just starting later).

#### Ladder Career Salary Realism Rules

**During training/academy/apprenticeship/developmental phases**, annual increases should be modest (3–8% or $2–5K/year) unless documented step increases are larger. Do NOT assume $10–20K annual jumps during training periods.

**Big salary jumps should only occur at documented milestone events:**
- Apprentice → Journeyman (trades): typically a 25–35% jump after 4–5 year apprenticeship
- Developmental → Certified (ATC): CPC certification brings significant raise, but developmental phases have incremental checkpoint raises over 2–4 years
- Patrol → Sergeant/Detective (law enforcement): promotion brings ~$10–15K bump after 5–8 years
- Probationary → Sworn (fire/police): modest bump ($2–4K) after 6–12 month probation
- Seniority-based (flight attendants): early years see only 3–6% annual increases; pay curve steepens at year 5+

**Reference pay structures by career type:**
| Career Type | Annual Increase During Training | Milestone Jump | Time to Median |
|---|---|---|---|
| Government step (police, fire, CBP) | $2–4K/year (step increases) | $10–15K at promotion | 8–10 years |
| Federal GS scale (CBP) | $6–8K/year (grade promotions GL-5→GS-12) | N/A (grade-based) | 4–5 years |
| Trade apprenticeship (electrical, plumbing, HVAC) | 5–10% of journeyman/year | 25–35% at journeyman | 5–7 years |
| FAA ATC (ATSPP pay bands) | $8–17K/year during developmental | $20K at CPC certification | 7–9 years |
| Airline seniority (flight attendants) | $1.5–3K/year early; $4–5K/year mid | None (smooth curve) | 10+ years |

### 10-Year Net Earnings ($)
`Sum(Yr1..Yr10) - Training Cost` — computed by `calc_e10()`.

### 10-Year Net Earnings Calculation
The exact year-by-year salary timeline used to compute the 10-Year Net Earnings figure.

- **Salary schedule/ladder careers**: List each year's salary showing the step/promotion that applies. When a promotion has a range of expected timing (e.g., "3–10 years to make Sergeant"), use the midpoint (e.g., Year 6.5 → round to Year 7).
- **Linear growth careers**: State the formula: `(Year1 + Median) / 2 × 10 - Training Cost = result`.

**Example (ATC, ladder):** "Yr1 $47K (academy + AG) → Yr2 $55K (D1) → Yr3 $65K (D2) → Yr4 $78K (D3) → Yr5 $95K (near CPC) → Yr6 $115K (CPC) → Yr7 $130K → Yr8 $140K → Yr9–10 $144,580 × 2 = $1,014,160 − $0 training = $1,014,160"

**Example (Respiratory Therapist, linear):** "($57,000 + $80,450) / 2 × 10 − $18,000 = $669,250"

### 5. 10-Year Net Earnings Calculation Model
Must include **two things**:

1. **Training description**: What the training/education is, how long it takes, approximate cost, and whether it causes $0 earning years. If the career has multiple entry paths and the shorter path was used for the Yr columns, note which path was chosen.
2. **Earnings trajectory**: For salary schedule careers, describe the ladder steps and what impacts salary (e.g., facility level for ATC, certifications for police). For linear careers, note factors that can push above/below the estimate (overtime, specialization, setting).

**Example (ATC):** "FAA Academy in Oklahoma City (3–5 months, paid from day one). 2–4 years developmental training (AG→D1→D2→D3) with incremental checkpoint raises. CPC certification ~Year 5–6 brings major pay jump. Reaches BLS median ($144,580) by Year 9. Level 12 facility CPCs regularly exceed $180K. Highest-ROI career on this list."

**Example (Dental Hygienist, 2yr school):** "2–3 year CODA-accredited dental hygiene associate degree ($15K–$30K) required before earning; 2 years of $0 earnings during school. Linear growth from $65K (entry-level RDH) to BLS median $94,260 over remaining 8 years."

**Example (Dental Assistants, OJT path):** "OJT path: many states allow on-the-job training with no formal program — 0 unpaid years. Salary grows linearly from entry to median over 10 years."

### 6. Difficulty Score
`High`, `Medium`, or `Low`

Factors to consider:
- **Training barriers**: Competitiveness of program admission (acceptance rates), length and rigor of training, licensing/certification exam difficulty and pass rates
- Competitiveness of hiring (hiring ratios, selection processes)
- Physical demands and danger
- Lifestyle demands (travel, irregular hours, emotional toll)

### 7. Difficulty Score Explanation
Short explanation of what makes the career easy or hard to enter and stay in. Must address the difficulty of getting accepted into and completing the required training/education. Include specific barriers (program acceptance rates, exam pass rates, age limits, physical requirements, competitive selection processes).

### 8. How to Get There
Step-by-step training pathway with costs at each step. Include:
- Specific program names/types and duration
- Exam names and fees
- Total estimated out-of-pocket cost
- Whether employer/union/government pays for training
- Alternative pathways if they exist (e.g., military route for aircraft mechanics)

**Example (ATC):** "FAA Academy in Oklahoma City: 3–5 months, paid federal employment from day one. After graduating, you're placed at a facility for on-the-job certification — typically 2–4 more years at increasing pay. The federal government covers everything."

### 9. Job Market
Describe prospects for getting and keeping the job:
- BLS projected growth rate
- Number of annual openings (if notable)
- Current supply/demand dynamics (shortages, competition)
- Geographic considerations
- Factors affecting job security

**Example (ATC):** "2,200 openings per year. Rigorous FAA selection with historically high training washout rates; extreme mental demands and ongoing recertification; hard age-31 start cutoff."

### 10. Pension
Describe retirement benefits if the job has a pension. Include:
- Type (defined-benefit, defined-contribution)
- Eligibility (years of service, age)
- Which employer types offer pensions vs. 401(k) only
- Union pension funds if applicable

**Example (Police Supervisor):** "Defined-benefit pension after 20 years — many departments allow retirement at 50."

If no pension is typical, say so and note what retirement options exist (401k, self-funded).

---

## calc_e10() Python Function

```python
def calc_e10(row):
    """
    Calculate 10-Year Net Earnings from CSV row dict.

    Inputs read from row:
      - 'Calculation Type': 'ladder' or 'linear'
      - 'Year 1 Income ($)': int
      - 'Training Cost ($)': int
      - 'Median Annual Wage ($)': int (parsed from 'Median Wage')
      - 'Yr1 ($)' .. 'Yr10 ($)': int (ladder: manually set; linear: auto-filled)

    For linear careers, auto-fills Yr1–Yr10 via interpolation before summing.
    Returns: updated row with Yr1–Yr10, 10-Year Net Earnings, and Calculation string.
    """
    yr1 = int(row['Year 1 Income ($)'])
    median = int(row['Median Annual Wage ($)'])
    training = int(row['Training Cost ($)'])
    calc_type = row['Calculation Type']

    if calc_type == 'linear':
        for i in range(10):
            row[f'Yr{i+1} ($)'] = str(round(yr1 + (median - yr1) * i / 9))

    yr_vals = [int(row[f'Yr{i+1} ($)']) for i in range(10)]
    total = sum(yr_vals) - training
    row['10-Year Net Earnings ($)'] = str(total)

    if calc_type == 'linear':
        row['10-Year Net Earnings Calculation'] = (
            f'Linear: (${yr1:,} + ${median:,}) / 2 × 10 − ${training:,} = ${total:,}'
        )
    else:
        parts = [f'Yr{i+1} ${v:,}' for i, v in enumerate(yr_vals)]
        row['10-Year Net Earnings Calculation'] = (
            ' + '.join(parts) + f' = ${sum(yr_vals):,} − ${training:,} training = ${total:,}'
        )
    return row
```

### Invariant
`10-Year Net Earnings ($)` must always equal `sum(Yr1..Yr10) - Training Cost`. The function enforces this.

### When to use each type
| Type | When | Yr1–Yr10 set by |
|------|------|-----------------|
| `ladder` | Government pay scales, union step increases, trade apprenticeships, distinct promotion milestones | Human (manual research) |
| `linear` | Gradual unstructured wage growth | `calc_e10()` auto-interpolation |

---

## Research Process (per row)

1. **Web search** the career's training pathway, entry-level salary, and pay progression
2. **Determine calculation model**: salary ladder (government/union/trades) vs. linear growth
3. **Calculate 10-year net earnings** using the appropriate model
4. **Assess difficulty** based on entry barriers, training rigor, and working conditions
5. **Write all 10 fields** with specific, factual details (exam names, program costs, certification acronyms)

## Key Principles
- Use real credential names (NBCOT, ARDMS, NREMT, ASE, NABCEP, etc.)
- Include specific exam fees and program cost ranges
- Note union vs. non-union pathways where applicable
- Mention military-to-civilian pipelines where relevant
- For salary schedules, cite the actual step names (GS-5, Step 1, Journeyman, etc.)
- Overtime, shift differentials, and tips are mentioned but NOT included in the base calculation
