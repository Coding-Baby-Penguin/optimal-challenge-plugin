"""Explicit local goal check. No host interception or semantic inference."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

STAGES = ('planning', 'delegation', 'implementation', 'completion')

def inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents

def field(text: str, name: str) -> str:
    values = re.findall(r'^' + re.escape(name) + r':\s*(.+?)\s*$', text, re.MULTILINE)
    if len(values) != 1:
        raise ValueError('instruction requires one ' + name)
    return values[0].strip('`')

def read(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError('missing or unreadable ' + label + ': ' + str(path)) from exc

def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field: ' + key)
        result[key] = value
    return result

def check(args) -> dict:
    instruction = Path(args.instruction).resolve()
    text = read(instruction, 'instruction').decode('utf-8-sig')
    if field(text, 'Project ID') != args.project_id:
        raise ValueError('project identity mismatch in instruction')
    root = (instruction.parent / field(text, 'Project boundary')).resolve()
    goal = (instruction.parent / field(text, 'Goal')).resolve()
    target = Path(args.target).resolve()
    if not inside(goal, root):
        raise ValueError('goal outside project')
    if not inside(target, root):
        raise ValueError('target outside project')
    # A nested explicit boundary must bind to this same project; never inherit it.
    parent = target if target.is_dir() else target.parent
    while parent != root:
        for filename in ('AGENTS.md', 'CLAUDE.md', 'goal.md'):
            nested = parent / filename
            if nested.is_file() and nested != instruction and nested != goal:
                data = read(nested, 'nested instruction').decode('utf-8-sig')
                if filename == 'goal.md':
                    raise ValueError('nested project boundary requires its own goal check')
                if field(data, 'Project ID') != args.project_id:
                    raise ValueError('nested project boundary mismatch')
                nested_root = (parent / field(data, 'Project boundary')).resolve()
                nested_goal = (parent / field(data, 'Goal')).resolve()
                if nested_root != root or nested_goal != goal:
                    raise ValueError('nested project boundary mismatch')
        parent = parent.parent
    raw = read(goal, 'goal')
    contracts = re.findall(r'^```json\s*\n(.*?)^```\s*$', raw.decode('utf-8-sig'), re.MULTILINE | re.DOTALL)
    if len(contracts) != 1:
        raise ValueError('goal requires one JSON contract')
    contract = json.loads(contracts[0], object_pairs_hook=unique_json)
    if not isinstance(contract, dict):
        raise ValueError('goal contract must be a JSON object')
    if type(contract.get('schema_version')) is not int or contract.get('schema_version') != 1:
        raise ValueError('unsupported schema')
    if contract.get('project_id') != args.project_id:
        raise ValueError('project identity mismatch in goal')
    if (goal.parent / contract.get('project_root', '')).resolve() != root:
        raise ValueError('goal root mismatch')
    if contract.get('status') != 'CONFIRMED':
        raise ValueError('goal status ' + str(contract.get('status')) + ': reconcile affected work only')
    for name in ('purpose', 'sources', 'in_scope', 'acceptance'):
        if not contract.get(name):
            raise ValueError('goal missing ' + name)
    if not isinstance(contract['purpose'], str) or not contract['purpose'].strip():
        raise ValueError('goal purpose must be nonblank text')
    for name in ('sources', 'in_scope', 'acceptance'):
        if not isinstance(contract[name], list):
            raise ValueError('goal ' + name + ' must be a list')
    for item in contract['acceptance']:
        if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip()
                                             for key in ('id', 'outcome', 'evidence_required')):
            raise ValueError('each acceptance criterion needs id, outcome and evidence_required text')
    criteria = {item['id'] for item in contract['acceptance']}
    if len(criteria) != len(contract['acceptance']):
        raise ValueError('duplicate criterion ID')
    if args.criterion not in criteria:
        raise ValueError('unknown criterion: ' + args.criterion)
    digest = hashlib.sha256(raw).hexdigest()
    if args.stage != 'planning' and not args.planned_hash:
        raise ValueError('planned goal hash required')
    if args.planned_hash and args.planned_hash != digest:
        raise ValueError('goal changed: reread and reconcile the plan')
    if args.alignment != 'in-scope':
        raise ValueError('direction review holds ' + args.alignment)
    if not args.contribution.strip():
        raise ValueError('criterion contribution required')
    evidence = None
    if args.stage == 'completion':
        if not args.artifact:
            raise ValueError('completion evidence required')
        evidence_path = Path(args.artifact).resolve()
        evidence_bytes = read(evidence_path, 'evidence')
        if not evidence_bytes:
            raise ValueError('empty evidence')
        evidence = dict(path=str(evidence_path), sha256=hashlib.sha256(evidence_bytes).hexdigest())
    return dict(status='PASS_LOCAL_CHECK', project_id=args.project_id, project_root=str(root),
        instruction_path=str(instruction), goal_path=str(goal), goal_sha256=digest,
        goal_status=contract['status'], sources=contract['sources'], stage=args.stage,
        criterion_ids=[args.criterion], alignment=args.alignment, contribution=args.contribution,
        evidence=evidence, limitation='Semantic alignment/evidence sufficiency are reviewer decisions; no host interception.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('instruction','project-id','target','criterion','alignment','contribution'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--planned-hash')
    parser.add_argument('--artifact')
    args = parser.parse_args()
    try:
        receipt = check(args)
    except (ValueError, KeyError, TypeError, UnicodeError, OSError) as exc:
        print(json.dumps(dict(status='HOLD', stage=args.stage, reason=str(exc))))
        return 2
    print(json.dumps(receipt, ensure_ascii=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
