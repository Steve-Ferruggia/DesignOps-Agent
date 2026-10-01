# DesignOps Triage Agent

An AI agent that takes an inbound design support request from raw intake text to
a ready-for-assignment **Design Support Brief** — complete with a complexity
classification, effort estimate, designer match, and a clear
`APPROVED FOR ASSIGNMENT | NEEDS INFO | ON HOLD` gate decision.

Built as a submission for the Pindrop PM AI Enablement take-home project.

---

## The Problem

The CIO Design team runs a **Short-term Design Support** process (BPMN diagram attached)
where product teams request UX, Visual Design, or UX Research support. Intake is
unstructured — requests arrive as Jira tickets, emails, or Mural comments with varying
levels of detail. An **Iteration Manager** then manually:

1. Reads the request and fills in missing fields
2. Judges complexity and estimates effort
3. Checks designer availability in a staffing spreadsheet
4. Writes a brief for the Craft Lead and designer
5. Routes to an approval gate

This manual triage takes hours per request and the quality of briefs varies by person.
The staffing spreadsheet (tracked in an Excel workbook across 6 sheets and 12 designers)
has no memory of past patterns — every triage starts from scratch.

**Average days to staff** across the historical backlog ranged from 1 day (quick-turn VD)
to 46+ days (complex embedded UXR). The agent targets the 80% of requests in the 1–15
day range where the intake-to-brief step is the bottleneck.

---

## What the Agent Does

```
[Raw request text]
        │
        ▼
 ┌─────────────────────┐
 │  extract_requirements│  ← Skill: parse fields, flag missing info
 └─────────────────────┘
        │ structured JSON
        ▼
 ┌─────────────────────┐
 │  classify_complexity │  ← Skill: Low/Medium/High + effort estimate
 └─────────────────────┘    (reads domain history from memory)
        │ classification JSON
        ▼
 ┌─────────────────────┐
 │   match_designer     │  ← Deterministic: filter + score roster
 └─────────────────────┘    (reads designer_roster.json from memory)
        │ designer match
        ▼
 ┌─────────────────────┐
 │   generate_brief     │  ← Skill: Markdown artifact with gate decision
 └─────────────────────┘
        │
        ▼
 [outputs/<jira_key>_brief.md]
        │
        ▼
 ┌─────────────────────┐
 │   update_memory      │  ← Append to request history, update roster load
 └─────────────────────┘
```

**Human gate:** The Iteration Manager reviews the brief and makes the final
assignment call. The agent recommends — the human decides.

---

## Repository Structure

```
designops-triage-agent/
├── run.py                        # Main orchestrator — entry point
├── requirements.txt
│
├── agent/
│   └── agent_instructions.md     # Agent identity, workflow, matching rules, boundaries
│
├── skills/
│   ├── extract_requirements.md   # Skill: parse raw request → structured JSON
│   ├── classify_complexity.md    # Skill: complexity tier + effort estimate → JSON
│   └── generate_brief.md         # Skill: synthesize → Markdown brief
│
├── memory/
│   ├── designer_roster.json      # 12 designers: skills, load, availability, domains
│   ├── request_history.json      # 9 past requests + domain patterns
│   └── agent_memory.json         # Run log + schema documentation
│
├── inputs/
│   ├── request_1_low_complexity.txt      # 1-day VD request, urgent deadline
│   ├── request_2_medium_complexity.txt   # 3-month 50% UX embed
│   └── request_3_edge_case_not_ready.txt # VD request, team not ready
│
└── outputs/
    └── .gitkeep                  # Generated briefs written here at runtime
```

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/Steve-Ferruggia/DesignOps-Agent.git
cd DesignOps-Agent

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your OpenAI API key
echo "OPENAI_API_KEY=sk-..." > .env

# 5. (Optional) Override model
echo "OPENAI_MODEL=gpt-4o" >> .env
```

---

## Running the Agent

```bash
# Run on a specific request file
python run.py inputs/request_1_low_complexity.txt

# Run on inline text
python run.py --input "We need a VD for a 1-day infographic update. Domain: South. Jira: CD-99999."

