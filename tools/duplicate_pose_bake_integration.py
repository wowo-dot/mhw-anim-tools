"""Example adapter for a worker; no auto-installation or production file writes.

Run within Blender with this checkout installed/importable as mhw_anim_tools.
The callback is the caller's existing qualified retarget/keying step. The helper
is a native source rig, not a new retargeting solver or a G8F rest-pose conversion.
"""
from mhw_anim_tools.blender_adapter.pose_helpers import create_evaluated_helper, dispose_evaluated_helper
from mhw_anim_tools.core.formats.lmt.source_bank import LmtSourceBankCache


def bake_source_clip(cache, source_path, entry_id, native_template, consume_frame,
                     *, base_policy, base_action=None, subframes=(0.0,)):
    bank = cache.load(source_path)
    helper = create_evaluated_helper(bank, entry_id, native_template,
        base_policy=base_policy, base_action=base_action, create_raw_action=False)
    try:
        count = helper.evaluation.source.header.frame_count
        for frame in range(count):
            for fraction in subframes:
                time = frame + float(fraction)
                if time > count - 1:
                    continue
                evaluated = helper.set_frame(time)
                consume_frame(time, evaluated)  # Copy matrices before the next frame.
        return dict(source_sha256=bank.sha256, frame_count=count,
                    loop_frame=helper.evaluation.source.header.loop_frame,
                    binding_rule=helper.action['mhw_anim_tools_pose_rule'])
    finally:
        dispose_evaluated_helper(helper)


def new_worker_cache():
    return LmtSourceBankCache(max_banks=2, max_bytes=512*1024*1024)
