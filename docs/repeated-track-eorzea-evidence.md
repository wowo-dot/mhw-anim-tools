# Eorzea duplicate-track capture evidence, 2026-09-15

**Later result:** [native binding analysis](repeated-track-native-binding.md)
establishes general skeletal selection independently of these seven capture
cases. Its findings do not remove this report's arm residual or expand its
rendered-pose accuracy claim.

**Captured body/root results agree with the later records in evc0074 player
entries 2, 3 and 5.** Five distinct target poses cover all three entries. The
tested earlier and mixed selections disagree substantially. Together with the
[four evc0034 cases](repeated-track-runtime-evidence.md), this makes seven
affected player clips with measured body/root results agreeing with later
records. It is still not a universal last-record-wins rule.

The distinction matters particularly here: the earlier conflicting records
are zero translations or identity root transforms. Adding zero or composing
with identity can produce the same result as selecting the later record.
These captures cannot distinguish those equivalent candidates. They also do
not establish export ownership or justify discarding any source records.

No add-on behavior, animation tolerance, game asset, bakery artifact or pinned
snapshot was changed. This is research evidence, not an installable evaluator.

## Captures and source identity

The user supplied the 348.053-second video
`C:/Users/akifs/Videos/Monster Hunter- World - 2026-09-15 3-34-31 PM.mp4` and
**42 new RDCs / 69,841,382,308 bytes**, showing the Cactuar/Moogle encounter in
**A Visitor from Eorzea**. The body clips are independently matched against
the native evc0074 bank using ordinary local arm rotations. The retained
`evc0034` filename prefix is not a scene identifier.

Every RDC was hashed and its embedded thumbnail read. **19 selected captures
were replayed**, yielding 19 distinct verified body poses across **285 matched
draws**. Five target poses account for **72 draws**; the other 14 poses are
ordinary controls. The other **23 captures** have hash/header/thumbnail checks
only and are not included in numerical pose claims.

Full native vertex-block hashes identify Innerwear 501. All 86-joint slices
agree byte for byte across independently read matched draws within each
capture. The source identities are:

| Source | SHA-256 |
| --- | --- |
| `event/evc0074/pl000_00/pl000_00.lmt` | `b5d1f5664cbbf9efcda4720966301ab851477f5d708baaba0d9a35116dc128c4` |
| `pl/f_equip/pl501_0000/body/mod/f_body501_0000.mod3` | `bfdf5604a6d09892621df415bec1e06cd800d662888f8a31462d97e7fed42c64` |
| Supplied video | `fd51d6ef55b57966b1f91d244ed51a0f6a4562cedf305cb8c2d9c934e03b8ed9` |

Read-only MO2 verification found no loose override for the LMT, scene/camera
SDLs or body MOD3. Configuration hashes match the earlier preparation and
remain unchanged. Packed archives and runtime plugin effects are outside that
check's scope. The game was neither relaunched nor controlled in this pass.

## The conflicting records

Slot numbers are zero-based source record indices, retained independently of
their repeated `(bone_id, usage)` identities.

| Entry | Conflicting identity | Earlier slot / content | Later slot / content |
| --- | --- | --- | --- |
| 2 | `(0, 1)` body translation | 32 / static zero, codec 1 | 168 / animated, codec 4 |
| 3 | `(-1, 3)` root rotation | 0 / static identity, codec 2 | 2 / nonidentity static rotation, codec 2 |
| 3 | `(-1, 4)` root translation | 1 / static zero, codec 1 | 3 / nonzero static translation, codec 1 |
| 5 | `(0, 1)` body translation | 206 / static zero, codec 1 | 217 / animated, codec 4 |

All these records have mode 0, tag 205, and weight 1.0. The later entry-3 root
translation is `(4279.703125, 3668.559082, -13332.537109)`. Its stored XYZW
rotation is approximately `(0, 0.67183572, 0, 0.74070019)`.

The [visibility audit](repeated-track-hazards-evidence.md) found all three
entries enabled in the native scene's Draw schedule. Entry 2 has 131 native
frames but only a 95-tick selector interval; the two captured fits fall inside
that played interval. Entry 3 has 134 frames and entry 5 has 56 frames. No end
tail derived from an action header participates in these comparisons.

## Fitting and candidate results

The search covers all **18 populated body entries** below ID 300 in this bank,
using unique rotations for functions 5–12. Time is refined using only 5 and 9;
the remaining ordinary joints and every conflicting track are holdouts.
Quaternion inversion is also considered in the coarse search and does not
win. Root/body position and orientation never participate in fitting, and no
world placement correction is fitted.

Fitted source-frame coordinates are not runtime counters. NLERP and SLERP are
diagnostic sampling alternatives, not independently established engine rules.
The existing add-on decoder is used. The target fits have no search-bound hits;
an ordinary entry-4 control fits frame zero and is a boundary sample.

For the native body function 0, the compared world transform is:

```text
source_root_transform @ source_body0_local_transform
```

| Render frame | Entry | Fitted frame | Earlier position error | Later position error | Later orientation error |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2998583 | 2 | 6.520 | 338.689626 | 0.027152 | <0.00001 degree |
| 2999038 | 2 | 76.680 | 334.272441 | 0.022085 | <0.00001 degree |
| 3000136 | 3 | 31.375 | 15396.368363 | 0.061418 | <0.00001 degree |
| 3000894 | 3 | 88.290 | 15456.969842 | 0.096280 | <0.00001 degree |
| 3003998 | 5 | 51.115 | 855.785887 | 0.027017 | <0.00001 degree |

