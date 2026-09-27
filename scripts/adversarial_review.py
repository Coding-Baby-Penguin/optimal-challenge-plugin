#!/usr/bin/env python3
"""Second-pass adversarial checks independent of validate.py."""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from .evaluate_routing import validate_manifest as validate_routing_manifest
except ImportError:  # Direct CLI execution puts scripts/ on sys.path.
    from evaluate_routing import validate_manifest as validate_routing_manifest

ROOT = Path(__file__).resolve().parents[1]


def unconditional_costly_behavior_issues(policy_texts):
    """Return source-qualified unconditional team/review policy violations."""

    patterns = (
        r"\balways\s+spawn\b",
        r"\balways\s+delegate\b",
        r"\balways\s+create\s+(?:a\s+)?team\b",
        r"\balways\s+require\s+independent\s+review\b",
        r"\breview\s+every\s+task\s+independently\b",
        r"\bindependent\s+review\s+is\s+required\s+for\s+(?:all|every)\b",
    )
    found = []
    for source, content in policy_texts.items():
        if not isinstance(content, str):
            found.append(f"{source}: policy content is not text")
            continue
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                found.append(f"{source}: unconditional costly behavior matches {pattern}")
    return found


def collect_issues(root: Path = ROOT) -> tuple[list[str], int]:
    skill_path = root / "skills" / "optimal-challenge" / "SKILL.md"
    reference_dir = skill_path.parent / "references"
    issues: list[str] = []

    def require(condition, message):
        if not condition:
            issues.append(message)

    skill = skill_path.read_text(encoding="utf-8")
    reference_paths = sorted(reference_dir.glob("*.md"))
    all_refs = {path.name for path in reference_paths}
    mentioned = set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", skill))
    require(
        all_refs == mentioned,
        f"Orphan/unmentioned references: files-only={sorted(all_refs-mentioned)}, mentioned-only={sorted(mentioned-all_refs)}",
    )

    for term in ["PageRank", "tree-sitter", "pytest", "npm test", "PostToolUse", "PreToolUse", "Claude Opus", "GPT-"]:
        require(term.lower() not in skill.lower(), f"Runtime router leaked specialist/platform detail: {term}")

    runtime_policy = {"SKILL.md": skill}
    runtime_policy.update({path.name: path.read_text(encoding="utf-8") for path in reference_paths})
    combined = "\n".join(runtime_policy[path.name] for path in reference_paths)
    for phrase in [
        "never autonomously expand privileges",
        "never expand permissions",
        "do not promote from one occurrence",
        "the parent is process authority",
        "every mitigation has a blind spot",
        "passing tests are evidence only for what they cover",
    ]:
        require(phrase in combined.lower(), f"Missing critical guardrail: {phrase}")
    issues.extend(unconditional_costly_behavior_issues(runtime_policy))

    orchestration = json.loads((root / "config" / "orchestration.json").read_text(encoding="utf-8"))
    privacy = orchestration.get("persistence_privacy", {})
    require(privacy.get("persist_transcripts") is False, "Transcript persistence must default false")
    require(privacy.get("persist_sensitive_data") is False, "Sensitive-data persistence must default false")
    budget = orchestration.get("budget", {})
    require(budget.get("enforcement") == "advisory", "Committed budget enforcement must remain advisory")
    team_policy = runtime_policy["team-orchestration.md"].lower()
    require("never promise automatic prevention" in team_policy, "Advisory budget policy overclaims enforcement")
    for forbidden in ["advisory budget prevents", "advisory ceiling guarantees", "automatic budget enforcement"]:
        require(forbidden not in combined.lower(), f"Advisory budget represented as enforced: {forbidden}")

    for forbidden_path in [".mcp.json", "hooks/hooks.json", "agents", "monitors/monitors.json", ".lsp.json", "settings.json"]:
        require(not (root / forbidden_path).exists(), f"Unexpected active component in lightweight v1: {forbidden_path}")

    try:
        validated_routes = validate_routing_manifest(root / "tests" / "team-routing.json")
        require(validated_routes > 0, "Team routing evaluator validated no cases")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"Calculation/route disagreement: {exc}")

    project = json.loads((root / "config" / "project.json").read_text(encoding="utf-8"))
    for key in ["orchestrationSchema", "teamRegistrySchema", "allocationLedgerSchema"]:
        relative = project.get("paths", {}).get(key)
        require(isinstance(relative, str) and (root / relative).is_file(), f"Orphan or missing schema path: {key}")
    for template in ["TEAM-CHARTER.md", "TEAMMATE-CAPSULE.yaml", "RETURN-CAPSULE.yaml", "task-capsule.yaml", "QUESTION-BUNDLE.md"]:
        path = skill_path.parent / "templates" / template
        require(path.is_file(), f"Missing team template: {template}")
        require(f"templates/{template}".lower() in combined.lower(), f"Orphan team template: {template}")

    portable = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    require(
        set(portable) <= {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"},
        "Portable manifest has unsupported top-level field",
    )
    require(
        re.fullmatch(r"(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", portable["name"]) is not None,
        "Portable plugin name violates Agent Plugins pattern",
    )
    claude = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", claude["name"]) is not None, "Claude plugin name is not kebab-case")

    scenarios = json.loads((root / "tests" / "scenarios.json").read_text(encoding="utf-8"))
    scenario_text = "\n".join(scenario["expect"] for scenario in scenarios)
    for pair in [
        ("multi-workstream", "challenge-overdelegation"),
        ("evolution-candidate", "no-promotion-from-one-event"),
        ("hook-candidate", "do-not-hook-judgment"),
    ]:
        require(all(token in scenario_text for token in pair), f"Missing two-sided scenario pair: {pair}")
    return issues, len(all_refs)


def main() -> int:
    try:
        issues, reference_count = collect_issues()
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues, reference_count = [f"input: {exc}"], 0
    if issues:
        print("ADVERSARIAL REVIEW FAILED")
        for issue in issues:
            print("-", issue)
        return 1
    print("ADVERSARIAL REVIEW PASSED")
    print(f"Reference modules: {reference_count}; all are explicitly lazy-addressable from SKILL.md")
    print("No active hooks, MCP servers, agents, monitors, LSP servers, or default settings shipped")
    print("Two-sided regression cases present for delegation, evolution, and hooks")
    print("Agent-team adversarial checks passed: conditional spawning/review, budget truth, routing agreement, and owned schemas/templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
