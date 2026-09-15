# Duplicate-track generalization investigation, 2026-09-15

**Update: the [native binding investigation](repeated-track-native-binding.md)
establishes last-applicable-record selection for skeletal pose destinations,
with instruction replay on all 773 affected actions and 88 ordinary controls.**
Separate control consumers can select the first record, so this is not a global
source-list deduplication rule. The historical census/capture reasoning below
predates that engine-code result.

Captured body/root results agree with later records for evc0034 entries
0/1/4/14 and evc0074 entries 2/3/5.
The [Eorzea follow-up](repeated-track-eorzea-evidence.md) adds the latter three
cases, with zero/identity records that leave composition alternatives unresolved.
The full native census now identifies
every repeated group in the supplied extract. The subsequently investigated
**Hazards of the Job** entry 6 is authored with player drawing disabled, making
it unsuitable for a normal rendered-pose reference. See the
[capture and visibility findings](repeated-track-hazards-evidence.md), which
supersede the capture recommendation below and identify visible alternatives.
No add-on playback or export behavior has changed during this phase.

## Complete native census

The scanner read all 5,774 paths returned by `rg --files` for `.lmt` files under
the supplied native `chunk` extract. All banks are version 95. This is complete
for that extract and file inventory, not a claim about other game releases,
mods, unavailable assets, or runtime-created motions.

| Measurement | Count |
| --- | ---: |
| Banks / actions / ordered records | 5,774 / 105,040 / 11,546,642 |
| Affected banks / actions | 114 / 773 |
| Repeated identity groups | 9,347 |
| Complete-content-identical groups | 5,296 |
| Conflicting groups | 4,051 |
| Actions with at least one conflicting group | 684 |
| Actions with only identical repeated groups | 89 |

The affected-action counts exactly reproduce the historical documentation.
Every group now has an ordered slot list and every record has its metadata,
basis, source addresses, and complete-content fingerprint. Comparison normalizes
the two track addresses while retaining pointer presence and including referenced
buffer and bounds bytes. All other header bytes remain significant. This is
track-content equality, not proof that identical copies can safely be discarded
under an unknown composition rule. TIML relocation is outside this census.

All 11,546,642 records have `joint_type=0`, `unknown_tag=205` (`0xCD`), and weight
`1.0`. These fields therefore cannot distinguish duplicate families within this
extract. Their runtime meaning is not established by their constancy. The
observed action flag words occur in ordinary actions too; this inspection has
not identified a flag that explains duplicate dispatch.

| Records per repeated identity | Groups |
| --- | ---: |
| 2 | 8,754 |
| 3 | 194 |
| 6 | 117 |
| 7 | 279 |
| 13 | 3 |

The 13-record groups are root rotation, translation and scale in
`event/evc0014/gm035_10/gm035_10.lmt`, entry 3. A general implementation must
retain arbitrary ordered multiplicity rather than assuming two records.

Conflicting groups include animated-to-animated (1,614), animated-to-static
(784), static-to-animated (1,139), and static-to-static (514) first/last pairs.
Here “static” describes an empty payload buffer; it does not assert whether the
runtime applies that record. Splitting records at a second root rotation is
likewise a descriptive operation, not a verified block boundary.

Affected actions by top-level path: `em` 518, `event` 242, `npc` 9, `Assets` 3,
and `otomo` 1. There are no repeated identities in the scanned `hm` banks.
This distribution does not establish whether external playback context selects
a rule, nor whether all these assets belong to the user's baking inventory.

## Player-body event cases

Within `event/<event>/pl000_00/pl000_00.lmt`, 25 actions contain repeated
identities: **11 conflicting and 14 entirely identical**. The following table
lists all 25. These paths define the scope; NPCs, weapons, props and monsters
make up the other affected event actions.

| Gallery title | Native event | Entries | Conflicting groups per entry |
| --- | --- | --- | --- |
| Hazards of the Job | evc0008 | 6 | 1 |
| The End Result | evc0014 | 14 | 2 (plus 2 identical) |
| Trouble in the Vale | evc0019 | 2 | 0 (77 identical) |
| Crown of the Ancient Tree | evc0021 | 20 | 2 |
| Where Life Converges | evc0032 | 0, 4, 5, 6, 8, 9, 18, 20, 22, 23, 24, 25, 29 | 0 (77 identical each) |
| The Admiral Blows In | evc0034 | 0, 1, 4, 14 | 33 (plus 1 identical each) |
| Denouement | evc0035 | 33 | 2 (plus 78 identical) |
| A Visitor from Eorzea | evc0074 | 2, 3, 5 | 1, 2, 1 respectively |

Titles come from the native English Gallery GMD's stored text indices. The
evc0034 selection has quantitatively reconstructed evidence in
[the runtime report](repeated-track-runtime-evidence.md); evc0074 entries 2/3/5
now have corresponding [Eorzea evidence](repeated-track-eorzea-evidence.md).

## Initially proposed discriminator: Hazards of the Job (superseded)

The structural comparison below remains valid, but the capture recommendation
is withdrawn. Subsequent SDL inspection found `pl000_00/Draw=0` throughout
entry 6's interval. The same visibility check found evc0014 entry 14 hidden.
This does not resolve either action's duplicate semantics or authorize dropping
their records. See [the follow-up report](repeated-track-hazards-evidence.md).

Entry 6 has 219 records, 392 source frames, loop frame -1, and one repeated
identity: bone 0, usage 1 (body translation).

