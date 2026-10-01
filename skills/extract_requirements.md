---
name: extract_requirements
description: >
  Parses a raw design support request and extracts structured fields required
  for triage. Flags missing or ambiguous information and returns a structured
  JSON object. Reusable in any intake or onboarding workflow where unstructured
  text must be turned into actionable fields.
---

# Skill: extract_requirements

## Purpose
Parse a raw design support request (free-text description, Jira ticket body, or
email) and extract the structured fields the DesignOps triage workflow depends
on. Flag anything missing or ambiguous so the Iteration Manager can resolve it
before assignment.

## Input
A single string containing the raw request text. May include a domain/sponsor
name, a Jira key, a description, scope notes, and any timing or size hints.

## Output
Return a JSON object with the following fields. Use `null` for any field that
cannot be confidently extracted. Set `missing_fields` to a list of field names
that are null or ambiguous.

```json
{
  "jira_key": "CD-XXXXX or null",
  "domain": "Sponsor/domain team name or null",
  "description": "One-sentence summary of the request",
  "scope_details": "Verbatim scope text or best-effort summary",
  "skillset_requested": "UX | VD | UX/R | MM | UX/VD | null",
  "size_pct": "25 | 50 | 75 | 100 or null (numeric, as integer)",
  "timing": "human-readable duration e.g. '1 Day', '4-6 Weeks', '3 Months' or null",
  "timing_days_estimate": "integer best-estimate of calendar days or null",
  "embed_requested": "true | false | null",
  "hard_deadline": "ISO date string or null",
  "ready_to_staff": "true | false | null — whether the team is ready for a designer",
  "domain_context": "Any known product/system context mentioned",
  "missing_fields": ["list of field names that are null or require clarification"],
  "clarifying_questions": ["list of specific questions to ask the requester"]
}
```

## Rules
1. Do NOT infer `ready_to_staff: true` unless the text explicitly signals the
   team is ready. Default to `null` when ambiguous.
2. For `skillset_requested`, map common synonyms:
   - "visual design", "graphic design", "VD" → `"VD"`
   - "UX design", "interaction design", "wireframes", "prototyping" → `"UX"`
   - "user research", "UXR", "usability testing", "survey" → `"UX/R"`
   - "motion", "animation" → `"MM"`
   - Hybrid requests mentioning both UX and VD → `"UX/VD"`
3. For `size_pct`, map common phrases:
   - "full time", "100%", "dedicated" → `100`
   - "half time", "50%", "0.5 FTE" → `50`
   - "quarter time", "25%", "0.25 FTE" → `25`
   - "75%" → `75`
4. For `timing_days_estimate`, use conservative business-day estimates:
   - "1 day" → 1, "2-3 days" → 3, "1 week" → 5, "2 weeks" → 10,
   - "1 month" → 22, "2 months" → 44, "3 months" → 66, "6 months" → 132
5. Generate `clarifying_questions` only for fields that are truly blocking
   (skillset, timing, size, ready_to_staff). Do not ask about fields that
   can be reasonably inferred.
6. If the request is clearly on hold or not ready, set
   `ready_to_staff: false` and note it in `clarifying_questions`.

## Example

Input:
```
Domain: Pasquale
Jira: CD-18279
We need a UX designer at about 25% to help finish the CDPP portal Phase 1.
Phase 1 goes live January 18th so we need someone for about 2-3 weeks to review
error screens and incorporate seller feedback on the admin dashboard.
This is a continuation of Conner's earlier work.
```

Output:
```json
{
  "jira_key": "CD-18279",
  "domain": "Pasquale",
  "description": "UX designer at 25% to complete CDPP portal Phase 1 before Jan 18 launch",
  "scope_details": "Review error screens, validate them, and incorporate seller feedback on admin dashboard redesign. Continuation of prior work.",
  "skillset_requested": "UX",
  "size_pct": 25,
  "timing": "2-3 Weeks",
  "timing_days_estimate": 15,
  "embed_requested": true,
  "hard_deadline": "2023-01-18",
  "ready_to_staff": true,
  "domain_context": "CDPP portal, Phase 1 launch; prior designer was Conner Sinjem",
  "missing_fields": [],
  "clarifying_questions": []
}
```
