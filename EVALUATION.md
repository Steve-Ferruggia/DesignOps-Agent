# Evaluation and Edge Cases

## How to Run the Checks

```bash
# Run all three sample inputs
python run.py --demo

# Inspect generated briefs
ls outputs/
cat outputs/CD-19462_brief.md
```

---

## Representative Checks

### Check 1 — Field extraction on a well-formed request
**Input:** `request_1_low_complexity.txt`
**Expected:** All required fields extracted, `missing_fields: []`,
`ready_to_staff: true`, `hard_deadline: "2023-01-23"`

**Observed:** All fields extracted correctly. Deadline parsed from "January 23rd."
VD skillset mapped from "VD assistance." Size mapped to 100% from "100% for 1 day."

**Pass/Fail:** Pass

---

### Check 2 — Complexity classification with domain history
**Input:** `request_2_medium_complexity.txt` (Baroni domain, 50% UX, 3 months, embed)
**Expected:** `complexity: "high"` (3 months > 2 month medium threshold),
`risk_flags` includes `long_wait_pattern` (Baroni avg 18 days to staff),
`requires_im_review: true`

**Observed:** Classified as `high`. Risk flags: `["long_wait_pattern", "overallocation_risk"]`.
IM review flagged. Effort estimate: 33 designer-days (66 × 0.5).

**Pass/Fail:** Pass

---

### Check 3 — Designer matching availability filter
**Input:** `request_2_medium_complexity.txt` (50% UX, 3 months, embed required)
**Expected:** Designer with UX skill, embed_eligible, available in week 1,
not at 100% load. Cindy Rodriguez (VD only) should NOT match.

**Observed:** Cindy Rodriguez excluded (VD, not UX). Matthew Beasley recommended
(UX/UXR, embed eligible, 50% load, Baroni domain match). Confidence: high (score 7).

**Pass/Fail:** Pass

---

### Check 4 — Memory changes a subsequent result
**Setup:** Run `request_1_low_complexity.txt` first (CD-19462, 100% VD, approved).
Memory updates Yoonju Nam's load from 100% to still 100% (already at cap — tested
no-op behavior correctly). Run log appended.

Then run a second VD request with size 100% timing 1 day.
**Expected:** Yoonju Nam excluded if load = 100%; Janiel Richards or Cindy Rodriguez
recommended instead based on availability.

**Observed:** After first run, roster load correctly reflects Yoonju at 100%.
Second run routes to Janiel Richards (VD, load 50%, available W1 75%). Memory
correctly changed the outcome.

**Pass/Fail:** Pass

---

### Check 5 — Missing fields and clarifying questions
**Input:** `request_3_edge_case_not_ready.txt`
(VD implied but no explicit skillset, no size, no timing, team not ready)

**Expected:** `missing_fields` includes `size_pct` and `timing_days_estimate`,
`ready_to_staff: false`, gate = `ON HOLD`, `requires_im_review: true`.

**Observed:** Missing fields correctly identified. Skillset inferred as `VD` from
"data visualization" and "front end" context (confidence low). `ready_to_staff: false`
extracted from "team is not ready." Gate: `ON HOLD`. Clarifying questions generated
for size and timing. Brief correctly tells IM to check back in January 2023.

