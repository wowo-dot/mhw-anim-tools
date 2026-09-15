# Repeated MHW LMT tracks: Maya, importer, and native-file evidence

Research date: 2026-09-15. This document records the initial source investigation.
The subsequent capture analysis in `repeated-track-runtime-evidence.md` strongly
supports later-record motion for four fingerprinted evc0034 clips. The earlier
uncertainties below describe the state before that analysis. The later
[native binding investigation](repeated-track-native-binding.md) establishes
last-applicable-record skeletal binding across the affected corpus, while
identifying distinct first-record control consumers. Add-on playback/export
behavior has not changed.

Maya is a credible authoring reference. Capcom describes Maya as its main DCC and
lists an internal MT Framework asset exporter running inside Maya. That does not
specify how that exporter represents repeated LMT records, or how MHW evaluates
them. [Capcom's Autodesk profile](https://area.autodesk.jp/jobs/capcom/)

Autodesk documents additive, override, and override-passthrough layers. Rotation
can accumulate by Euler component or by layer using quaternion calculations;
scale can add or multiply. Consequently, "implement Maya layers" does not select
one mathematical rule. We still need the mapping from MHW data/runtime context
to the intended operation. No public Capcom exporter implementation or confirmed
MHW repeated-track runtime rule was located in this investigation.
[Maya layer modes](https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Animation/files/GUID-BBCA0BC3-7608-4E86-8E9F-B4099C316156.htm),
[rotation and scale accumulation](https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Animation/files/GUID-C7987782-C10D-433C-A78D-94C10D800608.htm)

## Independent importer behavior

These are static source inspections, not runs in Maya or 3ds Max, and not an
independent MHW runtime oracle. The reference repositories were not built or
executed.

| Implementation inspected | Treatment of repeated transforms | What it establishes |
| --- | --- | --- |
| Supplied MaxScript, BETA 5.1, `MT Framework (LMT, MOD).ms` | Iterates records in source order and assigns keys on the same bone controllers. No separate animation-layer construction found. | Later writes can replace keys at overlapping times; this is not proof of whole-track replacement in MHW. |
| RevilMax, `MTFImport.cpp` | Samples records and writes positions/rotations into the same controllers at the same frame times. Its additive checkbox uses a controller value at time -1. | The UI option is not a duplicate-record mode decoded from track metadata. |
| RevilLib, `lmt_to_gltf.cpp` | Keeps the first position/rotation/scale sample array for a bone and warns when another arrives. | Its converter's collision policy differs from Max's sequential writes. |
| FreeHK, `struct/Lmt.py` and `blender/lmt_importer.py` | Marks repeated `(usage, boneId)` records as folded; imports them into shifted FCurve indices, muted. | Preserves alternatives without establishing their combined motion. |

Pinned sources:

- [RevilLib e17f971, track dispatch](https://github.com/PredatorCZ/RevilLib/blob/e17f9718ea571f040a7e1f331c28a4d45a6066b5/toolset/lmt_to_gltf/lmt_to_gltf.cpp#L430).
  Its collision key is bone plus TRS category, which is broader than the add-on's
  bone plus exact LMT usage key.
- [RevilMax 44cf603, import loop](https://github.com/PredatorCZ/RevilMax/blob/44cf603992ce00818a9eaa100e3932c5a72adfa4/src/MTFImport.cpp#L578).
- [FreeHK 21acb2f, folded detection](https://github.com/AsteriskAmpersand/MHW-Free-HyperKinetics/blob/21acb2ffe515f47482e3971ac7b83b10d3f4a64b/struct/Lmt.py#L225)
  and [muted import](https://github.com/AsteriskAmpersand/MHW-Free-HyperKinetics/blob/21acb2ffe515f47482e3971ac7b83b10d3f4a64b/blender/lmt_importer.py#L25).
- Supplied `C:/Users/akifs/Downloads/MT Framework (1).mzp`, SHA-256
  `2948139ee93897937392716f65b1fddec1503aed887b225f61be0405ee68240a`.
  `ExecuteNode` around line 1702, `ImportFrames` around 1733, load loop around
  1786. Inspected as an archive, never installed or executed.
  [Author's page](https://lukascone.wordpress.com/2017/06/18/mt-framework-tools/).
  Autodesk documents that `addNewKey` returns the existing key at an occupied
  time. [Controller key API](https://help.autodesk.com/cloudhelp/2021/ENU/MAXScript-Help/files/3ds-Max-Objects-and-Interfaces/Animation-Controllers/Controller-Common-Properties/GUID-B1700B1D-B1EA-4A6C-B4A3-A29DB26C8C02.html)

The FreeHK terminology reference also explicitly leaves aspects of folded root
bases unresolved. Its import/export tail handling must not be mistaken for an
independent runtime observation.
[FreeHK terminology](https://github.com/AniBullet/MonsterHunterWorldModding/wiki/FreeHK-Terminology)

## Native fixture results

Read directly from the user's unchanged native extract under
`D:/mh world modding/whole game extract/chunk`. Counts below group records by
`(bone_id, usage)`. "Identical" means complete stored track content is equal
after normalizing addresses and comparing the referenced data. It does not mean
we have proved that multiplicity is irrelevant to runtime evaluation.

| Pipeline label | Native event / entry | Tracks | Identical repeated groups | Conflicting repeated groups |
| --- | --- | ---: | ---: | ---: |
| 20037:33 | evc0035 / 33 | 414 | 78 | 2 |
| 20023:20 | evc0021 / 20 | 90 | 0 | 2 |
| 20036:0 | evc0034 / 0 | 187 | 1 | 33 |
| 20036:1 | evc0034 / 1 | 187 | 1 | 33 |
| 20036:4 | evc0034 / 4 | 187 | 1 | 33 |
| 20036:14 | evc0034 / 14 | 187 | 1 | 33 |
| 20016:14 | evc0014 / 14 | 14 | 2 | 2 |
| Ordinary controls | 3:150, 3:151, 0:363, 2:67 | 82 each | 0 | 0 |

All tracks in these eleven clips have `joint_type=0`, `unknown_tag=205`,
`weight=1.0`. These fields alone do not distinguish conflicting members here.
That observation does not establish their general meaning or cover other modes.

The strongest new clue is in all four inspected `evc0034` entries:

- The first 107 records have empty animation buffers and carry stored bases.
- A later block of 80 records begins with a second root rotation record. It
  contains 60 nonempty buffers in entries 0/1 and 58 in entries 4/14.
- The later root rotation basis and XYZ translation basis match the action's
  stored root end fields byte for byte. The earlier root bases disagree.

| Entry | Earlier root rotation distance from header | Earlier root XYZ distance from header | Later root distances |
| --- | ---: | ---: | --- |
| 0 | 114.160071 degrees | 3025.515843 source units | Both zero; stored bytes match |
| 1 | 114.160071 degrees | 3109.850194 source units | Both zero; stored bytes match |
| 4 | 114.160071 degrees | 2993.894176 source units | Both zero; stored bytes match |
| 14 | 132.365810 degrees | 3002.464947 source units | Both zero; stored bytes match |

For partial clip `evc0014:14`, the later root's final payload sample is also much
closer to the header: rotation 0.027603 degrees versus 173.124448 degrees for the
earlier record; translation zero versus 88.873516 source units. This comparison
uses the add-on's payload decoder and is not independent codec validation.

**Inference:** replacement of an earlier initialization/default record by a later
record deserves priority over an assumed additive combination in the next
experiment. Neither these header relationships nor a plausible A/B preview
prove a universal last-record-wins rule. The block split is descriptive, not a
decoded runtime boundary.

Root checks deliberately use actual stored bases or final decoded payload
samples, never `decoded.tail_value`. The decoder inserts the action header into
that tail; comparing it back to the header would be circular.

An exploratory inspection of native `evc0034.sdl` finds separate `pl000_00` and
`pl000_00_face` branches referencing the same bank, with selector ranges beginning
at `0xe000` and `0xe12c`. Interpreting the low 12 bits as entry IDs gives 0 and
300. This is a limited SDL v32 interpretation, not a qualified general parser.
It does not assign ownership to duplicate records inside a body action. Missing
bone IDs therefore must not automatically be classified as facial or discarded.

## Consequences for a Blender helper implementation

Keep three distinct responsibilities:

1. **Source storage:** preserve every ordered record, metadata field, referenced
   payload, and stable source identity. Export must not infer record identity
   from only a bone name or the visible pose. Address relocation must preserve
   valid referenced data, including TIML.
2. **Motion evaluation:** evaluate each record at an explicit time, then apply
   a separately identified, verified resolution rule. Unknown cases remain
   unresolved; experimental first/last/composition previews must be marked as
   such. Identical records may share decoding work without deleting originals
   or assuming their runtime contributions collapse.
3. **Blender presentation:** write the resolved local transforms onto a helper
   armature with the correct hierarchy. Retarget from that evaluated armature
   onto the canonical rig. Helpers must not become extra exported LMT bones.

Parenting one helper under another already imposes transform multiplication.
Likewise, choosing Maya layers, Blender NLA blend modes, or constraint mix modes
would impose semantics before they have been established. Helpers should expose
the evaluator's result, not decide the rule accidentally through their hierarchy.

The evaluator should accept arbitrary time/subframe queries and work headlessly,
without depending on the previous frame or shared mutable action state. A pure
CPU implementation is sufficient for this architecture; there is no Maya,
3ds Max, PyTorch, CUDA, or NVIDIA dependency.

Existing integration gaps remain pending, not fixed by this research:

- Imported duplicates currently survive as raw channels but do not drive the
  normal visible bone channels.
- An incomplete raw component set currently produces a warning and can omit
  the record during export. That should become a blocking validation error.
- The bakery's `key_poses` clears FCurves, including raw channels. A helper-based
  integration needs explicit source storage/export ownership that survives
  creation of the retargeted action. Do not change the paused bakery implicitly.

## Next discriminating validation

Use an unmodified in-game capture or the game's evaluation code as the reference.
For `evc0034:0`, compare candidates at frame 135 (the supplied A/B investigation
reports a large posture difference), plus the start, end, and intermediate
frames. Measure root transforms and several body joints in a common coordinate
system; a camera-only silhouette comparison cannot qualify numerical accuracy.
Then check entries 1/4/14, the partial clip with its actual base action, and the
two remaining translation-conflict fixtures. A match on one clip cannot qualify all identities,
modes, owners, or sparse-channel behavior.

Preserve originals while testing first, last, additive/reference-relative, and
context-selected candidates. Quaternion order, reference bases, and coordinate
spaces must be explicit. Once a rule is independently qualified, validate
subframes, random access, loops, root/control channels, events, source-preserving
round trips, save/reopen, and ordinary single-track clips before baking at scale.

## Reproduction and scope

The standalone audit uses Python 3.10+ and this checkout's core modules. It has
no third-party dependencies. It reads seven LMT files and one SDL file, hashes
each before/after inspection, cross-checks independently unpacked physical track
records against the add-on reader, and writes only its requested JSON output.
The output includes source hashes, record fingerprints, root measurements, and
the script hash. Output inside the extract is rejected. Run without Python `-O`,
because verification uses assertions.

```powershell
python tools/audit_repeated_track_evidence.py --source-root 'D:\mh world modding\whole game extract\chunk' --output 'corpus_scans/duplicate_rules/evidence.json'
```

The full local result is `corpus_scans/duplicate_rules/evidence.json`, in the
ignored research directory. Reference source clones also live there. Verification
passed: script syntax, all eleven fixture audits, byte-identical JSON from a
second run, eight unchanged source-file hashes, and rejection of an output path
inside the extract. Evidence JSON SHA-256:
`5ff9bfd65c376928fe1d8cb47ac571ec34d78eb352cbaa4df417fa88f87e1972`.
These are structural checks, not Blender playback or game-accuracy tests.

This work adds the audit and this report only. It implements no playback rule,
performs no production rebake, and makes no new throughput claim. Existing CPU
throughput changes in the checkout are separate. The bakery, pinned snapshots,
native extracts, installed add-on, and game package were not modified.
