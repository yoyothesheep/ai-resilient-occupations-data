# Career CSV Enrichment Instructions

## Source File
`ai_resilience_scores-associates-5.5.csv` — 77 career rows with columns: Job Zone, Code, Occupation, url, Median Wage, Projected Growth, Employment Change, Projected Job Openings, Top Education Level, Sample Job Titles, Job Description, role_resilience_score, final_ranking, key_drivers

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


### Training Years
Duration of the initial training or school program in years. Use `0` if training is entirely on-the-job (no formal program before earning starts), `0.5` for ~6-month programs, or an integer for multi-year degrees/apprenticeships.

**Choosing the most commonly taken path:** When a career has multiple entry paths, choose the path set by the "Top Education Level" field (e.g., associate's degree vs. certificate, formal program vs. OJT). Note the chosen path in the **10-Year Net Earnings Calculation Model** field.

### Start From The Entry Level Step
**Year 1 is always the entry-level step — never a mid-career salary.** When you see a manager, supervisor, or senior role, do not start Year 1 at that role's salary. Start at the training or junior role that feeds into it. This is the most common mistake LLMs make with this dataset.

For occupations that belong to a clear professional hierarchy where the senior role is almost exclusively a promotion from a specific entry-level role, the 10-year calculation must start from the **absolute entry-level** of that career family, whether it's training or OJT.
- If there's 1 clear path from entry level, use it
- If there's multiple paths but one most commonly taken path, use the most commonly taken (for example Construction starts in a Carpentry apprenticeship)
- If there's multiple paths that are similar in likelihood, use a blended method (for example Food Service Managers can start from Cook, Server, or Host)

#### Canonical Paths 
These are examples of where multiple jobs share a common entry level step. They can be both ladder or linear growth.

**Strictly Applied To:**
- **Police Family:** All roles (Patrol, Supervisor, Detective) start at Year 1 patrol officer academy wage (~$60k).
- **Fire Family:** All roles (Firefighter, Supervisor, Inspector) start at Year 1 firefighter academy wage (~$45k).
- **Construction Family:** Supervisors must start at the trade-apprentice wage (typically Carpentry at ~$34k).
- **Wind Energy Family:** Operations Managers must start at the Year 1 Wind Technician wage (~$45k).
- **Solar Energy Family:** Installation Managers must start at the Year 1 Solar Installer wage (~$38k).
- **Mechanics Family:** Supervisors start at a **blended Year 1 income** ($38k) reflecting entry roles like Lube Tech, Helper, or Apprentice.
- **Food Service Family:** Managers start at a **blended Year 1 income** ($32k) reflecting several entry points (Cook, Server, Host, etc.).

**General Rule:**
All supervisor and manager roles in hierarchical trades or services MUST be modeled with an entry-level training start, even if lateral entry is technically possible. This ensures the 10-year net ROI reflects the reality of the career's full investment.

**Shared-path years must mirror the base role exactly.** For a supervisor/manager whose canonical path starts from a base role (e.g., Fire Supervisor starts as a Firefighter), copy the base role's Yr values year-for-year up to the promotion milestone. Do not diverge upward early — if the Firefighter row shows Yr1=$45k, Yr2=$47.7k, …, Yr7=$55.3k, the Fire Supervisor must use those same values for Yr1–Yr7.


### Training Salary ($)
If the training program or employer pays the trainee/student a wage during training, list that starter annual salary here. For example:
- Year 1 patrol officer academy wage (~$60k).
- Year 1 firefighter academy wage (~$45k).
- Year 1 carpentry apprenticeship wage (~$34k).

If the training is unpaid, set this field to $0.
If the student pays tuition to attend school, this field is $0 and tuition goes in the Training Cost ($) field.

**Fractional training (e.g., `Training Years = 0.5`):** Yr1 is a blend of the training wage and the first earning salary. For example, if academy pays $40k annualized for 6 months and post-academy pay is $60k, set `Training Salary ($) = 40000` and `Yr1 ($) = 50000`. `calc_e10()` computes this blend automatically for `linear` careers; set it manually for `ladder` careers.

### Training Cost ($)
Total out-of-pocket cost to enter the career. Use the most common/affordable pathway:
- Paid apprenticeships/academies: $0
- Certifications only: cost of cert program + exam fees
- Associate degrees: community college tuition (in-state)
- All: any other costs such as tools
- Does NOT include opportunity cost of foregone earnings during training

#### Training Rules
It's possible for a training path to both be paid, and have out-of-pocket costs.
Examples: Electricians, plumbers, HVAC technicians, carpenters, masons, and ironworkers.
Out-of-Pocket Costs: While employers or unions often cover tuition for classroom instruction, apprentices are frequently responsible for buying their own specialized tools (which can be expensive), work boots, and safety gear.

### Yr1 $ through Yr10 $
10 individual columns with the salary used for each year of the 10-year calculation.

- **Training years**: Yr1 is ALWAYS the start of the path. For full unpaid training years, set Yr to `0`. For full paid training years, set Yr to the `Training Salary ($)` wage. For example, a 2-year unpaid degree: Yr1=$0, Yr2=$0, Yr3=first-year salary. A 4-year paid carpentry apprenticeship: Yr1–Yr4 each reflect the apprentice step wage.
- **Fractional training**: See `Training Salary ($)` above. `calc_e10()` blends automatically for `linear` careers.
- **Ladder careers**: Manually set each earning year based on step/promotion research. When a promotion has a range of expected timing (e.g., "3–10 years of Patrol work to make Sergeant"), use the midpoint (e.g., Year 6.5 → round to Year 7).
- **Linear careers**: Set the FULL annualized starting salary in the first earning year's Yr column (e.g., `Yr1 ($)` if no training, or `Yr3 ($)` if 2 years of training). `calc_e10()` auto-fills all other Yr values by linear interpolation to the median.

#### General 3% Growth Rule
**In any year where salary growth is not dictated by a published schedule or specific formula, assume a 3% annual increase to match inflation.** This applies specifically to:
- Years spent in a specific role on a ladder before jumping to the next step.
- Years *after* a career has hit the BLS median, up through Year 10.
- Training/developmental phases where specific step increases aren't documented (do NOT assume $10–20K annual jumps during training).

**Big salary jumps should only occur at documented milestone events:**
- Apprentice → Journeyman (trades): typically a 25–35% jump after 4–5 year apprenticeship
- Developmental → Certified (ATC): CPC certification brings significant raise, but developmental phases have incremental checkpoint raises over 2–4 years
- Patrol → Sergeant/Detective (law enforcement): promotion brings ~$10–15K bump after 5–8 years
- Probationary → Sworn (fire/police): modest bump ($2–4K) after 6–12 month probation
- Seniority-based (flight attendants): early years see only 3–6% annual increases; pay curve steepens at year 5+

**Reference pay structures by career type:**
| Career Type | Annual Increase During Training | Milestone Jump | Time to Median (or final jump) |
|---|---|---|---|
| Government step (police, fire) | $2–4K/year (step increases) | $10–15K at promotion | 8–10 years |
| Federal GS scale (CBP) | $6–15K/year (grade promotions GL-5→GS-12) | N/A (grade-based) | 4–5 years to GS-12 (Note: GS-12 far exceeds BLS median! Use the real GS-12 salary, don't artificially cap at median) |
| Trade apprenticeship (electrical, plumbing, HVAC) | 5–10% of journeyman/year | 25–35% at journeyman | 5–7 years |
| FAA ATC (ATSPP pay bands) | $8–17K/year during developmental | $20K at CPC certification | 7–9 years |
| Airline seniority (flight attendants) | $1.5–3K/year early; $4–5K/year mid | None (smooth curve) | 10+ years |

**A Note on the BLS Median:**
Do not artificially cap ladder careers at the BLS median if the real-world progression pays more. **use the actual higher ladder wage**. If a career reaches the median before Year 10, apply the 3% growth rule for remaining years.
Examples: a known pay ladder (like the federal GS scale or an established union apprentice-to-journeyman timeline) 


### 10-Year Net Earnings ($)
`Sum(Yr1..Yr10) - Training Cost` — computed by `calc_e10()`.

### 10-Year Net Earnings Calculation
The exact year-by-year salary timeline used to compute the 10-Year Net Earnings figure.

- **Salary schedule/ladder careers**: List each year's salary showing the step/promotion that applies. When a promotion has a range of expected timing (e.g., "3–10 years to make Sergeant"), use the midpoint (e.g., Year 6.5 → round to Year 7).
- **Linear growth careers**: State the formula: `(Year1 + Median) / 2 × 10 - Training Cost = result`.


### 10-Year Net Earnings Calculation Model
Always use this exact 2-bullet format:

```
1. [Training label]: [Training description — what it is, duration, who pays, out-of-pocket cost]
2. Earnings trajectory: [Salary progression — how pay grows, key milestones, what drives variation]
```

**Training label** for bullet 1:
- `Paid Training:` — employer/department pays a wage during training (academies, apprenticeships, OJT, internal promotions)
- `Student Pays:` — candidate pays tuition upfront; no income during training (associate degrees, certificate programs)

**Examples:**

`1. Paid Training: FAA Academy in OKC pays a salary during the 2–5 months of training, followed by paid OJT at a facility ($0 cost).`
`2. Earnings trajectory: Starts ~$45k at the Academy/developmental phase. Jumps rapidly as trainees certify on sectors. Hits the BLS median ($144,580) around Year 5 upon achieving CPC status at a high-level facility; 3% annual growth thereafter.`

---

`1. Paid Training: Promoted from wind turbine technician roles — mapped from day one of the wind career ($0 cost, 0 unpaid years).`
`2. Earnings trajectory: Starts at entry technician wage (~$45k). Promotion to operations manager occurs around Year 6 (~$121k jump); grows to BLS median ($136,550) with 3% annual growth after.`

---

`1. Student Pays: 2-year CODA-accredited dental hygiene associate degree (~$15K–$30K tuition at community college; 2 years unpaid).`
`2. Earnings trajectory: Entry-level at ~$74K in Year 3. Linear growth to BLS median $94,260 over the remaining 8 years. Private practice settings often pay above median.`

---

`1. Paid Training: On-the-job training — no formal program required in most states, $0 cost, earning from day one.`
`2. Earnings trajectory: Salary grows linearly from ~$42K entry-level to BLS median $47,300 over 10 years.`

### Difficulty Score
`High`, `Medium`, or `Low`

Factors to consider:
- **Training barriers**: Competitiveness of program admission (acceptance rates), length and rigor of training, licensing/certification exam difficulty and pass rates
- Competitiveness of hiring (hiring ratios, selection processes)
- Physical demands and danger
- Lifestyle demands (travel, irregular hours, emotional toll)

### Difficulty Score Explanation
Short explanation of what makes the career easy or hard to enter and stay in. Must address the difficulty of getting accepted into and completing the required training/education. Include specific barriers (program acceptance rates, exam pass rates, age limits, physical requirements, competitive selection processes).

### How to Get There
Step-by-step training pathway with costs at each step. Include:
- Specific program names/types and duration
- Exam names and fees
- Total estimated out-of-pocket cost
- Whether employer/union/government pays for training
- Alternative pathways if they exist (e.g., military route for aircraft mechanics)

**Example (ATC):** "FAA Academy in Oklahoma City: 3–5 months, paid federal employment from day one. After graduating, you're placed at a facility for on-the-job certification — typically 2–4 more years at increasing pay. The federal government covers everything."

### Job Market
Describe prospects for getting and keeping the job:
- BLS projected growth rate
- Number of annual openings (if notable)
- Current supply/demand dynamics (shortages, competition)
- Geographic considerations
- Factors affecting job security

**Example (ATC):** "2,200 openings per year. Rigorous FAA selection with historically high training washout rates; extreme mental demands and ongoing recertification; hard age-31 start cutoff."

### Pension
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
def calc_e10(row: dict) -> dict:
    calc_type = row.get('Calculation Type', 'ladder')
    median = int(row.get('Median Annual Wage ($)', 0))
    training_cost = int(row.get('Training Cost ($)', 0))
    training_yrs = float(str(row.get('Training Years', '0') or '0'))
    paid_rate = int(float(str(row.get('Training Salary ($)', '0') or '0')))

    if calc_type == 'linear':
        full_training = int(training_yrs)
        frac_training = training_yrs - full_training
        start_year = full_training + 1  # first full earning year

        start_salary_str = row.get(f'Yr{start_year} ($)', '0')
        start_salary = int(float(start_salary_str.replace(',', ''))) if start_salary_str else 0

        # Fill full training years with paid_rate (0 if unpaid)
        for i in range(1, start_year):
            row[f'Yr{i} ($)'] = str(paid_rate)

        # Linear interpolation from start_year to year 10
        years_to_grow = 10 - start_year
        for i in range(start_year, 11):
            val = start_salary + (median - start_salary) * (i - start_year) / years_to_grow if years_to_grow > 0 else start_salary
            if i == start_year and frac_training > 0:
                # Blend: frac_training at paid_rate, remainder at earning rate
                val = paid_rate * frac_training + val * (1 - frac_training)
            row[f'Yr{i} ($)'] = str(round(val))

    yr_vals = [int(float(str(row.get(f'Yr{i+1} ($)', 0)).replace(',', ''))) for i in range(10)]
    total = sum(yr_vals) - training_cost
    row['10-Year Net Earnings ($)'] = str(total)

    if calc_type == 'linear':
        row['10-Year Net Earnings Calculation'] = (
            f'Linear: (${start_salary:,} up to ${median:,}) over {10 - training_yrs:g} yrs − ${training_cost:,} training = ${total:,}'
        )
    else:
        parts = [f'Yr{i+1} ${v:,}' for i, v in enumerate(yr_vals)]
        row['10-Year Net Earnings Calculation'] = (
            ' + '.join(parts) + f' = ${sum(yr_vals):,} − ${training_cost:,} training = ${total:,}'
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
