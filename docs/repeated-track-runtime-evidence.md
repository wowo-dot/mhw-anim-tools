# Repeated-track runtime evidence: evc0034, 2026-09-15

**Later result:** [native instruction analysis and replay](repeated-track-native-binding.md)
establishes the general skeletal binding rule and its separate control-reader
limits. This report retains the narrower claims supported by its captures alone.

The saved game captures strongly support **the later records as the evaluated
body/root motion in evc0034 entries 0, 1, 4 and 14**. Earlier-record selection
and the tested quaternion multiplication candidates disagree substantially.
This supplies an independent reference case for implementation. It does **not**
establish a universal last-record-wins dispatch rule for MHW LMT.

The subsequent [generalization investigation](repeated-track-generalization.md)
catalogues the full native corpus and identifies contrasting cases for further
captures. It does not extend this report's verified runtime coverage.

The subsequent [Hazards capture analysis](repeated-track-hazards-evidence.md)
adds a scene-visibility prerequisite: evc0008:6 and evc0014:14 are authored
with player drawing disabled. Their binding was subsequently covered by the
native-instruction corpus check; visibility does not change that selection rule.

The [Eorzea follow-up](repeated-track-eorzea-evidence.md) adds measured agreement
with later body/root records for evc0074 entries 2/3/5. Their zero/identity
earlier records leave composition alternatives indistinguishable in that set;
they do not establish universal ordered replacement.

No add-on playback, decoder, retargeting, export ownership or installed build
was changed by this investigation. The existing CPU throughput changes are
separate. No throughput claim follows from this analysis.

## Evidence and identification

The user recorded **The Admiral Blows In**, wearing Innerwear 501 with a cloth
scarf, and supplied 31 additional RenderDoc captures plus the 12:41:55 video.
Five more of that pass's captures were replayed during this analysis, bringing
the replayed user selection to **11 captures / 183 matched body draws**. Together
with the earlier five scene captures, this analysis uses **16 captures / 270
matched draws**. Two earlier captures contain the same held pose, so this is
15 distinct pose-buffer samples. The other 20 user captures retain header and
thumbnail validation only.

The native source files are:

| Source, relative to the native `chunk` extract | SHA-256 |
| --- | --- |
| `event/evc0034/pl000_00/pl000_00.lmt` | `db0fba34294e47e0539d81bc36d919f7f8ba160922e389c92516df08da70b5bc` |
| `pl/f_equip/pl501_0000/body/mod/f_body501_0000.mod3` | `bfdf5604a6d09892621df415bec1e06cd800d662888f8a31462d97e7fed42c64` |

The MO2 read-only verification found no loose override for these sources or the
scene/camera SDLs. Configuration hashes stayed unchanged. Packed archives and
runtime plugin effects are not exhaustively qualified by that check.

Full vertex-block hashes identify Innerwear 501. Palette contents were read
independently at every matched draw, then deduplicated by content. All 86-joint
slices agree byte for byte across matched draws within each capture. These
checks use extractor version 2; earlier version-1 comparisons are not evidence
of independent per-draw reads.

## Coordinate-space verification

For render frame **617442**, draw **21720**, the saved vertex shader reads three
float4 joint rows at `3 * (iMatrixIndex + vertexJointIndex)`. It weights those
matrices and transforms mesh positions directly into world space, then applies
view-projection. Applying `fWorld` again would apply placement twice.

CPU reconstruction from the saved input buffers agrees with the captured
post-vertex-shader `WorldPosition` for **6,228 index references / 1,236 distinct
vertices**:

| Error | Native source units |
| --- | ---: |
| Maximum component difference | 0.000659127447 |
| Maximum position distance | 0.000717426757 |
| Mean position distance | 0.000192209632 |

The draw's exact index-buffer hash also matches native mesh 2. These are small
floating-point differences, not bit-identical output or a complete animation
accuracy test. This post-VS check covers one draw; it does not claim every
shader or mesh format was reconstructed.

For this MOD3, the first matrix block contains local bind transforms and the
second contains inverse global bind transforms, in transposed storage relative
to the column-vector convention used here. The hierarchy reconstructed from
those blocks agrees within **5.72205e-6** maximum matrix-component difference.

