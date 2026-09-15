# Baking integration — CPU pose helpers, v1.1.0

The implemented API is `blender_adapter.pose_helpers.create_evaluated_helper`.
Use the **native MHW source skeleton** as its template, then feed its evaluated
matrices into the existing qualified G8F/Lara retargeting step. A G8F target rig
is not a substitute for the source template.

```python
from mhw_anim_tools.core.formats.lmt.source_bank import LmtSourceBankCache
from mhw_anim_tools.blender_adapter.pose_helpers import (
    create_evaluated_helper, dispose_evaluated_helper,
)

# Construct inside each Blender worker.
cache = LmtSourceBankCache(max_banks=2, max_bytes=512 * 1024 * 1024)
bank = cache.load(source_path)
source = create_evaluated_helper(
    bank, entry_id, native_armature,
    base_policy="REST",             # Explicit choice for this clip/context.
    create_raw_action=False,         # Skip authoring UI curves in a bake worker.
)
try:
    frame_count = source.evaluation.source.header.frame_count
    loop_frame = source.evaluation.source.header.loop_frame
    for frame in range(frame_count):
        evaluated = source.set_frame(frame)  # Also accepts e.g. 10.25.
        # Existing retarget/keying consumes evaluated.pose.bones[name].matrix.
        # Copy matrices now: evaluated objects change at the next frame.
finally:
    dispose_evaluated_helper(source)
```

[The callback-based example](../tools/duplicate_pose_bake_integration.py) can be
imported in an isolated worker. It performs no production writes and does not
install itself into `bake_common.py` or `bake_shard.py`.

For a partial clip, use `base_policy="ACTION", base_action=complete_base_action`.
A helper made from the intended ordinary base clip supplies a complete action.
The base must use the same skeleton/pose space; its missing-component curves
are copied at build time. Do not infer it from a last-viewed pose. The evc0014:14
test uses idle 0:1 as an explicit test context, not a universal cinematic recipe.

Mapping defaults to `MhBone_###` or `BoneFunction.###`. A caller may provide
`function_map={native_function_id: actual_bone_name}`. Keys are 9-bit IDs;
aliases may resolve to one destination. Ambiguous inferred maps and absent
mapped bones fail. Inspect `source.evaluation.bindings` and `.diagnostics` for
selected original slots and unbound/unsupported records.

Native sampling is **0..N−1**, with subframes inside that interval. Keep N and
loop metadata explicitly when assembling the exported bank. Do not infer native
counts from a legacy appended tail, scene range or base action length. The
helper adds no root sample at N and infers no wrapping, scene FPS, cinematic time
scale or layer transition.

Source ownership is explicit:

```python
from mhw_anim_tools.core.formats.lmt.source_slots import export_source_slots

unchanged_bytes = export_source_slots(bank)
edited_bytes = export_source_slots(bank, {entry_id: {original_slot_index: encoded_track}})
```

`encoded_track` is an `LmtTrack` with an intended encoded payload/reference, not
an evaluated transform. The edited-slot API preserves identities, count/order,
opaque metadata, other records/entries and native headers; it rebases events
and audits readback. It is separate from exporting the retargeted canonical
action. Normal LMT export rejects a helper action instead of overwriting raw
duplicate/control slots. Request `create_raw_action=True` for source authoring.
Existing encoding, retargeting and readback standards remain in force.

Cache and lifetime behavior:

- `cache.load(path)` compares complete current bytes before reusing a parse;
  same-size/time replacement is detected. SHA256 belongs to the loaded bytes.
  The LRU is bounded by bank count and charged memory. Oversized banks are
  returned without retention. Process changes reset inherited cache entries.
- A helper is an explicit source/base snapshot. Its curves need no cache or
  file reads during playback. `load_helper_source(helper, cache)` verifies its
  stored hash after reopen and rejects replaced files. Rebuild for changed
  inputs; no path-only decoded-motion cache is used. Do not reuse export
  analyses after authoring edits.
- The LRU budget excludes caller-held snapshots and Blender armatures/actions/
  FCurves. Dispose temporary helpers after consumers finish and release other
  held plans/banks. Shared actions/data remain alive. Saved review helpers
  persist until deliberately removed.
- Runtime is CPU-only using Blender's bundled Python. Research dependencies
  are not imported by the add-on; there is no new GPU/NVIDIA requirement.

See [supported rules and limits](repeated-track-support.md) for mirroring/control
exceptions, captured-pose residuals and tests. The existing
[throughput integration](bake-throughput.md) is independent: its measured gain
requires caller changes and does not measure the new helper. This release
has not been installed into the bakery or game.
