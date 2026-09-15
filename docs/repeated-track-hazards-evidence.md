# Hazards capture analysis and scene visibility, 2026-09-15

**Hazards of the Job entry 6 is authored with the hunter's `Draw` property
disabled throughout its scene interval.** This makes it an unsuitable target
for obtaining a normal rendered hunter pose. The earlier capture instructions
missed this visibility track. Additional free-camera screenshots of that interval
do not, by themselves, overcome an explicit scene visibility setting.

This is a scene-scheduling finding, **not a duplicate-track evaluation rule**.
The hidden entry's records remain unresolved and must be preserved. No add-on
playback/export rule, game asset, bakery output, or pinned snapshot was changed.
The four evc0034 cases in [the runtime report](repeated-track-runtime-evidence.md)
remain the qualified duplicate-motion observations.

Subsequent coverage: the [Eorzea investigation](repeated-track-eorzea-evidence.md)
adds five captured target poses across entries 2/3/5. Their measured body/root
results agree with later records. The hidden Hazards entry remains unresolved.

## New captures

The user supplied the 192.302-second Steam video
`C:/Users/akifs/AppData/Local/Temp/steam/386F765DA2BD547B.mp4`
(short alias `386F76~1.MP4`). SHA-256:
`f895aefccf5c6f5e49121e3a11f36958189fdca5af3f2836d0418be0734ae340`.
Its opening Gallery title confirms **Hazards of the Job**. The old `evc0034`
capture filename prefix is only a retained filename template.

There were **17 new RDC files / 27,114,028,783 bytes**: five from 14:12–14:13
and twelve from 14:24–14:27 local time. Every file was hashed, its embedded
thumbnail read, and its D3D12 capture replayed. Sixteen contain verified
Innerwear 501 body draws: **258 matched draws / 15 distinct pose-buffer slices**.
The pair 1927011/1927330 contains the same held pose. Full native vertex-block
hashes identify the body. Independently read 86-joint slices agree byte for
byte across matched draws within each capture.

Capture 1918977 shows the three small characters and contains **no matched body
draw**. Its hunter clip and time cannot be inferred from a body palette. This
is not treated as a target-entry pose or a failed duplicate evaluation.

All 16 recovered poses match ordinary entries **0, 1, 2, 4, 5, 7 and 8**.
There is **no recovered entry-6 pose**. In the latest recording, the interval
around 2:26–2:36 shows the small characters and the clue dialogue. This is a
video-specific visual cue, not a measurement of the game's animation counter.

| Render frame | Fitted entry | Fitted source frame | Unique-arm RMS disagreement, degrees |
| --- | ---: | ---: | ---: |
| 1927011 | 7 | 33.050 | 0.340 |
| 1927330 | 7 | 33.050 | 0.340 |
| 1927641 | 7 | 89.220 | 0.353 |
| 1927937 | 7 | 132.790 | 0.354 |
| 2087326 | 0 | 126.225 | 2.352 |
| 2087572 | 0 | 164.013 | 2.448 |
| 2090629 | 1 | 42.055 | 0.395 |
| 2094725 | 1 | 172.860 | 0.493 |
| 2096743 | 2 | 180.585 | 0.262 |
| 2103967 | 4 | 60.435 | 0.604 |
| 2104513 | 4 | 96.075 | 0.358 |
| 2105260 | 4 | 126.885 | 0.351 |
| 2106793 | 5 | 97.999 | 0.400 |
| 2111101 | 7 | 164.065 | 0.422 |
| 2111416 | 7 | 211.985 | 0.359 |
| 2114005 | 8 | 1.915 | 0.434 |

The search uses eight unique arm rotations across all 25 body entries, then
refines time using only functions 5 and 9. Root/body translation is held out;
no placement correction is fitted. These are inferred times using the existing
add-on decoder and diagnostic NLERP/SLERP alternatives. The two entry-0 samples
have larger disagreement, including 4.22–8.04 native units of body-position
error. They are not animation-accuracy qualification. No quality threshold was
relaxed. The coordinate reconstruction follows the previously checked body
shader/bind convention; no new post-VS shader reconstruction is claimed here.

The earlier 13:56:28 video pass contained 30 RDCs. Ten were replayed, producing
162 matched body draws in ordinary entries 0/5/7/8/9/14/20/24, with entry 7 sampled
three times. Its other 20 RDCs retain hash/header/thumbnail checks only. Across
the two Hazards inventories this is **47 files, 27 replays, 26 recovered poses
and 420 matched draws**. This does not expand duplicate-runtime coverage.

## The missing visibility condition

In native `event/evc0008/evc0008.sdl`, player `Draw` is row 46, track type 11,
property type 3. It contains 25 byte-valued boolean keys at data address 67136.
The motion selector is row 50. Both properties have the same 25 key times.
The motion-list resource resolves to `event/evc0008/pl000_00/pl000_00`.

