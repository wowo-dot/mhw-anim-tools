"""Check the implemented binding plan against all saved native loop results."""
import collections
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.pose_evaluation import compile_pose_evaluation

root = PROJECT/'corpus_scans/duplicate_rules/native_evaluator_20260915'
source = Path(sys.argv[1])
output = Path(sys.argv[2])
if output.exists():
    raise FileExistsError(output)
native = json.loads((root/'tracked_tool_corpus.json').read_text())
hashes = {row['bank']:row['sha256'] for row in native['sources']}
by_bank = collections.defaultdict(list)
for row in native['results']:
    by_bank[row['bank']].append(row)
count = calls = 0
unsupported = []
for path, cases in by_bank.items():
    data = (source/path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == hashes[path]
    bank = read_lmt_bytes(data, source_name=str(source/path))
    actions = {a.id:a for a in bank.actions}
    for row in cases:
        mapping = {i:str(i) for i in row['replays'][0]['mapped_function_ids']}
        plan = compile_pose_evaluation(actions[row['entry']],mapping,version=bank.header.version)
        selected = sorted(b.source_index for b in plan.bindings)
        for replay in row['replays']:
            assert selected == replay['selected_slots'], (path,row['entry'],replay['binder'])
            assert sum(len(b.source_indices) for b in plan.bindings) == replay['bindings']
            calls += 1
        if not plan.supported:
            unsupported.append(dict(bank=path,entry=row['entry'],errors=[d.message for d in plan.diagnostics if d.level=='ERROR']))
        count += 1
report = dict(actions=count, native_binding_comparisons=calls,
              duplicate_actions=sum(row['kind']=='duplicate' for row in native['results']),
              ordinary_actions=sum(row['kind']=='ordinary' for row in native['results']),
              source_banks=len(by_bank), unsupported_sampling=unsupported,
              native_reference_sha256=hashlib.sha256((root/'tracked_tool_corpus.json').read_bytes()).hexdigest())
output.write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
