# Native repeated-track binding rules, 2026-09-15

**The native skeletal binding rule is last applicable record per resolved
destination. It is not a per-clip rule.** Three native binding routines have
the same forward traversal and unconditional pointer replacement. Replaying
their unmodified x64 instructions against all **773 affected actions** and
**88 ordinary controls**, from 114 fingerprinted banks, passed. This establishes
record selection without requiring 773 in-game capture sessions.

This does **not** authorize globally deleting earlier records. A separate native
control-data consumer selects the **first** `bone_id=251, usage=1` record.
The same ordered list serves more than one consumer. Source-preserving export
must retain it in full.

No Blender playback, retargeting, installed add-on, game asset, or bakery output
was changed. These are research/verification tools, not an implemented duplicate
evaluator. This report supersedes the earlier recommendation to seek another
cutscene as the next means of establishing a general selection rule.

## Native evidence

The on-disk game executable has SHA-256
`c2ebbbd2c49f216d484e31a5219bed419eb1e5e7d206d02cba040a3ab79d90ea`.
Its `.text` is packed. The research script opened the already running process
with **PROCESS_VM_READ only**, read just the main module's `.text` twice, and
verified identical reads. It did not attach a debugger, pause, inject, write
process memory, or send inputs. All subsequent experiments ran offline.

The loaded `.text` SHA-256 is
`b3134322898e768bcf26a6fbb66b86af5806917af1bbdef7245d79b2cf519574`.
The local analysis copy combines that code section with the original PE's other
sections; its SHA-256 is
`cca74b3c4419d9ffc1fcea6d41b861b08c2021bb4fcae7c45bfbf7e9bd15ff34`.
It is an analysis artifact, not an executable intended to be launched.

SharpPluginLoader's previously pinned signatures each matched once in loaded
code: register LMT `0x142237830`, entity animation `0x141C014F0`, animation-layer
update `0x14224D530`. IDA 9.3 was used headlessly on the local copy. PE unwind
chaining was resolved when identifying complete function ranges; initial
function-chunk boundaries were not treated as independent routines.

| Operation | Native address | Relevant result |
| --- | --- | --- |
| Layer binding | `0x14224C200` | Forward 48-byte records; channel pointer replacement |
| Second skeletal binding path | `0x14237C980` | Same selection, different component layout |
| Binding with alternate joint storage | `0x142642A30` | Same selection, different joint-array source |
| Common binding helper | `0x1422341E0` | Assign source pointer, reset sampling cursor, copy payload pointer and weight |
| Track sampler | `0x142234010` | Sample the already bound record; static codecs 1/2 return its reference value |
| Resource entry lookup | `0x1422AC150` | Return the entry pointer from the LMT's motion table |
| Separate control consumer | `0x140A8ED80` | Stop at first `251 / translation` match |

The layer path can be followed from `0x142247ED0`: it clears binding state,
gets the original motion through `0x1422AC150`, then calls `0x14224C200`.
The latter reads the original record pointer/count at motion offsets 0/8.
It advances the source address by 48 bytes until the count is exhausted.
There is no grouping by clip number or authored-block boundary in that loop.

The common helper unconditionally performs the equivalent of:

```text
destination.time_cursor = 0
destination.payload_cursor = record.buffer_pointer
destination.record_pointer = record
destination.weight = record.weight
```

It neither checks for an occupied destination nor combines the old and new
values. Repetition therefore replaces the entire selected track, independent
of whether its key times overlap another record's keys. Identical copies have
the same pose value once selected; they are not applied repeatedly to the pose.

## Destination identity and limits

The verified native mapping is more precise than a dictionary keyed only by
the raw `(bone_id, usage)` pair:

| Usage | Binding destination |
| --- | --- |
| 0: rotation | Mapped joint's rotation state |
| 1: translation | Mapped joint's translation state |
| 2: scale | Mapped joint's scale state |
| 3: root rotation | Dedicated motion root-rotation state |
| 4: root translation | Dedicated motion root-translation state |
| 5: root scale | No binding assignment in these three switches |

For usages 0–2, a nonnegative ID is masked with `0x1FF` and looked up in the
model's function-to-joint byte table. Value 255 means unmapped. Negative IDs
have no ordinary joint destination. Aliases can collide at a resolved joint
even when their raw identifiers differ. Root usages 3/4 select their dedicated
destinations independently of the ID. Preserve raw record identity separately
from this evaluation mapping.

There are **192 repeated root-scale groups** in the catalogue. Their records
must remain preserved; these routines provide no basis for applying a root-scale
track to the Blender root helper. This finding does not establish that every
possible game subsystem ignores those bytes.

The complete extract uses `joint_type=0`, tag `0xCD`, and weight 1.0 on every
record. Nonzero joint types have additional native joint-state logic; that
behavior is outside this qualification. The loop does copy weight, and
downstream pose/layer evaluation uses weight/state flags. The binding result
alone does not qualify arbitrary weights, modes, codecs, procedural constraints,
mirroring, parent requirements, or layer composition.

Missing channels also require a separate base-pose/context decision. Do not
translate this finding into Maya-style additive, override, or passthrough layer
semantics. The finding is about selecting a record before pose sampling and
layer evaluation.