| Scene tick interval | Selector / candidate entry | Authored Draw |
| --- | --- | ---: |
| 1027–1127 | `0xe005` / 5 | 1 |
| 1127–1519 | `0xe006` / 6 | **0** |
| 1519–1831 | `0xe007` / 7 | 1 |

There are no intervening Draw changes in entry 6's 392-tick interval. The
boolean encoding was cross-checked against the already downloaded RevilLib
source at commit `e17f9718ea571f040a7e1f331c28a4d45a6066b5`:
`src/sdl.cpp` identifies type 11 as BoolTrack and reads one boolean per key;
property type 3 is the boolean property. This extends the existing exploratory
MHW SDL v32 reader; it is not a general-purpose SDL implementation.

The authored setting explains the missing rendered reference and agrees with
the surrounding recovered clips. It does not prove whether the engine still
evaluates a hidden skeleton, whether an unused GPU buffer is current, or which
duplicate record would affect a visible result in another context. No stale or
unbound palette is promoted to evidence. Altering Draw would change the tested
playback context and is not performed by this investigation.

## Visibility audit of all 25 affected player actions

The new read-only utility checks all eight affected player event banks and
their SDLs against the complete native census. It verifies the active motion
resource and reads Draw over every affected selector interval.

**Two conflicting actions are authored hidden:**

| Scene | Entry | Scene interval |
| --- | ---: | --- |
| Hazards of the Job / evc0008 | 6 | 1127–1519 |
| The End Result / evc0014 | 14 | 2373–2438 |

The other **23 actions** have Draw enabled throughout their intervals:
9 conflicting cases and 14 cases whose repeated records are identical. Draw
enabled is a prerequisite; camera/frustum/LOD conditions can still prevent a
matched render draw. The four previously measured evc0034 entries are enabled.

A useful next scene is **A Visitor from Eorzea / evc0074**:

| Entry | Scene interval | Conflicting identities | Candidate difference |
| --- | --- | --- | --- |
| 2 | 487–582 | Body-0 translation | Earlier static zero / later animated |
| 3 | 582–716 | Global root rotation and translation | Earlier identity/zero / later nonidentity placement |
| 5 | 930–986 | Body-0 translation | Earlier static zero / later animated |

All three are authored with Draw enabled. Entry 2 has 131 source frames but
only a 95-tick selector interval, so assuming that every clip is played to its
native end would be wrong. These tick ranges are not wall-clock instructions.
No new game scene has been launched. Gallery availability and actual rendered
coverage still need checking. Addition with zero or composition with identity
can coincide with later selection here, so agreement would not uniquely prove
a universal override rule. Crown of the Ancient Tree entry 20 and Denouement
entry 33 are also enabled. Crown has body-0 and function-30 translation
conflicts; Denouement has tiny function-30/47 translation differences.

## Reproduction and validation

Local evidence is under
`corpus_scans/duplicate_rules/hazards_20260915/user_142751/`:
`inventory.json`, `capture_hashes.json`, `poses/`, `scene_visibility.json`,
`validation.json`, `override_verification/verification.json`, and video contact
sheets. Fitted matrices and detailed errors are in the sibling
`analysis_new_complete/` directory. Earlier Hazards results are in
`user_135628/` and `analysis_selection/`.

```powershell
python tools/inspect_duplicate_scene_visibility.py --source-root 'D:\mh world modding\whole game extract\chunk' --catalogue corpus_scans/duplicate_rules/generalization_20260915/catalogue.jsonl --output corpus_scans/duplicate_rules/hazards_20260915/visibility_new.json
```

The utility requires ordinary Python 3.10+ and the standard library. Output must
be new and inside this checkout's `corpus_scans`, outside the source extract.
It verifies census bank fingerprints, file bounds, property encodings, boolean
values, ancestry, key ordering, resource identity, and unchanged source hashes.
It retains raw packed frame words and parent flags without assigning unsupported
semantics to them. It never edits the native SDL or bank.

Two visibility runs produced byte-identical JSON, SHA-256
`dc460215cf982e7cbbf9e4b3351bde2d5932e1296d0cee456af1aafad2ef3a91`.
Truncated SDL data, a non-boolean Draw byte, an existing output, and an output
inside the native extract were rejected. All 16 repeated pose reconstructions
produced exactly equal saved arrays and equal analysis JSON after normalizing
output paths. Capture sizes/timestamps remained unchanged after hashing and
analysis. Syntax checks passed. MO2's read-only check again found no loose
override for the bank, scene/camera SDLs or body mesh, and its configuration
hashes match the earlier preparation. Packed archives/runtime effects remain
outside that check's scope.

The compact retained summary is
[benchmarks/duplicate-hazards-2026-09-15.json](benchmarks/duplicate-hazards-2026-09-15.json).
RenderDoc replay uses the existing graphics setup; pose analysis uses system
Python with NumPy. These are research dependencies. No NVIDIA/CUDA/PyTorch
dependency, add-on API change, bake optimization or pipeline-speedup claim is
introduced by this work.