Position errors are Euclidean distances in **native source units**, not a
Blender-space fit or a new production accuracy tolerance. For entry 3, earlier
root orientation differs by **84.417810 degrees**. Both mixed root selections
were tested: earlier rotation/later translation gives **1064–1186 units**
position error; later rotation/earlier translation gives about **14475 units**.
The latter has the correct orientation but wrong placement.

The analysis checks 1,601 times around each coarse fit (approximately ±4 source
frames, clipped to native bounds) using both interpolation alternatives. Even
the worst later position error in each interval is below the best error of
every tested earlier/mixed candidate. An independent scalar verifier checks
81 times in each interval for both alternatives: **810 time/interpolation
samples across five poses**, with later selection closer at every sample.
The widest later error is 10.178507 units during this deliberately wider
timing sweep; that number is not a fitted-pose accuracy result.

## Ordinary-joint residuals

Ordinary controls cover entries **0, 1, 4, 20, 21, 30 and 34**. Their eight-arm
RMS disagreement is **0.284–0.408 degree**. Entry 3's target poses are similarly
close, at **0.306–0.331 degree**.

Entries 2 and 5 have larger ordinary-arm disagreement: **1.61–1.73 degrees RMS**.
In entry 2, functions 10/11/12 differ by approximately 1.7/2.7/3.7 degrees while
the two fitted anchors remain within about 0.033 degree. The coarse target
entry is still clearly separated from the next candidate (roughly 9 degrees
for entry 2). Clip 5 also has only one captured target pose, near its end.

These residuals are not corrected, ignored, or attributed conclusively to
procedural animation. The tested duplicate choices concern body/root
translation and global root orientation; they do not establish the cause of
the ordinary local-arm differences. Timing, decoding, procedural contributions
and playback context remain possible explanations. Full Blender/retargeted
animation accuracy still requires its own qualification.

## Coordinate-space check on a target draw

Capture **3000136**, draw **8632**, matches native body mesh 2. Its vertex
shader uses three float4 rows per joint from `gJointMatrixBuffer`, at the
current `iMatrixIndex` plus vertex joint indices. Weighted joint transforms
produce `WorldPosition` directly; a second `fWorld` placement is not applied.
The shader's separate previous-frame palette is not used as current-pose data.

CPU reconstruction from the saved input and joint buffers agrees with the
captured post-VS `WorldPosition` over **6,228 index references / 1,236 distinct
vertices**:

| Measurement | Native source units |
| --- | ---: |
| Maximum component difference | 0.002971772 |
| Maximum position distance | 0.003024170 |
| Mean position distance | 0.000668199 |

The complete index-buffer hash also matches native mesh 2. This is one checked
draw with small floating-point differences, not byte-identical skinning or a
general mesh/shader-format qualification. It independently supports the world
space used for the root/body candidate comparisons.

## What this supports

For these source fingerprints, entries, records and captured times, using the
later conflicting records reproduces the measured body/root result. It adds a
new event and two duplicate patterns to the existing evidence: zero-to-animated
body translation and identity-to-placement static root records.

It does **not** uniquely establish replacement, authoring-block ownership,
weighted override, passthrough, or general composition. For entries 2/5,
`zero + animated` equals the later translation. For entry 3, composition with
the earlier identity root also equals the later root. The earlier evc0034
tests rejected specific nonidentity quaternion products; the new degenerate
cases do not extend that rejection to every possible composition rule.

Remaining player cases include the enabled translation conflicts in evc0021:20
and evc0035:33, the hidden evc0008:6 and evc0014:14 cases, and identical-copy cases.
The complete 773-action corpus includes other subjects and greater multiplicity
that these player captures do not cover. Preserve unsupported and identical
records, arbitrary source order, events and correctly relocated TIML payloads.

## Reproduction and validation

Evidence root: `corpus_scans/duplicate_rules/eorzea_20260915/`. The
`user_153431/` directory contains inventory, hashes, thumbnails, selected
extractions and MO2 verification. `analysis_complete/` contains fitted results
and reconstructed arrays; `shader_3000136/` contains the target shader/buffers.

```powershell
python tools/verify_eorzea_runtime_evidence.py --analysis corpus_scans/duplicate_rules/eorzea_20260915/analysis_complete/analysis.json --output corpus_scans/duplicate_rules/eorzea_20260915/verification_new.json
```

The CPU verifier requires system Python 3.10+, NumPy, this checkout's decoder,
the existing scalar research math helper, and the native LMT/MOD3 fixtures.
It rechecks geometry and palette hashes, independently reconstructs world/local
matrices, verifies stable source-slot ownership and completeness of candidate
combinations, and recomputes fitted comparisons plus the independent sweep.
Derived input/output paths must be under `corpus_scans`; output must be new.

Verification passed for **19 captures, 285 draws and 28 fitted candidate
combinations**. Maximum position-error reproduction difference was zero;
maximum angular difference was **0.000000196 degree**. Two verifier runs
produced byte-identical JSON. A changed reported position error, wrong source
slot, and existing output were rejected. Syntax checks passed. Capture sizes
and timestamps remained unchanged after hashing/analysis; native source hashes
and MO2 configuration hashes remained unchanged.

The retained summary is
[benchmarks/duplicate-eorzea-2026-09-15.json](benchmarks/duplicate-eorzea-2026-09-15.json).
No new baking API, GPU dependency or pipeline-speedup claim follows from this
research. RenderDoc/NumPy are investigation tools, not new add-on dependencies.