## A concrete reason to preserve control records

Six inspected direct consumers search forward for usage 1 / ID 251 and stop at
the first match: `0x140245540`, `0x140A8ED80`, `0x140FCF420`, `0x141991920`,
`0x141FF9310`, and `0x14206D920`. Some downstream paths convert the sampled value
to another animation selector. These readers access the source list directly;
they do not ask the skeletal binding table which record won.

The isolated native search block `0x140A8EDBA..0x140A8EE05` was replayed on
all **57 affected `251 / translation` groups**, including **16 conflicting**
groups. It selected the first source slot in every case. The skeletal binder,
with that function mapped to a joint, selected the last. Three synthetic cases
also checked reversed values and skipping wrong IDs/usages. The other five
readers have static-code evidence only, not separate instruction replay.

Another inspected consumer, `0x14210D360`, scans scale records for IDs 30/47 and
tests sampled values. This reinforces that the ordered source list has uses
beyond visible skeletal pose. We have not implemented those game-control
systems in Blender or qualified their full effects.

## Verification

`tools/verify_native_track_binding.py` uses Unicorn 2.1.4 to execute the saved
instructions with a synthetic model lookup table, joint storage, and the native
ordered headers. Execution begins at each real function entry and stops after
the binding loop, before root endpoint calculations, interpolation, and final
pose/layer evaluation. Executable pages are read/execute in the emulator.
Game instructions run only under the emulator; there are no calls into the
running game and nothing is installed there.

The checker verifies the exact ordered calls to the binding helper, every final
source pointer, copied payload pointer/weight, cleared cursor, and empty state
for absent destinations. It verifies source bank hashes against the full census.
Original record buffer addresses are opaque values for this test; they are not
dereferenced, serialized, or reused in an exported LMT.

| Check | Result |
| --- | --- |
| Affected actions | 773 |
| Ordinary controls | 88, one eligible ordinary entry per affected bank |
| Fingerprinted native banks | 114 |
| Native binding-loop replays | 2,583: all 861 cases through all three paths |
| Verified ordered binding-helper calls | 280,926 |
| Synthetic binding replays | 49 |
| Native control-reader corpus cases | 57, including 16 conflicts |
| Deliberate first-wins substitution in skeletal binding | Rejected on all three paths |

Synthetic cases include multiplicities 1/2/3/6/7/13/257, all five handled
destinations plus unhandled root scale, aliases, negative/missing IDs, unusual
root IDs, source flags, and layer-bank/slot configurations. A zero-weight later
record still replaces the pointer. An unknown codec can also be bound; this is
deliberately **not** a claim that it can be decoded safely.

The test supplies an injective synthetic lookup for every nonnegative function
ID in each corpus action. Thus it establishes binding under known mappings,
not that every character's real model contains every function. Synthetic alias
and missing-target cases separately verify those branches. It does not replay
all 773 complete animations or assert retargeting accuracy.

The full corpus report was reproduced byte-identically. The tracked verifier
also passed its synthetic and consumer checks; report fingerprints are recorded
in `docs/benchmarks/duplicate-native-binding-2026-09-15.json`.

Local evidence lives in
`corpus_scans/duplicate_rules/native_evaluator_20260915/`. The executable/code
copies and IDA database remain ignored local artifacts; do not commit or
redistribute them with the add-on. To rerun against those local artifacts:

```powershell
& 'C:\Users\akifs\AppData\Local\Programs\Python\Python310\python.exe' tools/verify_native_track_binding.py fresh_binding_report.json
& 'C:\Users\akifs\AppData\Local\Programs\Python\Python310\python.exe' tools/verify_native_track_consumers.py fresh_consumer_report.json
```

Use fresh output names; existing reports are not overwritten.
`MHW_NATIVE_BINDING_EVIDENCE` can override the evidence directory, and
`MHW_NATIVE_SOURCE_ROOT` can override the native extract root. The census must
remain in the sibling `generalization_20260915` directory. Unicorn may be
installed in the evidence directory's `research_deps` or in the research Python
environment. IDA is needed only to repeat static analysis, not instruction replay.
Neither tool, NumPy, CUDA, NVIDIA, nor PyTorch becomes an add-on dependency.

## Implementation consequence

Implementation update: the CPU helper is now available in v1.1.0.
See [supported rules and tests](repeated-track-support.md) and
[baking integration](duplicate-track-baking-integration.md). The following
paragraphs record the boundary established by the binding investigation; later
native sampling and Blender qualification are documented in that build report.

Implement one source helper hierarchy with explicit root rotation/translation,
using a binding table that records the last applicable raw slot for each resolved
pose destination. Preserve all ordered raw records and their metadata/payloads
for round trips and control consumers. Keep game-control interpretation separate
from pose binding. This removes the need for a clip whitelist for the verified
native skeletal rule; unsupported contexts must still be reported explicitly.

The seven captured player clips remain independent rendered-pose checks. The
1.61–1.73-degree Eorzea arm residual remains unresolved; record selection does
not erase it. Source timing, loop boundaries, quaternion continuity, helper
sampling, edited-export ownership, and TIML relocation still need implementation
and regression qualification. No new throughput or full-pipeline speedup is
claimed by this research.
