"""Run with existing qrenderdoc --python; request JSON path is MHW_RD_REQUEST.

MHW_RD_PROJECT must name this checkout. qrenderdoc does not define __file__.

Modes: probe (connect/read metadata only), capture (exact PID, one frame).
No launch, injection, forced connection takeover, or global hook occurs here.
"""

import datetime
import json
import os
from pathlib import Path
import sys
import time
import traceback

import renderdoc as rd

root = Path(os.environ['MHW_RD_PROJECT']).resolve() / 'corpus_scans'


def inside_workspace(path):
    # The existing RenderDoc 1.46 embeds Python 3.8.
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


request_path = Path(os.environ['MHW_RD_REQUEST']).resolve()
if not inside_workspace(request_path):
    raise ValueError('Request must live inside this checkout/corpus_scans.')
request = json.loads(request_path.read_text(encoding='utf-8-sig'))
destination = Path(request['report']).resolve()
if not inside_workspace(destination):
    raise ValueError('Report must live inside this checkout/corpus_scans.')
if request['mode'] not in ('probe', 'capture'):
    raise ValueError('Unknown mode')
if request['mode'] == 'capture' and not request.get('expected_pid'):
    raise ValueError('Capture requires the exact expected game PID.')
report = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              mode=request['mode'], targets=[], status='starting')
target = None


def save():
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


save()
try:
    ident = rd.EnumerateRemoteTargets('localhost', 0)
    while ident:
        candidate = rd.CreateTargetControl('localhost', ident, 'LMT duplicate investigation', False)
        if candidate:
            row = dict(ident=ident, connected=candidate.Connected(), target=candidate.GetTarget(),
                       pid=candidate.GetPID(), api=candidate.GetAPI())
            report['targets'].append(row)
            if (row['connected'] and row['target'] == 'MonsterHunterWorld'
                    and (not request.get('expected_pid') or row['pid'] == request['expected_pid'])):
                target = candidate
                break
            candidate.Shutdown()
        ident = rd.EnumerateRemoteTargets('localhost', ident)
    if target is None:
        raise RuntimeError('No matching active MHW RenderDoc target.')
    report['status'] = 'connected'
    save()
    if request['mode'] == 'capture':
        prior = set()
        report['previous_captures'] = []
        quiet = 0
        deadline = time.monotonic() + 3
        while quiet < 5 and time.monotonic() < deadline:
            message = target.ReceiveMessage(None)
            if message.type == rd.TargetControlMessageType.NewCapture:
                cap = message.newCapture
                prior.add((cap.captureId, cap.frameNumber))
                report['previous_captures'].append(dict(path=cap.path, frame=cap.frameNumber,
                                                        id=cap.captureId, bytes=cap.byteSize))
                quiet = 0
            elif message.type == rd.TargetControlMessageType.Noop:
                quiet += 1
                time.sleep(.05)
        target.TriggerCapture(1)
        report['status'] = 'capture_requested'
        save()
        deadline = time.monotonic() + 45
        while target.Connected() and time.monotonic() < deadline:
            message = target.ReceiveMessage(None)
            if message.type == rd.TargetControlMessageType.NewCapture:
                cap = message.newCapture
                if (cap.captureId, cap.frameNumber) in prior:
                    continue
                report['capture'] = dict(path=cap.path, frame=cap.frameNumber,
                                         id=cap.captureId, bytes=cap.byteSize)
                report['status'] = 'captured'
                break
            if message.type == rd.TargetControlMessageType.Noop:
                time.sleep(.05)
        if report['status'] != 'captured':
            report['status'] = 'capture_timeout'
except Exception:
    report['status'] = 'failed'
    report['error'] = traceback.format_exc()
finally:
    save()
    if target:
        target.Shutdown()
sys.exit(0 if report['status'] in ('connected', 'captured') else 1)
