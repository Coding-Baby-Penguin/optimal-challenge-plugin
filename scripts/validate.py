#!/usr/bin/env python3
"""Dependency-free validator for the Optimal Challenge plugin package."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "optimal-challenge" / "SKILL.md"
REFS = SKILL.parent / "references"
SCENARIOS = ROOT / "tests" / "scenarios.json"

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid JSON: {path.relative_to(ROOT)}: {exc}")
        return {}


# Required structure
for rel in [
    "plugin.json",
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    "skills/optimal-challenge/SKILL.md",
    "tests/scenarios.json",
]:
    check((ROOT / rel).is_file(), f"Missing required file: {rel}")

root_manifest = read_json(ROOT / "plugin.json")
codex_manifest = read_json(ROOT / ".codex-plugin" / "plugin.json")
claude_manifest = read_json(ROOT / ".claude-plugin" / "plugin.json")

names = {m.get("name") for m in [root_manifest, codex_manifest, claude_manifest] if isinstance(m, dict)}
versions = {m.get("version") for m in [root_manifest, codex_manifest, claude_manifest] if isinstance(m, dict)}
check(names == {"optimal-challenge"}, f"Manifest name mismatch: {names}")
check(versions == {"1.0.0"}, f"Manifest version mismatch: {versions}")
check(root_manifest.get("$schema") == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "Portable manifest schema mismatch")
check(codex_manifest.get("skills") == "./skills/", "Codex skills path must be ./skills/")

# No active hooks in v1
check(not (ROOT / "hooks" / "hooks.json").exists(), "v1 must not ship active hooks/hooks.json")

# No symlinks or unsafe relative paths
for path in ROOT.rglob("*"):
    check(not path.is_symlink(), f"Symlink not allowed in package: {path.relative_to(ROOT)}")
    rel = path.relative_to(ROOT)
    check(".." not in rel.parts, f"Unsafe path: {rel}")

# Skill frontmatter
text = SKILL.read_text(encoding="utf-8")
fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
check(bool(fm), "SKILL.md missing YAML frontmatter")
front = fm.group(1) if fm else ""
name_m = re.search(r"^name:\s*(.+)$", front, re.M)
desc_m = re.search(r"^description:\s*(.+)$", front, re.M)
check(bool(name_m), "SKILL.md missing name")
check(bool(desc_m), "SKILL.md missing description")
if name_m:
    skill_name = name_m.group(1).strip()
    check(skill_name == "optimal-challenge", f"Unexpected skill name: {skill_name}")
    check(bool(re.fullmatch(r"[A-Za-z0-9-]+", skill_name)), "Skill name contains unsupported characters")
if desc_m:
    desc = desc_m.group(1).strip()
    check(desc.startswith("Use when"), "Skill description must start with 'Use when'")
    check(len(desc) <= 500, f"Skill description too long: {len(desc)} chars")

body = text[fm.end():] if fm else text
word_count = len(re.findall(r"\b[\w'-]+\b", body))
check(word_count <= 350, f"Runtime SKILL.md too large: {word_count} words (max 350)")

# All directly named reference files in SKILL.md must exist.
refs = sorted(set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", text)))
for ref in refs:
    check((REFS / ref).is_file(), f"Missing referenced module: references/{ref}")
check(len(refs) >= 8, f"Expected lazy-loaded reference coverage, found only {len(refs)}")

# Templates must be small and nonempty.
for path in (SKILL.parent / "templates").iterdir():
    if path.is_file():
        check(path.stat().st_size > 0, f"Empty template: {path.name}")
        check(path.stat().st_size < 10_000, f"Template unexpectedly large: {path.name}")

# Scenario matrix coverage and integrity.
scenarios = read_json(SCENARIOS)
check(isinstance(scenarios, list), "tests/scenarios.json must be a list")
if isinstance(scenarios, list):
    ids = [s.get("id") for s in scenarios]
    check(len(ids) == len(set(ids)), "Duplicate scenario IDs")
    check(len(scenarios) >= 25, f"Insufficient scenario coverage: {len(scenarios)}")
    prefixes = {str(i).split("-", 1)[0] for i in ids if i}
    required = {"direct", "ask", "research", "code", "agent", "context", "storage", "preference", "evolution", "hook", "sidefx", "simplify", "stagnation", "security", "output"}
    missing = required - prefixes
    check(not missing, f"Missing scenario classes: {sorted(missing)}")
    for s in scenarios:
        check(bool(s.get("prompt")), f"Scenario {s.get('id')} missing prompt")
        check(bool(s.get("expect")), f"Scenario {s.get('id')} missing expected behavior")
        check(isinstance(s.get("modules"), list), f"Scenario {s.get('id')} modules must be a list")

# Guard against accidental platform-coupling in the runtime core.
for forbidden in ["claude-opus", "gpt-", "~/.claude", "~/.codex"]:
    check(forbidden not in body.lower(), f"Runtime core contains platform-specific detail: {forbidden}")

if errors:
    print("VALIDATION FAILED")
    for e in errors:
        print(f"- {e}")
    sys.exit(1)

print("VALIDATION PASSED")
print(f"Runtime skill words: {word_count}")
print(f"Referenced lazy modules: {len(refs)}")
print(f"Behavior scenarios: {len(scenarios)}")
print("Active hooks: 0")