# Run all three demo inputs sequentially
python run.py --demo
```

The brief is written to `outputs/<jira_key>_brief.md`. Console output shows:
- Extracted fields and any missing information
- Complexity tier, effort estimate, and risk flags
- Recommended designer and match confidence
- Gate decision

---

## Reusable Skills

Each skill is defined in `skills/` as a Markdown instruction file with YAML frontmatter.
They can be invoked independently in any workflow that needs the same capability.

| Skill | Input | Output | Reuse potential |
|---|---|---|---|
| `extract_requirements` | Raw text | Structured JSON | Any intake: vendor requests, onboarding forms, support tickets |
| `classify_complexity` | Structured request + domain history | Complexity tier + effort JSON | Any triage or capacity planning workflow |
| `generate_brief` | Requirements + classification + designer match | Markdown artifact | Any workflow that needs a decision-ready handoff document |

### How skills are invoked

In `run.py`, each skill is loaded from its `.md` file and passed as a system prompt
to the LLM, with the structured input as the user message. This keeps skill logic
declarative and editable without touching Python code.

```python
skill_text = load_text(SKILLS_DIR / "extract_requirements.md")
result = chat(system=skill_text, user=raw_request, json_mode=True)
```

To reuse `extract_requirements` in a different workflow (e.g., enterprise onboarding):
1. Copy or reference `skills/extract_requirements.md`
2. Call `chat(system=skill_text, user=your_input, json_mode=True)`
3. The output schema is identical regardless of domain

---

## Memory and Context

The agent uses three JSON files as a lightweight store:

### `memory/designer_roster.json`
- 12 designers with: skills, level, domains, embed eligibility,
  current load %, weekly availability (next 4 weeks), active and past assignments
- **Read** at the start of every run for matching
- **Updated** after a low/medium complexity APPROVED run: increments `current_load_pct`
  and decrements week-1 availability

### `memory/request_history.json`
- 9 seed requests from the real staffing backlog (anonymized/polished)
- Domain patterns: typical skillsets, embed expectations, avg days to staff
- **Read** during complexity classification: domain history changes the complexity
  score and surfaces risk flags (e.g., `long_wait_pattern` for Baroni domain)
- **Updated** after every run: appends the new request with `outcome: "pending"`

### `memory/agent_memory.json`
- Run log: every execution recorded with timestamp, gate decision, brief path,
  recommended designer ID
- **How memory changes results:** If Baroni domain has `avg_days_to_staff: 18`,
  the classify skill surfaces `long_wait_pattern` risk flag → brief includes
  a specific action item for the Iteration Manager. A fresh run without history
  would classify the same request as Medium with no flags.

---

## Architecture

```
run.py (orchestrator)
  │
  ├── skills/extract_requirements.md  → LLM call (JSON mode)
  ├── skills/classify_complexity.md   → LLM call (JSON mode)
  ├── matching logic (pure Python)    → deterministic filter + score
  ├── skills/generate_brief.md        → LLM call (Markdown)
  │
  ├── memory/designer_roster.json     → read + write
  ├── memory/request_history.json     → read + write
  └── memory/agent_memory.json        → write (run log)
```

**LLM calls per run:** 3 (extract → classify → brief). Matching is deterministic Python.

**Model:** GPT-4o via OpenAI API. Temperature 0.2 for consistency.

**Tools used:** Python 3.11+, OpenAI Python SDK, python-dotenv. No frameworks, no vector DB,
no external services. Everything runs locally from a single `python run.py` command.

**What I reused vs. built:**
- Reused: OpenAI SDK, python-dotenv
- Built: orchestration logic, all three skill prompts, matching algorithm,
  memory update logic, data model, sample inputs
- Data: mock roster and request history derived from the real CIO Design staffing
  backlog Excel file (anonymized and extended)

---

## Key Tradeoffs

| Decision | Rationale |
|---|---|
| Skills as Markdown files, not Python classes | Editable by non-engineers; easy to version and review; LLM prompt is the skill |
| Matching is deterministic Python, not LLM | Availability math should not hallucinate; deterministic = auditable |
| Flat JSON files, not a database | Sufficient for demo scale; no infrastructure; easy to inspect and edit |
| 3 LLM calls, not 1 | Separation of concerns; each step's output is inspectable and reusable |
| GPT-4o at temp 0.2 | Consistent JSON extraction; lower temp = fewer schema violations |
| Human gate always required for High + embed | Agent recommends; human decides; builds trust before expanding autonomy |

---

## Iterations and Obstacles

1. **Excel data extraction** — The staffing backlog has 6 sheets, merged headers,
   and data starting at row 9 (not row 1). Used OfficeCLI dump + custom Node.js
   scripts to extract real field names, designer names, request types, and domain patterns.

2. **Skill granularity** — Initially designed one combined "triage" skill.
   Split into three after recognizing that a single prompt doing extract + classify + match
   was hard to test and the JSON schemas were conflicting.

3. **Matching algorithm** — First attempt used LLM for matching. Replaced with
   deterministic Python scoring after the LLM invented availability numbers. Trust
   but verify: LLM for language tasks, Python for arithmetic.

4. **Memory update timing** — Originally updated memory before generating the brief.
   Moved to after brief generation so a crash mid-brief doesn't corrupt the roster.

---

## Time Spent

| Activity | Time |
|---|---|
| Reading brief, analyzing BPMN diagram, extracting Excel data | 1.5 hours |
| Designing data model (roster, history, memory schema) | 1 hour |
| Writing skill prompts (3 iterations each) | 2 hours |
| Writing orchestrator + matching logic | 2 hours |
| Writing README, evaluation doc, sample outputs | 1.5 hours |
| **Total** | **~8 hours** |

---

## Measuring Success

| Metric | Target | How to measure |
|---|---|---|
| Time to brief | < 2 min vs. est. 30–60 min manual | Stopwatch on demo run |
| Field extraction accuracy | ≥ 90% on 10 known requests | Compare to ground truth from Excel |
| Designer match quality | Iteration Manager accepts rec ≥ 70% of the time | Tracked in run log `outcome` field |
| Missing field detection | Catches all blanks from known incomplete requests | Evaluate on request_3 edge case |
| Gate decision accuracy | ≤ 1 incorrect gate per 10 runs | Manual review of gate vs. actual IM decision |

See `EVALUATION.md` for observed results, edge cases, and known limitations.
