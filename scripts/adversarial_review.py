#!/usr/bin/env python3
"""Second-pass adversarial checks independent of validate.py."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "optimal-challenge" / "SKILL.md"
REFDIR = SKILL.parent / "references"
issues = []


def require(cond, msg):
    if not cond:
        issues.append(msg)

skill = SKILL.read_text(encoding="utf-8")
all_refs = {p.name for p in REFDIR.glob("*.md")}
mentioned = set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", skill))
require(all_refs == mentioned, f"Orphan/unmentioned references: files-only={sorted(all_refs-mentioned)}, mentioned-only={sorted(mentioned-all_refs)}")

# Lightweight core: implementation detail must remain outside router.
for term in ["PageRank", "tree-sitter", "pytest", "npm test", "PostToolUse", "PreToolUse", "Claude Opus", "GPT-"]:
    require(term.lower() not in skill.lower(), f"Runtime router leaked specialist/platform detail: {term}")

# Guard autonomy boundaries and user control.
combined = "\n".join(p.read_text(encoding="utf-8") for p in REFDIR.glob("*.md"))
for phrase in [
    "never autonomously expand privileges",
    "never expand permissions",
    "do not promote from one occurrence",
    "the parent is process authority",
    "every mitigation has a blind spot",
    "passing tests are evidence only for what they cover",
]:
    require(phrase in combined.lower(), f"Missing critical guardrail: {phrase}")

# Ensure no plugin code or config silently activates external services/hooks/agents.
for forbidden_path in [".mcp.json", "hooks/hooks.json", "agents", "monitors/monitors.json", ".lsp.json", "settings.json"]:
    p = ROOT / forbidden_path
    require(not p.exists(), f"Unexpected active component in lightweight v1: {forbidden_path}")

# Validate manifest fields against the current minimal documented constraints used by this package.
portable = json.loads((ROOT / "plugin.json").read_text())
require(set(portable) <= {"$schema","name","version","description","author","homepage","repository","license","keywords","extensions"}, "Portable manifest has unsupported top-level field")
require(re.fullmatch(r"(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", portable["name"]) is not None, "Portable plugin name violates Agent Plugins pattern")
claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", claude["name"]) is not None, "Claude plugin name is not kebab-case")

# Scenario suite must include both positive and negative versions of key costly behaviors.
scenarios = json.loads((ROOT / "tests" / "scenarios.json").read_text())
text = "\n".join(s["expect"] for s in scenarios)
for pair in [("multi-workstream","challenge-overdelegation"), ("evolution-candidate","no-promotion-from-one-event"), ("hook-candidate","do-not-hook-judgment")]:
    require(all(x in text for x in pair), f"Missing two-sided scenario pair: {pair}")

if issues:
    print("ADVERSARIAL REVIEW FAILED")
    for issue in issues:
        print("-", issue)
    sys.exit(1)

print("ADVERSARIAL REVIEW PASSED")
print(f"Reference modules: {len(all_refs)}; all are explicitly lazy-addressable from SKILL.md")
print("No active hooks, MCP servers, agents, monitors, LSP servers, or default settings shipped")
print("Two-sided regression cases present for delegation, evolution, and hooks")
