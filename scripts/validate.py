#!/usr/bin/env python3
"""Dependency-free validator for the Optimal Challenge plugin package."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG_PATH = ROOT / "config" / "project.json"

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


project_config = read_json(PROJECT_CONFIG_PATH)
plugin_config = project_config.get("plugin", {}) if isinstance(project_config, dict) else {}
path_config = project_config.get("paths", {}) if isinstance(project_config, dict) else {}
SKILL = ROOT / path_config.get("skill", "__missing_skill__")
REFS = SKILL.parent / "references"
SCENARIOS = ROOT / path_config.get("scenarios", "__missing_scenarios__")
expected_name = plugin_config.get("name")
expected_version = plugin_config.get("version")
expected_repository = plugin_config.get("repository")
expected_schema = plugin_config.get("portableSchema")
expected_codex_skills_path = plugin_config.get("codexSkillsPath")


# Required structure
for rel in [
    "config/project.json",
    "config/README.md",
    "docs/PROJECT-STATE.md",
    "plugin.json",
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    "skills/optimal-challenge/SKILL.md",
    "skills/optimal-challenge/agents/openai.yaml",
    "skills/optimal-challenge/references/continuity-collaboration.md",
    "skills/optimal-challenge/references/folder-architecture.md",
    "skills/optimal-challenge/references/configuration-governance.md",
    "skills/optimal-challenge/references/readme-maintenance.md",
    "skills/optimal-challenge/templates/FOLDER-PLAN.md",
    "skills/optimal-challenge/templates/PROJECT-STATE.md",
    "skills/optimal-challenge/templates/QUESTION-BUNDLE.md",
    "skills/optimal-challenge/templates/README-TEMPLATE.md",
    "skills/optimal-challenge/templates/REUSABLE-SNIPPET.md",
    "README.md",
    ".gitignore",
    "tests/scenarios.json",
    "tests/validation/test_package.py",
]:
    check((ROOT / rel).is_file(), f"Missing required file: {rel}")

root_manifest = read_json(ROOT / "plugin.json")
codex_manifest = read_json(ROOT / ".codex-plugin" / "plugin.json")
claude_manifest = read_json(ROOT / ".claude-plugin" / "plugin.json")

names = {m.get("name") for m in [root_manifest, codex_manifest, claude_manifest] if isinstance(m, dict)}
versions = {m.get("version") for m in [root_manifest, codex_manifest, claude_manifest] if isinstance(m, dict)}
check(bool(expected_name), "config/project.json missing plugin.name")
check(bool(expected_version), "config/project.json missing plugin.version")
check(bool(expected_repository), "config/project.json missing plugin.repository")
check(bool(expected_schema), "config/project.json missing plugin.portableSchema")
check(bool(expected_codex_skills_path), "config/project.json missing plugin.codexSkillsPath")
check(names == {expected_name}, f"Manifest name mismatch: {names}")
check(versions == {expected_version}, f"Manifest version mismatch: {versions}")
repositories = {m.get("repository") for m in [root_manifest, codex_manifest, claude_manifest] if isinstance(m, dict)}
check(repositories == {expected_repository}, f"Manifest repository mismatch: {repositories}")
check(root_manifest.get("$schema") == expected_schema, "Portable manifest schema mismatch")
check(codex_manifest.get("skills") == expected_codex_skills_path, "Codex skills path mismatch")

# This release line intentionally ships without active hooks.
check(not (ROOT / "hooks" / "hooks.json").exists(), "Plugin must not ship active hooks/hooks.json")

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
    check(skill_name == expected_name, f"Unexpected skill name: {skill_name}")
    check(bool(re.fullmatch(r"[A-Za-z0-9-]+", skill_name)), "Skill name contains unsupported characters")
if desc_m:
    desc = desc_m.group(1).strip()
    check(desc.startswith("Use when"), "Skill description must start with 'Use when'")
    check(len(desc) <= 500, f"Skill description too long: {len(desc)} chars")

body = text[fm.end():] if fm else text
word_count = len(re.findall(r"\b[\w'-]+\b", body))
check(word_count <= 350, f"Runtime SKILL.md too large: {word_count} words (max 350)")

# Always-on invocation metadata
agent_yaml = (SKILL.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
check("allow_implicit_invocation: true" in agent_yaml, "Optimal Challenge must allow implicit invocation")

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

# Continuity/collaboration safeguards must remain discoverable and actionable.
continuity = (REFS / "continuity-collaboration.md").read_text(encoding="utf-8").lower()
for phrase in ["checkpoint", "quota", "question bundle", "next steps", "reusable", "gitignore"]:
    check(phrase in continuity, f"Continuity policy missing concept: {phrase}")

gitignore_lines = {
    line.strip()
    for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
}
for pattern in [".env", ".env.*", "!.env.example", "*.pem", "*.key", "credentials.*", ".optimal-challenge/", "*.log", "dist/"]:
    check(pattern in gitignore_lines, f".gitignore missing safe default: {pattern}")

folder_policy = (REFS / "folder-architecture.md").read_text(encoding="utf-8").lower()
for phrase in ["ecosystem", "project root", "validation", "one-file folder", "path consumers", "rollback"]:
    check(phrase in folder_policy, f"Folder architecture policy missing concept: {phrase}")

config_policy = (REFS / "configuration-governance.md").read_text(encoding="utf-8").lower()
for phrase in ["hard-code audit", "deploy-varying", "named constant", "config/", "single loader", "secret manager"]:
    check(phrase in config_policy, f"Configuration governance policy missing concept: {phrase}")

readme_policy = (REFS / "readme-maintenance.md").read_text(encoding="utf-8").lower()
for phrase in ["one h1", "sentence case", "quick start", "relative links", "same change", "verify commands", "stale"]:
    check(phrase in readme_policy, f"README maintenance policy missing concept: {phrase}")

check(not (SKILL.parent / "templates" / "CHECKPOINT.md").exists(), "Legacy CHECKPOINT.md must not coexist with PROJECT-STATE.md")
check(not (SKILL.parent / "templates" / "STATE.md").exists(), "Legacy STATE.md must not coexist with PROJECT-STATE.md")

# Scenario matrix coverage and integrity.
scenarios = read_json(SCENARIOS)
check(isinstance(scenarios, list), "tests/scenarios.json must be a list")
if isinstance(scenarios, list):
    ids = [s.get("id") for s in scenarios]
    check(len(ids) == len(set(ids)), "Duplicate scenario IDs")
    check(len(scenarios) >= 25, f"Insufficient scenario coverage: {len(scenarios)}")
    prefixes = {str(i).split("-", 1)[0] for i in ids if i}
    required = {"direct", "ask", "research", "code", "agent", "context", "storage", "preference", "evolution", "hook", "sidefx", "simplify", "stagnation", "security", "structure", "config", "docs", "output"}
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
