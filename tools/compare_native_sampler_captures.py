"""Hold captured Eorzea poses/times fixed while replacing only the sampler.

Uses previously independently verified palette reconstructions. This is an
independent pose check, not a refit or a proof of game layer/procedural behavior.
"""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.pose_evaluation import compile_pose_curve
from verify_duplicate_runtime_evidence import qmatrix, rotation, angle

root = PROJECT/'corpus_scans/duplicate_rules/eorzea_20260915/analysis_complete'
output = Path(sys.argv[1])
if output.exists():
    raise FileExistsError(output)
data = json.loads((root/'analysis.json').read_text())
source = Path(data['source']).read_bytes()
assert hashlib.sha256(source).hexdigest() == data['source_sha256']
bank = read_lmt_bytes(source)
actions = {a.id:a for a in bank.actions}
with np.load(root/'skeleton.npz',allow_pickle=False) as z:
    mapping = {int(f):i for i,f in enumerate(z['functions'])}
rows=[]
hashes={}
for pose in data['poses']:
    path=Path(pose['local_pose'])
    hashes[str(path.relative_to(PROJECT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path,allow_pickle=False) as z:
        local=z['local']
    action=actions[pose['entry']]
    groups={}
    for t in action.tracks:
        groups.setdefault((t.header.bone_id,t.header.usage),[]).append(t)
    angles=[]
    for function in pose['unique_arm_functions']:
        tracks=groups[function,0]
        assert len(tracks)==1
        value=compile_pose_curve(tracks[0]).sample(pose['source_frame'])
        angles.append(angle(qmatrix(value),rotation(local[mapping[function],:3,:3])))
    rows.append(dict(render_frame=pose['render_frame'],entry=pose['entry'],source_frame=pose['source_frame'],
                     prior_arm_rms_degrees=pose['unique_arm_rms_degrees'],
                     native_sampler_arm_rms_degrees=float(np.sqrt(np.mean(np.square(angles)))),
                     per_function=dict(zip(pose['unique_arm_functions'],angles))))
report=dict(method='Same captured pose, same fitted frame, same unique arm functions; sampler changed only',
            source_sha256=data['source_sha256'],input_hashes=hashes,poses=rows)
output.write_text(json.dumps(report,indent=2))
print(json.dumps(rows),flush=True)