| Ordered slot | Codec / payload | Stored XYZ basis |
| --- | --- | --- |
| 7 | Codec 4 / 1,072 bytes | (-222.03064, 104.53183, -19.59302) |
| 211 | Codec 1 / empty | (0, 0, 0) |

Both records have the same mode, tag and weight. The separate global-root
rotation and translation are unique. A universal last-record rule would select
the later zero body translation. An animated-record preference would retain
the earlier motion. Addition with zero could also match the earlier result, so
one capture cannot distinguish every conceivable rule. These are predictions
to compare against game matrices, not an inference from whether a pose looks
plausible. Ownership of the later records remains unresolved.

The exploratory SDL reader finds player selector `0xe006` at tick 1127 and the
next selector at 1519: a 392-tick interval. The reader's selector mapping and
tick-to-wall-clock timing still require runtime alignment. RenderDoc frame
numbers are not source frames. Requested coverage is the first minute at normal
speed, with 6–8 F12 captures spread through visible hunter movement, plus a screen
recording. Innerwear 501 enables reuse of the independently identified geometry.
Full body and feet are useful where practical. Confirm the RenderDoc saved
counter rises; a Steam screenshot alone contains no joint buffers.

Read-only MO2 verification found no loose overrides for this bank, its scene
and camera SDLs, or Innerwear 501 geometry. Profile/configuration hashes remained
unchanged. The result is saved in
`corpus_scans/duplicate_rules/hazards_20260915/preparation/verification.json`.
Packed archive differences and runtime plugin effects are not qualified by
this check; the game was not relaunched or controlled by the verification.

The capture template may still begin with `evc0034`; its prefix is not scene
identity. Identify new files through the recording, Gallery title and animation
alignment, preserving their original names. The user controls the game during
this pass. No new capture is claimed as analyzed in this report.

## What the structural research cannot settle

Root action-header values are not a reliable standalone decision rule. Later
raw endpoints or bases are usually closer to the stored header, but some earlier
records are closer and often neither matches. A header may describe an endpoint
or chaining transform rather than an arbitrary interior pose. These cases are
heuristic exceptions, not observed runtime counterexamples. Comparisons never
use the decoder's header-injected tail, which would make that test circular.

The inspected public SharpPluginLoader source exposes action flags and external
animation-layer controls, but not an implementation of the native duplicate
resolver. Its metadata `ApplyType` enum belongs to TIML keyframes and must not
be interpreted as a skeletal-track blending flag. Its animation layer accepts
clip IDs, interpolation time, starting frame and other attributes, which shows
external playback context exists; it does not show that context selects duplicate
records. See the pinned primary sources:
[Motion.cs](https://github.com/Fexty12573/SharpPluginLoader/blob/1d57554df1d381df2cd91b97d47d7c94fb4bebb5/SharpPluginLoader.Core/Resources/Animation/Motion.cs)
and [AnimationLayerComponent.cs](https://github.com/Fexty12573/SharpPluginLoader/blob/1d57554df1d381df2cd91b97d47d7c94fb4bebb5/SharpPluginLoader.Core/Components/AnimationLayerComponent.cs).
The reference checkout was not built or installed into the game.

The remaining duplicate-evaluation alternatives include fixed ordered replacement, a rule selected
by currently unresolved metadata/ownership, or external playback context. No
new result here uniquely selects among them. Additional contrasting runtime
fixtures and, if necessary, the native evaluation path are the next evidence.
Successful fixtures increase coverage; they are not an exhaustive proof over
all possible playback contexts.

## Reproduction and validation

Research utility: `tools/scan_duplicate_track_rules.py`, system Python 3.10+,
standard library plus the existing add-on parser. No Blender, NumPy, PyTorch,
CUDA or NVIDIA dependency is required for the census. It reads bank data and
retains compact summaries; it does not cache every parsed bank or alter source
files. Output must be a new directory under this checkout's `corpus_scans` and
outside the extract. Use ordinary Python without `-O` so inherited audit
assertions remain enabled.

```powershell
python tools/scan_duplicate_track_rules.py --source-root 'D:\mh world modding\whole game extract\chunk' --paths corpus_scans/duplicate_rules/native_lmt_paths_20260915.txt --output corpus_scans/duplicate_rules/generalization_20260915
```

Full outputs are in `corpus_scans/duplicate_rules/generalization_20260915/`:
`catalogue.jsonl` contains all 773 affected actions and every repeated record;
`banks.json` contains every source hash and affected entry list; `actions.json`
is a compact index; `summary.json` contains aggregate counts. Catalogue SHA-256:
`e17b68d51ee812cf0dd578af9c2deb3af797db818106e0ce84ce870d51feabd8`.

The two full runs completed in **37.86 and 21.03 seconds** with zero errors and
unchanged hashes for all 5,774 source banks during each run. Catalogue, bank
manifest and action index are byte-identical between runs. These are research
scan timings, **not import/bake/export speedups**. Seven previously audited
duplicate fixtures match the saved complete-record evidence; four ordinary
fixtures remain absent from the duplicate index. Syntax and output guards
passed, including rejection of an existing output and a destination inside the
native extract.

The compact report, including all 25 player cases, ordered conflicting records,
source hashes and validation results, is
[`benchmarks/duplicate-generalization-2026-09-15.json`](benchmarks/duplicate-generalization-2026-09-15.json).
No bakery scripts, production bake outputs, pinned snapshots, installed game
assets or add-on execution paths were modified by this census.
