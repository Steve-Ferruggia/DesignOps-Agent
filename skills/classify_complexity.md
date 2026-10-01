---
name: classify_complexity
description: >
  Classifies a structured design request as Low, Medium, or High complexity
  and estimates effort in designer-days. Uses scope, skillset, timing,
  embed flag, and domain patterns from memory. Reusable in any triage,
  prioritization, or capacity-planning workflow.
---

# Skill: classify_complexity

## Purpose
Given a structured request object (output of `extract_requirements`) and
optional domain history from memory, assign a complexity tier and an effort
estimate. This drives staffing priority and determines whether an Iteration
Manager review gate is required before assignment.

## Input
A JSON object with at minimum:
- `skillset_requested`
- `size_pct`
- `timing_days_estimate`
- `embed_requested`
- `ready_to_staff`
- `domain` (optional, used to apply historical patterns from memory)

## Output
```json
{
  "complexity": "low | medium | high",
  "complexity_rationale": "One or two sentences explaining the classification",
  "effort_designer_days": <number>,
  "effort_confidence": "high | medium | low",
  "requires_im_review": true | false,
  "priority_flag": "urgent | normal | on_hold",
  "risk_flags": ["list of strings describing specific risks, or empty array"]
}
```

## Classification Rules

### Low complexity
All of the following:
- `timing_days_estimate` ≤ 5 (≤ 1 week)
- `size_pct` ≤ 100% (any allocation is fine for short work)
- `embed_requested` is false
- `skillset_requested` is a single skill (not hybrid)
- No missing required fields in the upstream extract

**Examples:** 1-day VD asset, quick infographic update, single-session review

### Medium complexity
Any one of the following:
- `timing_days_estimate` between 6 and 44 (1 week – 2 months)
- `embed_requested` is true AND `timing_days_estimate` ≤ 44
- Hybrid skillset (`UX/VD`) required
- `size_pct` ≥ 50% for multi-week engagement

**Examples:** 4–6 week UXR survey, 50% UX embed for 1 month, portal redesign phase

### High complexity
Any one of the following:
- `timing_days_estimate` > 44 (more than 2 months)
- `embed_requested` is true AND long duration
- Missing critical fields (`skillset_requested`, `timing_days_estimate`, `ready_to_staff`)
- Prior history shows same domain had long time-to-staff (> 20 days avg)

**Examples:** 3–6 month embedded UX, multi-phase product design, unclear scope

## Effort Estimation

`effort_designer_days` = (`timing_days_estimate` × `size_pct` / 100)

Round to nearest 0.5. Cap at 132 (6 months at 100%).

If `timing_days_estimate` is null, use domain history averages or set
`effort_designer_days` to null and `effort_confidence` to `"low"`.

## Priority Flag Rules

- `"urgent"`: `hard_deadline` is within 5 business days of today, OR
  timing is "1 Day" / "1-2 Days"
- `"on_hold"`: `ready_to_staff` is false
- `"normal"`: everything else

## `requires_im_review` Rules

Set to `true` when:
- complexity is `"high"`
- Any `risk_flags` are present
- `missing_fields` is non-empty (pass-through from extract output)
- `embed_requested` is true

## Risk Flags to Check

- `"scope_not_ready"` — `ready_to_staff` is false or null
- `"missing_skillset"` — `skillset_requested` is null
- `"missing_timing"` — `timing_days_estimate` is null
- `"hard_deadline_risk"` — deadline is within 5 days and no designer is matched yet
- `"continuation_risk"` — domain context mentions a prior designer by name;
  swapping designers mid-project increases ramp cost
- `"long_wait_pattern"` — domain history shows avg_days_to_staff > 20
- `"overallocation_risk"` — size_pct is 100% for duration > 22 days

## Example

Input:
```json
{
  "jira_key": "CD-19193",
  "domain": "Baroni",
  "skillset_requested": "UX/R",
  "size_pct": 50,
  "timing": "2 Months",
  "timing_days_estimate": 44,
  "embed_requested": true,
  "hard_deadline": null,
  "ready_to_staff": true,
  "missing_fields": []
}
```
Domain history: `{ "avg_days_to_staff": 18, "typical_embed": true }`

Output:
```json
{
  "complexity": "medium",
  "complexity_rationale": "50% allocation over 2 months with embed flag; within medium band but close to high threshold. Baroni historically averages 18 days to staff.",
  "effort_designer_days": 22,
  "effort_confidence": "high",
  "requires_im_review": true,
  "priority_flag": "normal",
  "risk_flags": ["long_wait_pattern"]
}
```
