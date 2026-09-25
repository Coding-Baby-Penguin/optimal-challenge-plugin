from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "optimal-challenge"
PROJECT_CONFIG = ROOT / "config" / "project.json"


class PackageIndependentReview(unittest.TestCase):
    def test_manifests_agree_with_project_config(self):
        project = json.loads(PROJECT_CONFIG.read_text())
        paths = [ROOT / "plugin.json", ROOT / ".codex-plugin/plugin.json", ROOT / ".claude-plugin/plugin.json"]
        manifests = [json.loads(p.read_text()) for p in paths]
        self.assertEqual({m["name"] for m in manifests}, {project["plugin"]["name"]})
        self.assertEqual({m["version"] for m in manifests}, {project["plugin"]["version"]})
        self.assertEqual({m["repository"] for m in manifests}, {project["plugin"]["repository"]})
        self.assertEqual(manifests[0]["$schema"], project["plugin"]["portableSchema"])
        self.assertEqual(manifests[1]["skills"], project["plugin"]["codexSkillsPath"])

    def test_claude_marketplace_agrees_with_project_config(self):
        project = json.loads(PROJECT_CONFIG.read_text())["plugin"]
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(marketplace["$schema"], project["claudeMarketplaceSchema"])
        self.assertEqual(marketplace["name"], project["claudeMarketplaceName"])
        self.assertTrue(marketplace["description"])
        self.assertEqual(len(marketplace["plugins"]), 1)

        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], project["name"])
        self.assertEqual(entry["version"], project["version"])
        self.assertEqual(entry["source"], project["claudeMarketplaceSource"])
        self.assertEqual(entry["homepage"], project["repository"])

    def test_skill_is_small_and_trigger_focused(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        body = text.split("---", 2)[-1]
        words = re.findall(r"\b[\w'-]+\b", body)
        self.assertLessEqual(len(words), 350)
        self.assertIn("description: Use when", text)
        self.assertNotIn("1% chance", text.lower())

    def test_all_skill_reference_links_exist(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        refs = set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", text))
        self.assertGreaterEqual(len(refs), 8)
        for ref in refs:
            self.assertTrue((SKILL_DIR / "references" / ref).is_file(), ref)

    def test_router_is_always_on_and_reuses_existing_plans(self):
        text = (SKILL_DIR / "SKILL.md").read_text().lower()
        for phrase in [
            "handling any request",
            "never invoke `superpowers:using-superpowers`",
            "reuse an applicable approved plan",
            "thread length alone never justifies planning",
        ]:
            self.assertIn(phrase, text)

        agent = (SKILL_DIR / "agents" / "openai.yaml").read_text().lower()
        self.assertIn("allow_implicit_invocation: true", agent)

    def test_no_active_hooks_ship(self):
        self.assertFalse((ROOT / "hooks" / "hooks.json").exists())

    def test_delegation_policy_blocks_recursive_planning(self):
        text = (SKILL_DIR / "references" / "delegation-budget.md").read_text().lower()
        self.assertIn("parent is process authority", text)
        self.assertIn("do not independently re-run", text)
        self.assertIn("needs_capability", text)

    def test_preference_policy_cannot_override_truth_or_safety(self):
        text = (SKILL_DIR / "references" / "preference-model.md").read_text().lower()
        self.assertIn("correctness/safety", text)
        self.assertIn("never expand permissions", text)
        self.assertIn("sensitive personal traits", text)

    def test_evolution_is_bounded_and_reversible(self):
        text = (SKILL_DIR / "references" / "evolution-policy.md").read_text().lower()
        self.assertIn("rollback", text)
        self.assertIn("never autonomously expand privileges", text)
        self.assertIn("split", text)
        self.assertIn("prune", text)
        self.assertIn("retire", text)

    def test_codebase_paradoxes_are_guarded(self):
        text = (SKILL_DIR / "references" / "reality-model.md").read_text().lower()
        for phrase in [
            "available context will be used reliably",
            "retrieved code includes every relevant dependency",
            "passing tests prove the requested behavior",
            "more agents, retrieval, or verification monotonically improves quality",
        ]:
            self.assertIn(phrase, text)

    def test_context_state_does_not_become_append_only_chat_clone(self):
        text = (SKILL_DIR / "references" / "context-management.md").read_text().lower()
        self.assertIn("rewrite, do not append forever", text)
        self.assertIn("minimum sufficient context", text)

    def test_runtime_exposes_continuity_and_collaboration_policy(self):
        router = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertIn("references/continuity-collaboration.md", router)

        policy = (SKILL_DIR / "references" / "continuity-collaboration.md").read_text().lower()
        for phrase in [
            "quota",
            "resume",
            "question bundle",
            "next steps",
            "reusable",
            "hard-coded",
            "gitignore",
        ]:
            self.assertIn(phrase, policy)

    def test_single_project_state_template_has_resume_and_development_path(self):
        project_state = (SKILL_DIR / "templates" / "PROJECT-STATE.md").read_text().lower()
        for field in [
            "goal:",
            "last updated:",
            "current verified state:",
            "completed:",
            "now:",
            "next:",
            "later:",
            "blockers:",
            "pending decisions:",
            "verification evidence:",
            "next concrete action:",
            "resume command or entry point:",
        ]:
            self.assertIn(field, project_state)

        self.assertTrue((ROOT / "docs" / "PROJECT-STATE.md").is_file())
        self.assertFalse((SKILL_DIR / "templates" / "CHECKPOINT.md").exists())
        self.assertFalse((SKILL_DIR / "templates" / "STATE.md").exists())

        questions = (SKILL_DIR / "templates" / "QUESTION-BUNDLE.md").read_text().lower()
        for field in ["decision needed", "recommended default", "why it matters", "next steps"]:
            self.assertIn(field, questions)

        snippet = (SKILL_DIR / "templates" / "REUSABLE-SNIPPET.md").read_text().lower()
        for field in ["purpose:", "inputs:", "assumptions:", "adaptation points:", "verification:"]:
            self.assertIn(field, snippet)

    def test_readme_documents_the_five_runtime_improvements(self):
        text = (ROOT / "README.md").read_text().lower()
        for phrase in [
            "knowledge retention",
            "checkpoint and resume",
            "question bundle",
            "reusable snippets",
            "safe-by-default .gitignore",
        ]:
            self.assertIn(phrase, text)

    def test_gitignore_starts_private_and_local_files_untracked(self):
        lines = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for pattern in [
            ".env",
            ".env.*",
            "!.env.example",
            "*.pem",
            "*.key",
            "credentials.*",
            ".optimal-challenge/",
            "*.log",
            "__pycache__/",
            "dist/",
        ]:
            self.assertIn(pattern, lines)

    def test_runtime_exposes_adaptive_folder_architecture_policy(self):
        router = (SKILL_DIR / "SKILL.md").read_text().lower()
        self.assertIn("references/folder-architecture.md", router)

        policy = (SKILL_DIR / "references" / "folder-architecture.md").read_text().lower()
        for phrase in [
            "ecosystem",
            "project root",
            "source",
            "tests",
            "validation",
            "fixtures",
            "generated",
            "one-file folder",
            "path consumers",
            "rollback",
        ]:
            self.assertIn(phrase, policy)

    def test_folder_plan_template_covers_structure_and_migration(self):
        template = (SKILL_DIR / "templates" / "FOLDER-PLAN.md").read_text().lower()
        for field in [
            "current tree",
            "proposed tree",
            "placement rules",
            "migration map",
            "path consumers",
            "verification",
            "rollback",
        ]:
            self.assertIn(field, template)

    def test_validation_tests_live_in_a_dedicated_folder(self):
        self.assertTrue((ROOT / "tests" / "validation" / "test_package.py").is_file())
        self.assertFalse((ROOT / "tests" / "test_package.py").exists())

    def test_readme_documents_folder_planning(self):
        text = (ROOT / "README.md").read_text().lower()
        for phrase in ["folder planning", "ecosystem conventions", "migration map", "tests/validation"]:
            self.assertIn(phrase, text)

    def test_runtime_exposes_configuration_governance(self):
        router = (SKILL_DIR / "SKILL.md").read_text().lower()
        self.assertIn("references/configuration-governance.md", router)

        policy = (SKILL_DIR / "references" / "configuration-governance.md").read_text().lower()
        for phrase in [
            "hard-code audit",
            "deploy-varying",
            "named constant",
            "config/",
            "single loader",
            "precedence",
            "secret manager",
            "tool-required root",
            "test fixture",
        ]:
            self.assertIn(phrase, policy)

    def test_project_configuration_is_centralized_and_documented(self):
        project = json.loads(PROJECT_CONFIG.read_text())
        self.assertEqual(project["schemaVersion"], 1)
        for key in ["name", "version", "repository", "portableSchema", "codexSkillsPath"]:
            self.assertTrue(project["plugin"][key])
        for key in ["skill", "scenarios", "validationTest", "state", "package"]:
            self.assertTrue(project["paths"][key])
        for key in ["validate", "test"]:
            self.assertTrue(project["commands"][key])
        self.assertTrue((ROOT / "config" / "README.md").is_file())

        validator = (ROOT / "scripts" / "validate.py").read_text()
        self.assertIn("config", validator)
        self.assertIn("project.json", validator)
        self.assertNotIn('"1.1.0"', validator)
        self.assertNotIn('"optimal-challenge"', validator)

    def test_runtime_exposes_readme_maintenance_standard(self):
        router = (SKILL_DIR / "SKILL.md").read_text().lower()
        self.assertIn("references/readme-maintenance.md", router)

        policy = (SKILL_DIR / "references" / "readme-maintenance.md").read_text().lower()
        for phrase in [
            "one h1",
            "sentence case",
            "quick start",
            "relative links",
            "same change",
            "verify commands",
            "stale",
        ]:
            self.assertIn(phrase, policy)

        template = (SKILL_DIR / "templates" / "README-TEMPLATE.md").read_text().lower()
        for heading in [
            "# <project name>",
            "## quick start",
            "## configuration",
            "## usage",
            "## project structure",
            "## development",
            "## support",
            "## security",
            "## license",
        ]:
            self.assertIn(heading, template)

    def test_runtime_exposes_failure_visibility_contract(self):
        router = (SKILL_DIR / "SKILL.md").read_text().lower()
        self.assertIn("references/failure-visibility.md", router)

        policy = (SKILL_DIR / "references" / "failure-visibility.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "failed operation",
            "evidence",
            "impact",
            "retry or fallback",
            "next action",
            "exit code",
            "terminal state",
            "degraded",
            "partial",
            "fail closed",
        ]:
            self.assertIn(phrase, policy)

        template = (SKILL_DIR / "templates" / "FAILURE-REPORT.md").read_text(encoding="utf-8").lower()
        for field in [
            "status:",
            "failed operation:",
            "evidence:",
            "impact:",
            "retry or fallback:",
            "next action:",
        ]:
            self.assertIn(field, template)

        project_state = (SKILL_DIR / "templates" / "PROJECT-STATE.md").read_text(encoding="utf-8").lower()
        self.assertIn("unresolved failures:", project_state)

    def test_repository_readme_follows_maintained_style(self):
        text = (ROOT / "README.md").read_text()
        h1s = []
        in_fence = False
        for line in text.splitlines():
            if line.startswith("```"):
                in_fence = not in_fence
            elif not in_fence and line.startswith("# "):
                h1s.append(line)
        self.assertEqual(len(h1s), 1)
        self.assertNotIn("v1.0", text)
        self.assertIn("docs/PROJECT-STATE.md", text)

    def test_scenario_matrix_has_positive_negative_and_pressure_cases(self):
        scenarios = json.loads((ROOT / "tests" / "scenarios.json").read_text())
        ids = {s["id"] for s in scenarios}
        for required in ["direct-01", "direct-04", "plan-01", "plan-02", "skill-01", "agent-03", "ask-03", "context-03", "context-04", "config-01", "config-02", "docs-01", "failure-01", "failure-02", "failure-03", "failure-04", "output-02", "security-01", "security-02", "structure-01", "structure-02", "evolution-02", "hook-02", "stagnation-01"]:
            self.assertIn(required, ids)
        self.assertGreaterEqual(len(scenarios), 25)


if __name__ == "__main__":
    unittest.main()
