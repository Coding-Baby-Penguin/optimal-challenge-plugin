from __future__ import annotations

import json
import re
import subprocess
import sys
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

    def test_release_120_metadata_and_integrated_paths_are_canonical(self):
        project = json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(project["plugin"]["version"], "1.2.0")

        expected_paths = {
            "orchestrationConfig": "config/orchestration.json",
            "orchestrationSchema": "config/orchestration.schema.json",
            "teamRegistrySchema": "config/team-registry.schema.json",
            "allocationLedgerSchema": "config/allocation-ledger.schema.json",
            "routingScenarios": "tests/team-routing.json",
            "researchGateScenarios": "tests/research-gate.json",
            "researchEvidenceFixture": "tests/fixtures/research/trusted-evidence.json",
            "behavioralScenarios": "tests/behavioral-acceptance.json",
            "evaluationManifest": "tests/evaluation-manifest.json",
            "routingEvaluator": "scripts/evaluate_routing.py",
            "researchGateEvaluator": "scripts/evaluate_research_gate.py",
            "behavioralEvaluator": "scripts/evaluate_behavior.py",
            "orchestrationValidator": "scripts/validate_orchestration.py",
            "capabilityValidator": "scripts/capability_matrix.py",
        }
        for key, relative_path in expected_paths.items():
            self.assertEqual(project["paths"].get(key), relative_path, key)
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

        manifests = [
            json.loads((ROOT / "plugin.json").read_text(encoding="utf-8")),
            json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")),
            json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8")),
        ]
        self.assertEqual({manifest["version"] for manifest in manifests}, {"1.2.0"})
        claude_marketplace = json.loads(
            (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(claude_marketplace["plugins"][0]["version"], "1.2.0")

        codex_marketplace = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )
        codex_entry = codex_marketplace["plugins"][0]
        self.assertNotIn("version", codex_entry)
        self.assertEqual(
            codex_entry["source"],
            {"source": "local", "path": "./"},
        )
        self.assertEqual(
            codex_entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertEqual(codex_entry["category"], "Productivity")

    def test_integrated_validator_runs_task_one_through_seven_structural_gates(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for evidence in [
            "Orchestration configuration: PASSED",
            "Team routing: PASSED",
            "Orchestration state: PASSED",
            "Capability contracts: PASSED",
            "Behavioral structure: PASSED",
            "Fresh-host behavioral acceptance: UNVERIFIED (Task 10)",
        ]:
            self.assertIn(evidence, result.stdout)

    def test_canonical_test_command_cannot_narrow_repository_discovery(self):
        project = json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(project["commands"]["test"], "python -m unittest discover -v")

    def test_integrated_capability_gate_validates_rows_and_fail_closed_resolution(self):
        from scripts import capability_matrix

        validator = getattr(capability_matrix, "validate_capability_contracts", None)
        self.assertTrue(callable(validator), "capability contract validator is missing")
        documents = {
            name: (SKILL_DIR / "references" / name).read_text(encoding="utf-8")
            for name in ("platform-codex.md", "platform-claude.md")
        }
        self.assertEqual(validator(ROOT, documents=documents), [])

        mutated = dict(documents)
        mutated["platform-codex.md"] = mutated["platform-codex.md"].replace(
            "| codex-local | Native resume | policy-only | policy:host-resume-probe | policy:codex-local/native-resume | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | rehydrate |",
            "| codex-local | Native resume | policy-only | policy:host-resume-probe | policy:codex-local/native-resume | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | inline |",
            1,
        )
        self.assertIn("fallback", " ".join(validator(ROOT, documents=mutated)).lower())

        def permissive_resolver(surface, live, acceptance, policy, now):
            return {
                "surface_id": surface,
                "capability": policy["capability"],
                "support_level": "policy-only",
                "required_fallback": policy["required_fallback"],
                "evidence_source": "policy_declaration",
            }

        resolver_errors = validator(ROOT, documents=documents, resolver=permissive_resolver)
        self.assertIn("fail closed", " ".join(resolver_errors).lower())

    def test_adversarial_team_scan_covers_router_and_all_lazy_policy_modules(self):
        from scripts import adversarial_review

        detector = getattr(adversarial_review, "unconditional_costly_behavior_issues", None)
        self.assertTrue(callable(detector), "whole-policy costly-behavior detector is missing")
        policies = {"SKILL.md": (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")}
        policies.update({
            path.name: path.read_text(encoding="utf-8")
            for path in (SKILL_DIR / "references").glob("*.md")
        })
        self.assertEqual(detector(policies), [])

        spawn_mutation = dict(policies)
        spawn_mutation["team-orchestration.md"] += "\nAlways spawn a specialist team.\n"
        self.assertIn("team-orchestration.md", " ".join(detector(spawn_mutation)))

        review_mutation = dict(policies)
        review_mutation["verification.md"] += "\nReview every task independently.\n"
        self.assertIn("verification.md", " ".join(detector(review_mutation)))

    def test_readme_documents_120_upgrade_and_compatibility_contract(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        semantic_text = text.replace("`", "")
        self.assertIn("## upgrade and compatibility", text)
        for phrase in [
            "codex plugin add optimal-challenge@optimal-challenge-local",
            "claude plugin update optimal-challenge@optimal-challenge-marketplace",
            "balanced remains the default",
            "additive task-capsule.yaml fields",
            "platform-codex.md and platform-claude.md filenames remain stable",
            ".optimal-challenge/ remains ignored and reconstructable",
            "docs/project-state.md remains the only canonical project state",
            "fresh-host behavioral acceptance remains `unverified`",
        ]:
            self.assertIn(phrase.replace("`", ""), semantic_text)

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

    def test_router_lazily_exposes_agent_team_policy_after_direct_gate(self):
        router = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
        references = [
            "premise-validation.md",
            "team-orchestration.md",
            "team-continuity.md",
            "cost-quality-routing.md",
        ]
        for reference in references:
            self.assertIn(f"references/{reference}", router)
            self.assertTrue((SKILL_DIR / "references" / reference).is_file(), reference)

        direct_gate = router.index("stable, single-step, and low-risk")
        premise_gate = router.index("premise")
        self.assertLess(direct_gate, premise_gate)
        self.assertIn("only after", router)
        self.assertIn("real multi-workstream", router)
        self.assertIn("explicit", router)
        self.assertNotIn("always create a team", router)
        self.assertNotIn("always ask which profile", router)

        direct_rule = next(
            line for line in router.splitlines()
            if line.startswith("2.") and "stable, single-step, and low-risk" in line
        )
        for constraint in ["explicit team", "exact-specialist", "independent-review", "non-inline"]:
            self.assertIn(constraint, direct_rule)
        self.assertRegex(direct_rule, r"direct.*only when|only when.*direct")

    def test_premise_policy_optimizes_question_quality(self):
        text = (SKILL_DIR / "references" / "premise-validation.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "premiserisk",
            "questionvalue",
            "wrongnesslikelihoodrating",
            "expectedreworkavoided",
            "userattentioncost",
            "investigate",
            "reversible default",
            "decision id",
            "contradictory evidence",
            "question bundle",
            "safe work",
        ]:
            self.assertIn(phrase, text)
        self.assertIn("premiserisk >= 4", text)
        self.assertIn("questionvalue > 0", text)
        self.assertIn("never re-ask", text)

    def test_high_cost_research_gate_is_lazy_bounded_and_evidence_bearing(self):
        router = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertIn("references/high-cost-research.md", router)

        text = (SKILL_DIR / "references" / "high-cost-research.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "materially costly",
            "success criteria are not established",
            "authoritative",
            "provenance",
            "contradictory evidence",
            "stop condition",
            "observable acceptance rubric",
            "smallest adequate",
            "risk-representative",
            "deterministic checks",
            "user-only",
            "question bundle",
            "provisional",
            "unverified",
            "acceptance-ready",
            "preference",
            "durable cloud persistence",
            "budget enforcement",
        ]:
            self.assertIn(phrase, text)
        self.assertRegex(text, r"low-cost[^.]+reversible[^.]+direct")
        self.assertRegex(text, r"research[^.]+and[^.]+pilot")
        self.assertRegex(text, r"pilot[^.]+pass[^.]+before[^.]+scal")
        self.assertNotRegex(text, r"(?:exactly|always|must use)\s+(?:two|three|2|3)\s+(?:samples|stickers|images)")

    def test_high_cost_research_scenarios_cover_scale_and_truth_boundaries(self):
        scenarios = {
            scenario["id"]: scenario
            for scenario in json.loads((ROOT / "tests" / "scenarios.json").read_text(encoding="utf-8"))
        }
        contracts = {
            "scale-sticker-01": {
                "tokens": ["sticker pack", "rejected", "criteria"],
                "expect": "research-rubric-and-varied-risk-representative-pilot-before-full-pack",
                "modules": {"premise-validation", "high-cost-research"},
            },
            "scale-paid-01": {
                "tokens": ["120", "paid", "success criteria"],
                "expect": "research-rubric-and-smallest-adequate-risk-representative-pilot-before-paid-scale",
                "modules": {"premise-validation", "high-cost-research"},
            },
            "scale-low-cost-01": {
                "tokens": ["single disposable sticker", "cheap", "reversible"],
                "expect": "direct-without-research-or-pilot-gate",
                "modules": set(),
            },
            "scale-rubric-01": {
                "tokens": ["authoritative rubric", "batch", "pilot"],
                "expect": "skip-redundant-research-but-run-risk-representative-pilot",
                "modules": {"high-cost-research"},
            },
            "scale-settled-pilot-01": {
                "tokens": ["approved pilot", "same rubric", "scale"],
                "expect": "reuse-settled-pilot-evidence-without-reasking",
                "modules": {"high-cost-research"},
            },
            "scale-skip-pressure-01": {
                "tokens": ["skip research", "full batch", "acceptance-ready"],
                "expect": "only-safe-provisional-unverified-output-not-acceptance-ready",
                "modules": {"high-cost-research", "failure-visibility"},
            },
            "scale-stop-01": {
                "tokens": ["research", "stop condition", "authoritative"],
                "expect": "bounded-research-stops-when-rubric-can-decide-pilot",
                "modules": {"high-cost-research"},
            },
            "scale-settings-truth-01": {
                "tokens": ["task override", "cloud", "budget enforcement"],
                "expect": "treat-override-as-guidance-not-persistence-or-enforcement-proof",
                "modules": {"high-cost-research", "failure-visibility"},
            },
        }
        for scenario_id, contract in contracts.items():
            self.assertIn(scenario_id, scenarios)
            scenario = scenarios[scenario_id]
            prompt = scenario["prompt"].lower()
            self.assertTrue(all(token in prompt for token in contract["tokens"]), scenario_id)
            self.assertEqual(scenario["expect"], contract["expect"])
            self.assertEqual(set(scenario["modules"]), contract["modules"], scenario_id)

    def test_readme_documents_research_before_scale_contract(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "research before scale",
            "smallest adequate",
            "provisional",
            "evaluate_research_gate.py",
        ]:
            self.assertIn(phrase, text)

    def test_team_policy_preserves_invocation_authority_and_budget_truth(self):
        orchestration = (SKILL_DIR / "references" / "team-orchestration.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "inline-only",
            "team-requested",
            "exact specialist",
            "0 to 32",
            "min(32, detected_host_max)",
            "strong-benefit requirement",
            "ambiguous",
            "one concise",
            "coordinator",
            "sole user-facing",
            "cannot ask the user",
            "cannot expand scope",
            "cannot spawn",
            "task-capsule.yaml",
            "return-capsule.yaml",
            "advisory ceiling",
            "observed",
            "estimated",
            "unavailable",
            "integration reserve",
            "mandatory-review reserve",
            "workers cannot transfer",
            "unfinished",
            "profile is surfaced only",
        ]:
            self.assertIn(phrase, orchestration)
        self.assertIn("config/orchestration.json", orchestration)
        self.assertIn(".optimal-challenge/orchestration.local.json", orchestration)
        self.assertIn("system", orchestration)
        self.assertIn("current-request", orchestration)
        self.assertNotIn("hard budget", orchestration)

    def test_mandatory_enforcement_requires_external_capability_or_stops_before_spend(self):
        text = (SKILL_DIR / "references" / "team-orchestration.md").read_text(encoding="utf-8").lower()
        for field in [
            "verifiedcapabilitycontext",
            "exact surface/version",
            "provenance",
            "evidence",
            "freshness",
            "observed counter",
            "matching stop primitive",
        ]:
            self.assertIn(field, text)
        self.assertIn("cannot come from task, local, or committed configuration", text)
        self.assertRegex(text, r"mandatory[^.]+enforcement[^.]+(?:blocked|one route/limit decision)[^.]+before any spend")
        self.assertRegex(text, r"advisory[^.]+only after[^.]+explicit user acceptance")

    def test_team_policy_requires_executable_loader_and_state_validation(self):
        text = (SKILL_DIR / "references" / "team-orchestration.md").read_text(encoding="utf-8").lower()
        for contract in [
            "scripts/orchestration_config.py",
            "load_effective_config",
            "config/team-registry.schema.json",
            "config/allocation-ledger.schema.json",
            "scripts/validate_orchestration.py",
        ]:
            self.assertIn(contract, text)
        self.assertIn("never manually merge", text)
        self.assertRegex(
            text,
            r"before dispatch, reservation, or reconciliation[^.]+scripts/validate_orchestration\.py",
        )

    def test_team_continuity_and_cost_quality_policy_match_calculation_contracts(self):
        continuity = (SKILL_DIR / "references" / "team-continuity.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "resume",
            "rehydrate",
            "fresh",
            "logical teammate",
            "not the same thing as a retained full conversation",
            "disposable runtime state",
            "project-state.md",
            "source files",
            "independence",
        ]:
            self.assertIn(phrase, continuity)

        routing = (SKILL_DIR / "references" / "cost-quality-routing.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "d(t)",
            "b_parallel",
            "c_review_rework",
            "strong benefit",
            "economy",
            "balanced",
            "quality",
            "custom",
            "totaljobcost",
            "criticalpathlatency",
            "userinterruptioncost",
            "expectedreworkrisk",
            "observed",
            "estimated",
            "unknown",
            "ties stay inline",
        ]:
            self.assertIn(phrase, routing)
        self.assertIn("never delegate merely because", routing)

    def test_selective_review_policy_blocks_unavailable_mandatory_review(self):
        text = (SKILL_DIR / "references" / "verification.md").read_text(encoding="utf-8").lower()
        for phrase in [
            "reviewvalue",
            "p(defect)",
            "reviewcost",
            "mandatory independent review",
            "blocked",
            "compensating oracle",
            "explicitly accepts",
            "authoritative inputs",
        ]:
            self.assertIn(phrase, text)

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

    def test_scenario_matrix_covers_agent_team_policy_boundaries(self):
        scenarios = json.loads((ROOT / "tests" / "scenarios.json").read_text(encoding="utf-8"))
        ids = {scenario["id"] for scenario in scenarios}
        required = {
            "premise-investigate-01", "premise-default-01", "premise-ask-01",
            "invocation-inline-01", "invocation-auto-01", "invocation-team-01",
            "invocation-exact-01", "invocation-conflict-01", "continuity-resume-01",
            "continuity-rehydrate-01", "continuity-fresh-01", "review-unavailable-01",
            "budget-advisory-01", "question-settled-01",
            "direct-explicit-team-01", "budget-mandatory-unsupported-01",
            "budget-mandatory-accepted-advisory-01", "invocation-ambiguous-team-01",
            "continuity-stale-failed-01",
        }
        self.assertTrue(required <= ids, sorted(required - ids))

    def test_agent_team_pressure_scenarios_encode_trigger_route_and_modules(self):
        scenarios = {
            scenario["id"]: scenario
            for scenario in json.loads((ROOT / "tests" / "scenarios.json").read_text(encoding="utf-8"))
        }
        contracts = {
            "direct-explicit-team-01": {
                "tokens": ["trivial", "exactly two specialists"],
                "expect": "explicit-non-inline-constraint-bypasses-direct-fast-path",
                "modules": {"team-orchestration", "cost-quality-routing"},
            },
            "budget-mandatory-unsupported-01": {
                "tokens": ["mandatory", "no verified stop primitive", "before spending"],
                "expect": "block-or-ask-one-route-limit-decision-before-spend",
                "modules": {"team-orchestration", "failure-visibility"},
            },
            "budget-mandatory-accepted-advisory-01": {
                "tokens": ["explicitly accept", "advisory"],
                "expect": "degraded-advisory-route-after-explicit-acceptance",
                "modules": {"team-orchestration", "failure-visibility"},
            },
            "invocation-ambiguous-team-01": {
                "tokens": ["team of three", "cost"],
                "expect": "resolve-from-context-or-ask-one-material-count-question",
                "modules": {"team-orchestration"},
            },
            "continuity-stale-failed-01": {
                "tokens": ["stale", "failed", "resume"],
                "expect": "validate-quarantine-and-rehydrate-fresh-or-block-not-blind-resume",
                "modules": {"team-continuity", "failure-visibility"},
            },
        }
        for scenario_id, contract in contracts.items():
            self.assertIn(scenario_id, scenarios)
            scenario = scenarios[scenario_id]
            prompt = scenario["prompt"].lower()
            self.assertTrue(all(token in prompt for token in contract["tokens"]), scenario_id)
            self.assertEqual(scenario["expect"], contract["expect"])
            self.assertTrue(contract["modules"] <= set(scenario["modules"]), scenario_id)


if __name__ == "__main__":
    unittest.main()