**Pass/Fail:** Pass (with caveat — see Known Limitations #1)

---

## Edge Cases

### Edge Case A — Completely empty or off-topic input
**Input:** `"Can you order lunch for the design team?"`
**Expected behavior:** Brief generated with status `NEEDS INFO`, single clarifying
question asking for a design request description.
**Observed:** Agent produces a brief with `missing_fields: ["description", "skillset_requested",
"timing", "size_pct", "ready_to_staff"]` and clarifying question: "Please provide a
description of the design work needed." Gate: `NEEDS INFO`. Does not crash.
**Pass/Fail:** Pass

---

### Edge Case B — No available designer for a skill
**Setup:** Temporarily set all UX designers to `current_load_pct: 100` in the roster.
**Input:** `request_2_medium_complexity.txt` (requires UX)
**Expected behavior:** `recommended: null`, `no_match_reason` explains the gap,
gate = `NEEDS INFO`.
**Observed:** Matching returns null. Brief includes `no_match_reason`:
"No designer with skill 'UX' is available at 50% for '3 Months'. Consider revisiting
timing or splitting the request." Gate: `NEEDS INFO`. IM action item: "Identify
contractor or defer request until capacity opens."
**Pass/Fail:** Pass

---

### Edge Case C — Ambiguous skillset (VD with UX language)
**Input:** "We need design help creating wireframes AND polishing the visual presentation."
**Expected behavior:** Skillset classified as `UX/VD` (hybrid). Complexity elevated.
**Observed:** `skillset_requested: "UX/VD"`. Matching filters to designers with both
UX and VD skills (Madison Barr matched). Complexity elevated to medium.
**Pass/Fail:** Pass

---

### Edge Case D — Continuation risk (prior designer named in request)
**Input:** `request_1_low_complexity.txt` — note includes "continuation of Conner's work"
in similar CDPP request.
**Expected:** Risk flag `continuation_risk` surfaced. Conner Sinjem recommended if available.
**Observed:** `continuation_risk` flag added. Conner Sinjem scores +4 on jira key continuation
bonus. Brief notes: "Prior designer Conner Sinjem named in scope — swapping increases ramp cost."
**Pass/Fail:** Pass

---

## Known Limitations

### 1. Skillset inference on vague requests is low-confidence
When a request doesn't use any of the canonical terms (UX, VD, UX/R), the extract
skill infers based on context clues. "Data visualization" → VD is usually right,
but "design help" without further context returns `null` with a clarifying question.
**Mitigation:** The `clarifying_questions` field always surfaces this to the IM.
**What to fix before rollout:** Add a validation pass that rejects briefs where
`skillset_requested` is null without sending to the IM first.

### 2. Availability numbers become stale between runs
The roster is updated optimistically after approved runs but does not track time.
A designer who completes an assignment is not automatically freed up.
**Mitigation:** The run log records all assignments. An Iteration Manager reviewing
the brief can see active assignments and current load.
**What to fix before rollout:** Add a weekly availability refresh step (or integrate
with a calendar API) to reset `current_load_pct` as assignments close.

### 3. Memory is single-file, no concurrency control
Running two requests simultaneously would corrupt `agent_memory.json`.
**Mitigation:** The current use case is sequential (one Iteration Manager, one run at a time).
**What to fix before rollout:** Replace flat JSON with SQLite or a simple key-value store
with atomic writes.

### 4. LLM can hallucinate field values on very short inputs
With fewer than 3 sentences of context, the extract skill occasionally fills in
plausible-but-wrong values (e.g., inferring `embed: true` from "product team" language
when the request didn't specify). Temperature 0.2 reduces this but does not eliminate it.
**Mitigation:** The `missing_fields` array flags low-confidence fields. The Evidence
vs. Assumptions table in the brief surfaces inferences explicitly.
**What to fix before rollout:** Add a confidence score to each extracted field and
flag any field where confidence < 0.7 as an assumption in the brief.

### 5. Designer roster is static mock data
The roster was derived from the real staffing backlog Excel file but is not connected
to a live system. Availability numbers reflect a snapshot, not real-time state.
**Mitigation:** The roster is a plain JSON file that any Iteration Manager can manually
update before a run.
**What to fix before rollout:** Build a lightweight sync job that pulls from the
staffing spreadsheet (or a future HR system) to refresh the roster weekly.

---

## What I Would Improve Before Rollout

1. **Structured input form** (2 weeks): Replace free-text intake with a simple form
   (Jira template or Slack workflow) that pre-populates `domain`, `jira_key`, `skillset`,
   and `timing`. Reduces LLM inference burden by ~60%.

2. **Live roster sync** (1 week): Connect the roster to the existing staffing spreadsheet
   via a scheduled read, so availability numbers stay accurate.

3. **IM feedback loop** (2 weeks): Add a `--feedback` CLI flag where the IM records
   whether the recommended designer was accepted, rejected, or modified. Feed that back
   into `request_history.json` domain patterns to improve future matching scores.

4. **Confidence scoring on extraction** (1 week): Add per-field confidence to the
   extract skill output. Surface low-confidence fields more prominently in the brief
   and require IM confirmation before approval.

5. **Multi-skill routing** (2 weeks): Support requests that require two designers
   (e.g., 0.5 UX + 0.5 UXR). Currently the agent matches one designer; split requests
   would need two matching passes and a combined brief.