```text
posed_world[i] = captured_skin_matrix[i] @ global_bind[i]
posed_local[i] = inverse(posed_world[parent[i]]) @ posed_world[i]
```

Unparented bones retain their world transforms. No root removal or camera fit
is used for the numerical comparisons. Polar decomposition extracts rotation
from the reconstructed local matrix; reflection is rejected.

## Clip and time matching

Clip candidates were searched across all 16 body entries in this bank, using
only nonduplicate local rotations for functions 5/6/7/8/9/10/11/12. The best
entry is clearly separated from other entries for the selected samples.
Quaternion inversion was also tested and was not the winning convention.

Time was then refined using only the nonduplicate rotations for functions 5
and 9. The other ordinary channels and **all conflicting records** are holdouts.
Root position/orientation never participates in fitting.

The table's times are **fitted source-frame coordinates**, not values read from
a game animation counter. NLERP and SLERP are diagnostic alternatives; selecting
the smaller fitting loss does not establish the engine's interpolation rule.
One refinement (`622312`) reaches the end of its search interval, so its time
is especially provisional. The source decoder is the add-on's decoder, not an
independently qualified decoder. Action-header-derived root tails are not used
for these interior-frame comparisons.

## Conflicting body rotations

Each of these actions has 187 ordered records: an earlier 107-record block and
a later 80-record block. There are 34 repeated identities, 33 with different
complete record contents. The sampled records have joint type 0, unknown tag
205 and weight 1.0. A block split is descriptive; no runtime block-selection
flag has been decoded.

The table measures RMS angular disagreement across the **21 duplicated local
rotation identities that have a parent**. It excludes global root and the five
unparented control bones.

| Capture / render frame | Inferred entry | Fitted frame | Earlier record, degrees | Later record, degrees | Later root/body-0 position error, native units |
| --- | ---: | ---: | ---: | ---: | ---: |
| User 605776 | 0 | 40.176 | 68.755 | 0.058 | 0.02330 |
| User 615673 | 0 | 164.209 | 70.145 | 0.042 | 0.01459 |
| Earlier opening 272494 | 1 | 58.315 | 69.253 | 0.093 | 0.16001 |
| Earlier opening 197082 | 4 | 34.463 | 71.552 | 0.078 | 0.04134 |
| User 621367 | 4 | 26.486 | 71.519 | 0.054 | 0.03306 |
| User 621965 | 4 | 154.836 | 71.888 | 0.105 | 0.01470 |
| User 622312 | 4 | 223.250 | 73.446 | 0.140 | 0.02094 |
| User 634147 | 14 | 37.896 | 63.596 | 0.030 | 0.01968 |

The tested products `first @ last`, `last @ first`, and both products with an
interposed inverse local bind rotation have approximately **52.6 degrees RMS**
error. These specific candidates are rejected; this does not test every
possible weighted, reference-relative, or context-selected operation.

There is an important coverage distinction. All 21 measurements come from the
captured joint palette, but only functions **1, 2, 3, 4 and 13** are directly
weighted to the verified Innerwear body geometry. Across those five identities,
earlier records give **58.181–87.916 degrees RMS**, later records
**0.023–0.198 degrees RMS**, and the products about **47.2 degrees RMS**.
The other 16 identities are palette evidence; their influence on other equipped
meshes has not been independently verified here. No unused record is discarded.

A sensitivity check evaluated 81 times over fitted time ±4 source frames,
using both NLERP and SLERP, for all 21 identities and separately the five
directly weighted identities. Later selection beat first and both direct
multiplication candidates at **every tested time in all 32 scenarios**.
The worst later RMS in that wider interval was 3.007 degrees; the best first
RMS was 58.181 degrees. This qualifies the separation between candidates, not
the fitted timestamp or production accuracy.

## Root and control evidence

For body function 0, compare the captured world transform against:

```text
LMT_root_transform @ body_function_0_local_transform
```

