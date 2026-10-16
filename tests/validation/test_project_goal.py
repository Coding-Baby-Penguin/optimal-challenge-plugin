"""Real filesystem/CLI checks; semantic decisions are explicit reviewer inputs."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'project_goal.py'

class ProjectGoalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'Tools' / 'AI Continuity'
        self.root.mkdir(parents=True)
        self.target = self.root / 'ai-continuity' / 'src' / 'fix.js'
        self.target.parent.mkdir(parents=True)
        self.goal = self.root / 'Codex' / 'context' / 'goal.md'
        self.goal.parent.mkdir(parents=True)
        self.instruction = self.root / 'AGENTS.md'
        self.instruction.write_text('Project ID: ai-continuity\nProject boundary: .\nGoal: Codex/context/goal.md\n')
        self.contract = dict(schema_version=1, project_id='ai-continuity', project_root='../..',
            status='CONFIRMED', purpose='Lightweight task continuity', sources=['owner:confirmed'],
            in_scope=['Task/status updates'], out_of_scope=['Document store'],
            acceptance=[dict(id='G1', outcome='Durable task update', evidence_required='Actual durable readback')])
        self.write_goal()

    def write_goal(self):
        self.goal.write_text('# Goal\n```json\n' + json.dumps(self.contract) + '\n```\n')

    def run_check(self, stage='planning', **overrides):
        args = dict(instruction=str(self.instruction), project_id='ai-continuity', target=str(self.target),
                    stage=stage, criterion='G1', alignment='in-scope', contribution='Fix durable update regression')
        if stage != 'planning':
            args['planned_hash'] = hashlib.sha256(self.goal.read_bytes()).hexdigest() if self.goal.exists() else '0'*64
        if stage == 'completion':
            self.artifact = self.root / 'Codex' / 'evidence.txt'
            self.artifact.write_text('Actual durable readback receipt')
            args['artifact'] = str(self.artifact)
        args.update(overrides)
        command = [sys.executable, '-B', str(SCRIPT)]
        for name, value in args.items():
            command.extend(['--'+name.replace('_', '-'), str(value)])
        return subprocess.run(command, capture_output=True, text=True)

    def test_checker_exists(self):
        self.assertTrue(SCRIPT.is_file(), 'project-specific goal checker is absent')

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_normal_nested_work_at_all_four_boundaries(self):
        for stage in ('planning','delegation','implementation','completion'):
            result = self.run_check(stage)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            receipt=json.loads(result.stdout)
            self.assertEqual(receipt['stage'], stage)
            self.assertEqual(receipt['goal_path'], str(self.goal.resolve()))

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_wrong_project_and_prefix_collision(self):
        for target in (self.root.parent/'ExpensePulse'/'fix.js', self.root.parent/'AI Continuity2'/'fix.js'):
            result=self.run_check(target=target)
            self.assertEqual(result.returncode, 2)
            self.assertIn('target outside project', result.stdout)
        result=self.run_check(project_id='drawio')
        self.assertEqual(result.returncode,2)
        self.assertIn('project identity mismatch',result.stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_missing_goal_never_falls_back_to_parent(self):
        self.goal.unlink()
        (self.root.parent/'goal.md').write_text('Parent Tools goal')
        result=self.run_check()
        self.assertEqual(result.returncode,2)
        self.assertIn('missing or unreadable goal',result.stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_unconfirmed_conflicting_parked_and_wrong_root(self):
        for status in ('DRAFT','CONFLICT','PARKED'):
            self.contract['status']=status; self.write_goal()
            result=self.run_check()
            self.assertEqual(result.returncode,2)
            self.assertIn(status,result.stdout)
        self.contract['status']='CONFIRMED'; self.contract['project_root']='../../..'; self.write_goal()
        self.assertIn('goal root mismatch',self.run_check().stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_stale_hash_requires_reconciliation(self):
        planned=hashlib.sha256(self.goal.read_bytes()).hexdigest()
        self.goal.write_text(self.goal.read_text()+'Owner correction\n')
        for stage in ('delegation','implementation','completion'):
            result=self.run_check(stage, planned_hash=planned)
            self.assertEqual(result.returncode,2)
            self.assertIn('goal changed',result.stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_scope_drift_and_missing_criterion_hold(self):
        for alignment in ('scope-change','conflict','unreviewed'):
            result=self.run_check(alignment=alignment,contribution='Add document store / Drawio UI gate')
            self.assertEqual(result.returncode,2)
        self.assertIn('unknown criterion',self.run_check(criterion='G9').stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_completion_requires_readable_evidence(self):
        result=self.run_check('completion',artifact=self.root/'absent.txt')
        self.assertEqual(result.returncode,2)
        self.assertIn('missing or unreadable evidence',result.stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_duplicate_contract_and_schema_hold(self):
        self.goal.write_text(self.goal.read_text()*2)
        self.assertIn('one JSON contract',self.run_check().stdout)
        self.contract['schema_version']=2; self.write_goal()
        self.assertIn('unsupported schema',self.run_check().stdout)

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_malformed_structures_return_hold_instead_of_traceback(self):
        for contract in (None, [], 'goal', dict(self.contract, acceptance=['G1']),
                         dict(self.contract, sources='owner'), dict(self.contract, acceptance=[{}])):
            self.contract=contract; self.write_goal()
            result=self.run_check()
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'HOLD')

    @unittest.skipUnless(SCRIPT.is_file(), 'checker absent: baseline')
    def test_goal_escape_and_distinct_nested_boundary_hold(self):
        self.instruction.write_text('Project ID: ai-continuity\nProject boundary: .\nGoal: ../goal.md\n')
        self.assertIn('goal outside project',self.run_check().stdout)
        self.instruction.write_text('Project ID: ai-continuity\nProject boundary: .\nGoal: Codex/context/goal.md\n')
        (self.target.parent/'AGENTS.md').write_text('Project ID: expensepulse\n')
        self.assertIn('nested project boundary',self.run_check().stdout)

if __name__ == '__main__':
    unittest.main()
