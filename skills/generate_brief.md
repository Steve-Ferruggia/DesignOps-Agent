---
name: generate_brief
description: >
  Produces a structured Design Support Brief — the handoff artifact the
  Iteration Manager and designer both act on. Combines extracted requirements,
  complexity classification, and a recommended designer match into a single
  readable document with a clear APPROVED / NEEDS INFO gate. Reusable in any
  workflow that needs a concise, decision-ready artifact from structured data.
---

# Skill: generate_brief

## Purpose
Synthesize the outputs of `extract_requirements` and `classify_complexity`,
plus a designer match from the roster, into a single Design Support Brief.
The brief is the primary handoff artifact: the Iteration Manager uses it to
approve or send back for clarification; the designer uses it to understand
scope on day one.

## Input
A JSON object with three top-level keys:

```json
{
  "requirements": { /* output of extract_requirements */ },
  "classification": { /* output of classify_complexity */ },
  "designer_match": {
    "recommended": { /* designer object from roster, or null */ },
    "alternatives": [ /* up to 2 alternate designers, or [] */ ],
    "match_rationale": "Why this designer was selected",
    "match_confidence": "high | medium | low",
    "no_match_reason": "null, or reason if recommended is null"
  }
}
```

## Output Format

Produce a Markdown document with the following sections in order.
Do not add sections not listed here. Do not pad with filler text.

---

```markdown
# Design Support Brief — [JIRA_KEY]

**Status:** [APPROVED FOR ASSIGNMENT | NEEDS INFO | ON HOLD]
**Generated:** [ISO timestamp]
**Complexity:** [Low | Medium | High]   **Priority:** [urgent | normal | on_hold]
**Effort Estimate:** [N designer-days]  **Confidence:** [high | medium | low]

---

## Request Summary
[2–3 sentence plain-English description of what is being asked, who is asking,
and what success looks like. Write for a designer who has no prior context.]

## Scope
| Field | Value |
|---|---|
| Domain / Sponsor | [domain] |
| Jira Key | [jira_key] |
| Skillset Required | [skillset_requested] |
| Allocation | [size_pct]% |
| Duration | [timing] |
| Embed with Team | [Yes / No / Unknown] |
| Hard Deadline | [hard_deadline or "None stated"] |
| Ready to Staff | [Yes / No / Unknown] |

## Recommended Designer
**[Designer Name]** ([level], [skills joined with "/"])
- Current load: [current_load_pct]%
- Available next 4 weeks: [available_pct_next_4_weeks as "W1: X% / W2: X% / W3: X% / W4: X%"]
- Domain fit: [domain match explanation]
- Match rationale: [match_rationale]
- Match confidence: [match_confidence]

> **No match found** — [no_match_reason]
(Use the "No match found" block only when recommended is null; otherwise omit it.)

## Alternatives
1. [Alt designer name] — [brief reason]
2. [Alt designer name] — [brief reason]
(Omit this section if alternatives list is empty.)

## Evidence vs. Assumptions
| Type | Item |
|---|---|
| Evidence | [Fact drawn directly from the request text or roster data] |
| Evidence | [...] |
| Assumption | [Inference made where data was missing or ambiguous] |
| Assumption | [...] |

## Open Questions / Risks
[List each risk_flag and missing_field as a bullet. For each, write one actionable
sentence describing what needs to be resolved and by whom.
If none, write "None — request is clear and designer is matched."]

## Recommended Next Steps
1. [First concrete action — who does what by when]
2. [Second action if needed]
3. [...]
(Maximum 4 steps. Be specific. Do not write generic "proceed with design" steps.)

## Gate Decision
**[APPROVED FOR ASSIGNMENT | NEEDS INFO | ON HOLD]**
[One sentence rationale for the gate decision.]
```

---

## Gate Decision Rules

- **APPROVED FOR ASSIGNMENT**: no missing required fields, `ready_to_staff` is
  true, a recommended designer is matched, and complexity is low or medium
  with no blocking risk flags.
- **NEEDS INFO**: any missing required field (`skillset_requested`,
  `timing_days_estimate`, `ready_to_staff`), OR no designer match found,
  OR `requires_im_review` is true with unresolved blocking risks.
- **ON HOLD**: `ready_to_staff` is false, OR `priority_flag` is `"on_hold"`.

The gate decision at the top and at the bottom must always match.

## Evidence vs. Assumptions Rules

- **Evidence**: any field that was explicitly stated in the source request text
  or read directly from the roster (name, load, skill tag).
- **Assumption**: any field inferred by the agent (timing estimate converted
  from a phrase, embed flag inferred from "embedded team" language, designer
  domain fit inferred from past assignments).
- Always include at least one assumption row if any inference was made.
- Never list an item as Evidence if it required inference.

## Style Rules

- Write in plain, direct language. No em-dashes. No marketing language.
- The Request Summary must be understandable by someone who has not read
  the original request.
- The Recommended Designer block must show real numbers from the roster —
  never write "available" without showing the actual percentages.
- Maximum brief length: 600 words (excluding tables). Be concise.
