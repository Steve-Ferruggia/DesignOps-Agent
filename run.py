#!/usr/bin/env python3
"""
DesignOps Triage Agent — Orchestrator
======================================
Runs the full triage workflow for a single design support request.

Usage:
    python run.py <input_file>               # run on a .txt request file
    python run.py --input "raw text"         # run on inline text
    python run.py --demo                     # run all three sample inputs

Requirements:
    pip install openai python-dotenv

Set OPENAI_API_KEY in a .env file or as an environment variable.
Model defaults to gpt-4o; override with OPENAI_MODEL env var.
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
BASE_DIR = Path(__file__).parent
MEMORY_DIR = BASE_DIR / "memory"
SKILLS_DIR = BASE_DIR / "skills"
AGENT_DIR = BASE_DIR / "agent"
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------
def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f"[WARN] Could not load {path}: {e}", file=sys.stderr)
        return {}


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def load_text(path: Path) -> str:
    return path.read_text()


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
def chat(system: str, user: str, json_mode: bool = False) -> str:
    """Single LLM call. Returns the assistant message content."""
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        **kwargs,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Skill loaders
# ---------------------------------------------------------------------------
def skill_extract_requirements(raw_request: str) -> dict:
    skill_text = load_text(SKILLS_DIR / "extract_requirements.md")
    system = (
        "You are a design operations assistant. "
        "Follow the skill instructions below exactly and return valid JSON only.\n\n"
        + skill_text
    )
    user = f"Parse the following design support request:\n\n---\n{raw_request}\n---"
    raw = chat(system, user, json_mode=True)
    return json.loads(raw)


def skill_classify_complexity(requirements: dict, domain_history: dict) -> dict:
    skill_text = load_text(SKILLS_DIR / "classify_complexity.md")
    system = (
        "You are a design operations assistant. "
        "Follow the skill instructions below exactly and return valid JSON only.\n\n"
        + skill_text
    )
    user = dedent(f"""
        Classify the following structured request.

        Requirements:
        {json.dumps(requirements, indent=2)}

        Domain history (from memory):
        {json.dumps(domain_history, indent=2)}
    """)
    raw = chat(system, user, json_mode=True)
    return json.loads(raw)


def skill_generate_brief(requirements: dict, classification: dict, designer_match: dict) -> str:
    skill_text = load_text(SKILLS_DIR / "generate_brief.md")
    system = (
        "You are a design operations assistant. "
        "Follow the skill instructions below exactly and produce a Markdown brief.\n\n"
        + skill_text
    )
    user = dedent(f"""
        Generate a Design Support Brief from the following inputs.

        Requirements:
        {json.dumps(requirements, indent=2)}

        Classification:
        {json.dumps(classification, indent=2)}

        Designer Match:
        {json.dumps(designer_match, indent=2)}
    """)
    return chat(system, user, json_mode=False)


# ---------------------------------------------------------------------------
# Designer matching logic
# ---------------------------------------------------------------------------
SKILL_ALIASES = {
    "UX/VD": {"UX", "VD"},
    "UX/R": {"UX/R"},
    "VD": {"VD"},
    "UX": {"UX"},
    "MM": {"MM"},
    "Content": {"Content"},
}


def designer_matches_skill(designer: dict, skillset_requested: str) -> bool:
    if not skillset_requested:
        return False
    needed = SKILL_ALIASES.get(skillset_requested, {skillset_requested})
    designer_skills = set(designer.get("skills", []))
    return bool(needed & designer_skills)


def designer_is_available(designer: dict, size_pct: int, timing: str) -> bool:
    load = designer.get("current_load_pct", 100)
    if load >= 100:
        return False
    avail = designer.get("available_pct_next_4_weeks", [0, 0, 0, 0])
    week1 = avail[0] if avail else 0
    # For 1-day requests, any designer under 100% qualifies
    if timing and ("1 day" in timing.lower() or "1-2 day" in timing.lower()):
        return True
    # Otherwise need week1 availability >= size_pct fraction
    min_needed = (size_pct or 0) / 100 * 0.25  # at least 25% of requested size in week 1
    return week1 >= min_needed


def score_designer(designer: dict, requirements: dict, classification: dict) -> int:
    score = 0
    domain = (requirements.get("domain") or "").strip()
    embed = requirements.get("embed_requested")
    complexity = classification.get("complexity", "low")

    if domain and domain in designer.get("domains", []):
        score += 3
    if embed and designer.get("embed_eligible"):
        score += 2
    past = designer.get("past_assignments", [])
    jira = requirements.get("jira_key", "")
    if any(domain in (p or "") for p in past):
        score += 2
    if jira and jira in past:
        score += 4

    avail = designer.get("available_pct_next_4_weeks", [0])
    week1 = avail[0] if avail else 0
    extra = max(0, week1 - ((requirements.get("size_pct") or 0) / 100 * 0.25))
    score += int(extra / 0.25)

    level = designer.get("level", "Mid")
    if complexity == "high" and level == "Senior":
        score += 1
    if complexity == "low" and level == "Junior":
        score += 1

    return score


def match_designer(requirements: dict, classification: dict, roster: list) -> dict:
    skillset = requirements.get("skillset_requested")
    size_pct = requirements.get("size_pct") or 0
    timing = requirements.get("timing") or ""

    candidates = [
        d for d in roster
        if designer_matches_skill(d, skillset) and designer_is_available(d, size_pct, timing)
    ]

    if not candidates:
        return {
            "recommended": None,
            "alternatives": [],
            "match_rationale": "No designer passes mandatory filters.",
            "match_confidence": "low",
            "no_match_reason": (
                f"No designer with skill '{skillset}' is available at "
                f"{size_pct}% for '{timing}'. "
                "Consider revisiting timing or splitting the request."
            ),
        }

    scored = sorted(candidates, key=lambda d: score_designer(d, requirements, classification), reverse=True)
    top = scored[0]
    alts = scored[1:3]

    top_score = score_designer(top, requirements, classification)
    if top_score >= 4:
        confidence = "high"
    elif top_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    rationale_parts = []
    if (requirements.get("domain") or "") in top.get("domains", []):
        rationale_parts.append(f"domain match ({requirements.get('domain')})")
    if requirements.get("embed_requested") and top.get("embed_eligible"):
        rationale_parts.append("embed eligible")
    rationale_parts.append(f"current load {top.get('current_load_pct')}%")
    avail = top.get("available_pct_next_4_weeks", [0])
    rationale_parts.append(f"W1 availability {int(avail[0] * 100)}%")
    rationale = "; ".join(rationale_parts) if rationale_parts else "best available match"

    return {
        "recommended": top,
        "alternatives": alts,
        "match_rationale": rationale.capitalize(),
        "match_confidence": confidence,
        "no_match_reason": None,
    }


# ---------------------------------------------------------------------------
# Memory update
# ---------------------------------------------------------------------------
def update_memory(requirements: dict, classification: dict, designer_match: dict,
                  brief_path: Path, gate: str) -> None:
    # 1. Append to request history
    history = load_json(MEMORY_DIR / "request_history.json")
    new_entry = {
        "jira_key": requirements.get("jira_key"),
        "domain": requirements.get("domain"),
        "description": requirements.get("description"),
        "skillset": requirements.get("skillset_requested"),
        "size": f"{requirements.get('size_pct')}%",
        "timing": requirements.get("timing"),
        "embed": requirements.get("embed_requested"),
        "days_to_staff": None,
        "assigned_to": (designer_match.get("recommended") or {}).get("id"),
        "outcome": "pending" if gate == "APPROVED FOR ASSIGNMENT" else "needs_info",
        "complexity": classification.get("complexity"),
        "notes": f"Generated by agent run at {datetime.now(timezone.utc).isoformat()}",
    }
    history.setdefault("past_requests", []).append(new_entry)
    save_json(MEMORY_DIR / "request_history.json", history)

    # 2. Update designer load if low/medium complexity + approved
    rec = designer_match.get("recommended")
    if rec and classification.get("complexity") in ("low", "medium") and gate == "APPROVED FOR ASSIGNMENT":
        roster_data = load_json(MEMORY_DIR / "designer_roster.json")
        for d in roster_data.get("roster", []):
            if d["id"] == rec["id"]:
                size = requirements.get("size_pct") or 0
                d["current_load_pct"] = min(100, d.get("current_load_pct", 0) + size)
                avail = d.get("available_pct_next_4_weeks", [0, 0, 0, 0])
                if avail:
                    avail[0] = max(0.0, avail[0] - (size / 100 * 0.25))
                break
        save_json(MEMORY_DIR / "designer_roster.json", roster_data)

    # 3. Append run log
    mem = load_json(MEMORY_DIR / "agent_memory.json")
    run_id = f"run_{len(mem.get('run_log', [])) + 1:03d}"
    mem.setdefault("run_log", []).append({
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "jira_key": requirements.get("jira_key"),
        "status": "success" if gate == "APPROVED FOR ASSIGNMENT" else gate.lower().replace(" ", "_"),
        "brief_path": str(brief_path.relative_to(BASE_DIR)),
        "recommended_designer_id": (rec or {}).get("id"),
        "gate_decision": gate,
    })
    mem["_last_updated"] = datetime.now(timezone.utc).isoformat()
    save_json(MEMORY_DIR / "agent_memory.json", mem)


# ---------------------------------------------------------------------------
# Gate extraction helper
# ---------------------------------------------------------------------------
def extract_gate(brief_md: str) -> str:
    for line in brief_md.splitlines():
        if "APPROVED FOR ASSIGNMENT" in line:
            return "APPROVED FOR ASSIGNMENT"
        if "NEEDS INFO" in line:
            return "NEEDS INFO"
        if "ON HOLD" in line:
            return "ON HOLD"
    return "NEEDS INFO"


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def run(raw_request: str) -> Path:
    print("\n" + "=" * 60)
    print("DesignOps Triage Agent")
    print("=" * 60)

    # Load memory
    roster_data = load_json(MEMORY_DIR / "designer_roster.json")
    roster = roster_data.get("roster", [])
    history = load_json(MEMORY_DIR / "request_history.json")

    # Step 1 — Extract requirements
    print("\n[1/5] Extracting requirements...")
    requirements = skill_extract_requirements(raw_request)
    print(f"      Jira: {requirements.get('jira_key')} | Skill: {requirements.get('skillset_requested')} "
          f"| Size: {requirements.get('size_pct')}% | Timing: {requirements.get('timing')}")
    if requirements.get("missing_fields"):
        print(f"      Missing fields: {requirements['missing_fields']}")

    # Step 2 — Classify complexity
    print("\n[2/5] Classifying complexity...")
    domain = requirements.get("domain") or ""
    domain_history = history.get("customer_patterns", {}).get(domain, {})
    classification = skill_classify_complexity(requirements, domain_history)
    print(f"      Complexity: {classification.get('complexity').upper()} | "
          f"Effort: {classification.get('effort_designer_days')} days | "
          f"Priority: {classification.get('priority_flag')}")
    if classification.get("risk_flags"):
        print(f"      Risk flags: {classification['risk_flags']}")

    # Step 3 — Match designer
    print("\n[3/5] Matching designer...")
    designer_match = match_designer(requirements, classification, roster)
    rec = designer_match.get("recommended")
    if rec:
        print(f"      Recommended: {rec['name']} (load: {rec['current_load_pct']}%, "
              f"confidence: {designer_match['match_confidence']})")
    else:
        print(f"      No match found: {designer_match['no_match_reason']}")

    # Step 4 — Generate brief
    print("\n[4/5] Generating brief...")
    brief_md = skill_generate_brief(requirements, classification, designer_match)
    gate = extract_gate(brief_md)

    # Write output
    jira_key = requirements.get("jira_key") or f"untitled_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    safe_key = re.sub(r"[^A-Za-z0-9_-]", "_", jira_key)
    brief_path = OUTPUTS_DIR / f"{safe_key}_brief.md"
    brief_path.write_text(brief_md)

    # Step 5 — Update memory
    print("\n[5/5] Updating memory...")
    update_memory(requirements, classification, designer_match, brief_path, gate)

    # Summary
    print("\n" + "-" * 60)
    print(f"  Request : {requirements.get('description', 'N/A')}")
    print(f"  Complexity : {classification.get('complexity', 'N/A').upper()}")
    print(f"  Effort   : {classification.get('effort_designer_days', 'N/A')} designer-days")
    print(f"  Designer : {rec['name'] if rec else 'No match'}")
    print(f"  Gate     : {gate}")
    print(f"  Brief    : {brief_path}")
    print("-" * 60 + "\n")

    return brief_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="DesignOps Triage Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input_file", nargs="?", help="Path to a .txt request file")
    group.add_argument("--input", "-i", help="Raw request text (quoted string)")
    group.add_argument("--demo", action="store_true", help="Run all three sample inputs")
    args = parser.parse_args()

    if args.demo:
        samples = [
            BASE_DIR / "inputs" / "request_1_low_complexity.txt",
            BASE_DIR / "inputs" / "request_2_medium_complexity.txt",
            BASE_DIR / "inputs" / "request_3_edge_case_not_ready.txt",
        ]
        for sample in samples:
            print(f"\n>>> Running demo: {sample.name}")
            run(sample.read_text())
    elif args.input:
        run(args.input)
    else:
        path = Path(args.input_file)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        run(path.read_text())


if __name__ == "__main__":
    main()