All eight combinations of earlier/later root rotation, root translation and
body-0 translation were checked. Using the later records gives the position
errors in the table and less than 0.00001 degree orientation disagreement.
Using all earlier records gives **2345–2490 native units** position error and
**114.160 degrees**, or **132.366 degrees for entry 14**, orientation error.
No placement transform is fitted to obtain those results.

Controls 249–253 were also compared under the later root, retaining their
unparented native skeleton representation. Later candidates agree within
0.151 native units and 0.143 degrees in the examined samples. In particular,
control 253's later inverse-root transform produces the identity world matrix
observed in its palette slot. This is useful evidence of the control/root
relationship, not proof of the control's gameplay purpose.

These controls are unweighted to the verified body mesh. Identical translation
records on 251, and almost identical rotations on 251/252, cannot establish a
selection or accumulation rule from these captures. Preserve both records.

## Ordinary controls and remaining uncertainty

The other captures align to ordinary entries **2, 12, 17, 25 and 30**. The two
frozen opening captures align to entry 2, not conflicting entry 0. They confirm
repeatability but are not two independent tests of duplicate handling.

Ordinary single-track holdout RMS disagreement is **0.114–0.282 degrees** at the
fitted times. Individual ordinary arm joints reach approximately 0.92 degree.
Therefore the small remaining differences cannot all be attributed to duplicate
selection. Timing, interpolation/codec details, and procedural contributions
are still possible explanations. A constant correction was not established and
none was applied. No existing animation-quality tolerance has been relaxed.

The following remain unqualified:

- Universal sequential overwrite versus selection of a later authored block or
  another context rule that produces the same result on these four fixtures.
- Different weights, joint modes, unknown flags, or more than two records.
- General identical-record collapse, tiny function-30/47 translation conflicts
  in `evc0035:33`, body-0/function-30 translation conflicts in `evc0021:20`, and
  partial/base-action composition in `evc0014:14`.
- Exact engine time, subframe interpolation, loop/end boundaries, and all
  procedural/IK/cloth effects. Cloth scarf motion is not analyzed.
- Blender helper playback, save/reopen, retargeted output accuracy, edited-track
  export, and source-preserving round trips for a future evaluator.

## Reproduction and checks

Local analysis lives under
`corpus_scans/duplicate_rules/runtime_20260915/`. The compact checked-in numeric
summary is `docs/benchmarks/duplicate-runtime-2026-09-15.json`.

`tools/verify_duplicate_runtime_evidence.py` re-reads the native bank/skeleton,
checks recorded geometry/palette hashes and per-draw equality, independently
reconstructs saved world/local transforms, and recomputes the reported duplicate
and root comparisons at the recorded fitted times. It accepts only this source
bank/body fingerprint, restricts derived input/output paths to `corpus_scans`,
and rejects an existing output file.

```powershell
& 'C:\Users\akifs\AppData\Local\Programs\Python\Python310\python.exe' tools/verify_duplicate_runtime_evidence.py --runtime corpus_scans/duplicate_rules/runtime_20260915 --output corpus_scans/duplicate_rules/runtime_20260915/verification_new.json
```

Verification passed for **16 captures, 270 matched draws, 1,008 duplicate
rotation candidate checks and 128 root combinations**. Reproduction differences
were at most 0.000002415 degree; root-position errors reproduced exactly. Two
runs produced byte-identical JSON. A deliberately changed angular result and an
attempt to reuse an existing output path were rejected. Script syntax passed.
These are research validation checks, not Blender or full add-on regression tests.

The local `reproduction_bundle.zip` contains the analysis scripts, reports,
small reconstructed pose arrays, and a manifest. It excludes native source
assets, videos and RDCs; the large captures and referenced buffer extracts must
remain available locally. Source paths are specific to this workstation.

Analysis requires **NumPy in system Python**. Capture extraction used RenderDoc
1.46; initial MOD3 geometry inspection used Blender 4.5.10 and the existing MHW
Model Editor. These are research tools, **not add-on dependencies**. Neither the
analysis nor the proposed Blender evaluator requires PyTorch, CUDA or NVIDIA.

The bakery, pinned snapshots, native extracts and installed game assets were
not edited. See `duplicate-track-baking-integration.md` for the implementation
boundary this evidence supports.
