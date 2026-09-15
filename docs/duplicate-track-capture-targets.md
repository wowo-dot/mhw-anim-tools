# Duplicate-track catalogue status and in-game capture targets

Investigated on 2026-09-15. This document identifies existing records and scenes,
then records the subsequently authorized live capture session. No duplicate
playback rule or export behavior has been changed.

**Current priority:** the [native binding investigation](repeated-track-native-binding.md)
has established the skeletal selection rule and replayed all 773 affected clips'
binding instructions. No additional cutscene capture is required to distinguish
first/last/additive pose binding. The capture recommendations below are historical,
not requests for the user to record another scene.

**Capture-target correction:** the subsequent
[Hazards and visibility analysis](repeated-track-hazards-evidence.md) found that
evc0008 entry 6 and evc0014 entry 14 have player `Draw=0` throughout their scene
intervals. Do not request normal rendered hunter captures for those hidden
intervals. All three conflicting player clips in **A Visitor from Eorzea** have
Draw enabled and have now been captured and analyzed; see the
[Eorzea results](repeated-track-eorzea-evidence.md). Five target poses agree with
their later body/root records. Enabled drawing alone does not guarantee camera
visibility. The historical sessions below remain unchanged.

**Historical candidate after Eorzea:** Trouble in the Vale, evc0019 player entry 2,
has 77 complete-content-identical repeated groups, 180 records and 321 native
frames. The verified SDL visibility audit has Draw enabled over ticks 881–1202.
This addresses identical-copy behavior separately from conflicting records.
Its duplicated nonidentity root rotation separates a single application from
the direct doubled-rotation candidate by approximately 45.483858 degrees at
sampled frames 0/80/160/240/320; the nonzero root translation is also repeated.
These are native-source predictions, not runtime observations. They do not
identify first versus last because the copies are identical, and no capture
counter/local-frame alignment has yet been established for this scene.

Crown of the Ancient Tree entry 20 mostly repeats the already tested
zero-to-animated body-translation pattern. Denouement entry 33's conflicting
function-30/47 translation bases differ by only approximately 0.00001144 and
0.00000572 native units, respectively, making first/last separation a poor
target for the present captured-float-matrix method. Its many identical
records are a separate question. These priorities avoid requesting more
captures merely to increase the case count.

Subsequent analysis: see `repeated-track-runtime-evidence.md`. Shader space and
bind reconstruction have now been checked for the selected body draw, and
16 scene captures strongly support later-record body/root motion for evc0034
entries 0/1/4/14. The session stages below are historical; their pending-space
qualifications and six-capture replay count are superseded for that selection
by the new report. Universal duplicate semantics remain unresolved.

The subsequent [full native census](repeated-track-generalization.md) now
records all 773 affected actions and every duplicate slot. It reproduces the
historical totals and initially proposed Hazards of the Job as a contrasting
runtime test; that target is superseded by the visibility correction above.
The missing-catalogue account below describes the earlier investigation
stage, before that complete census was regenerated.

## What was documented previously

The original add-on documentation, already present in commit `af9f900` and
retained in `docs/known-warnings.md`, records repeated `(bone_id, usage)` identities
in **114 / 5,774 LMT files** and **773 / 105,040 actions**. It also documents the
raw-slot import/export path and its lack of resolved visible motion.

These are historical corpus totals, not counts from today's selected-fixture
audit. A complete saved list of all affected files/actions/record slots has not
been located in the current checkout, its local scan reports, or the inspected
historical documentation. Some writer-readiness reports retain capped examples;
the local `lmt_writer_readiness_full.json` currently says `complete: false` and
only 1,000 files processed. That file is not a complete duplicate catalogue.
Absence from these locations does not prove the catalogue never existed elsewhere.

The newer native-fixture audit records every repeated group and original slot in
the seven selected duplicate clips, including complete-content comparisons. It
must not be described as covering all 773 affected actions. Its output is
`corpus_scans/duplicate_rules/evidence.json`; see `repeated-track-research.md`.

## Named scenes from the game's own Gallery data

The authoritative name mapping below comes from the native English
`common/text/cm_gallery_eng.gmd`, using each label's **stored text index**.
Label ordinal and text index differ in this file; matching by ordinal gives
incorrect scene names. The event IDs also match the affected banks' paths.

| Native event | English Gallery title | Pipeline clips | Repeated content in each inspected clip |
| --- | --- | --- | --- |
| `evc0034` | **The Admiral Blows In** | `20036:0`, `20036:1`, `20036:4`, `20036:14` | 33 conflicting groups and 1 identical group |
| `evc0021` | **Crown of the Ancient Tree** | `20023:20` | 2 conflicting groups |
| `evc0014` | **The End Result** | `20016:14` | 2 conflicting groups and 2 identical groups; partial clip |
| `evc0035` | **Denouement** | `20037:33` | 2 conflicting wrist groups and 78 identical groups |

The corresponding bank in each case is
`event/<event>/pl000_00/pl000_00.lmt`. Pipeline bank numbers are labels from the
bakery, not the game's Gallery IDs.

Native Gallery descriptions identify the first scene as the Admiral's arrival
during the subspecies investigation, the second as the Rathalos encounter while
seeking the First Wyverian, the third as the interrupted capture operation, and
the fourth as the celebration after resolving the Elder Crossing mystery.
The inspected `evc0034` subtitles independently mention the Admiral's return;
`evc0021` mentions Rathalos; `evc0014` mentions a hunter from the First.

Gallery is accessible from the title menu. Capcom's official release notes
document its addition there. The user's 2026-09-15 video confirms that The Admiral
Blows In is available on their selected hunter's save. Other scenes remain unverified.
[Capcom: Gallery Mode in the title menu](https://news.capcomusa.com/lets/browse/monster-hunter-world-launches-on-playstation-4-and-xbox-one-details-on-day-1-patch-revealed)

## Recommended first reference

Start with **Title menu -> Gallery -> The Admiral Blows In**, selecting the
intended hunter when prompted. It provides four conflicting body/root clips in
one named scene. The existing first/last experiment for entry 0 at local frame
135 produces a large posture difference, making it a useful discriminator. It
is easier to distinguish than the tiny wrist differences in Denouement.

The exploratory SDL v32 reader finds the following selectors on
`pl000_00/LayerWork/MotionWork/mMotionNoHex` in `event/evc0034/evc0034.sdl`:

| Candidate LMT entry | Raw selector | Scene timeline tick | Next selector tick |
| --- | --- | ---: | ---: |
| 0 | `0xe000` | 0 | 270 |
| 1 | `0xe001` | 270 | 410 |
| 4 | `0xe004` | 1040 | 1310 |
| 14 | `0xe00e` | 3421 | 3551 |

The low 12 selector bits matching entry IDs remain an explicit interpretation.
The opening of the body timeline is the initial capture target. Exact alignment
between scene ticks, local LMT frames, playback speed, and wall-clock seconds
still needs runtime verification. **RenderDoc's frame number is not an LMT frame
number.** Do not instruct the user to capture at a guessed number of seconds or
treat a visually similar pose as proof of frame alignment.

Before the next live reference session, verify the effective animation bank is
the original source rather than an installed retargeted replacement. Then capture
a visible hunter draw during the opening and identify its actual clip/time.
Further captures should cover the later conflicting entries and ordinary motion
controls. The live capture setup prepared on 2026-09-15 is documented below.
Mod selections and installed assets were not changed.

## Existing RenderDoc workflow to reuse

The earlier Panam workflow is available under:

`D:/mh world modding/base body/Panam_MHW_Base_v20/junction_rebuild/game_validation`

Its `capture_ledger.json` records five retained static game-pose captures. The
saved `extraction.json` reports successful D3D12 replay. The extractor identifies
body draws through complete vertex-buffer hashes, reads `gJointMatrixBuffer`,
and the saved converted poses report identical palettes across six verified body
draws. This is existing evidence, not a newly repeated capture validation.

Relevant files are `extract_motion_palette.py`, `convert_motion_palettes.py`,
`capture_ledger.json`, and `Review.md`. The scripts contain hardcoded paths and
write into the old project, so they must be adapted into this add-on's isolated
research workspace before execution. Do not run them in place or alter their
old requests, captures, launch configuration, or production overlays.

Final skinning matrices are useful independent pose evidence, but can include
procedural/IK contributions and may omit unweighted bones. Palette indices,
bind transforms, coordinate spaces, root placement, and animation timing must
be matched explicitly. The old static captures do not establish the runtime
rule for these newly identified clips.

## Reproduction

```powershell
python tools/locate_duplicate_capture_targets.py --source-root 'D:\mh world modding\whole game extract\chunk' --output 'corpus_scans/duplicate_rules/capture_targets.json'
```

This standalone Python 3.10+ research script reads the observed unencrypted GMD
variant, four native LMT banks, and one SDL. It writes only the requested JSON
outside the extract. The JSON includes source hashes, Gallery keys and text
indices, duplicate-group counts, and provisional selector ranges. Source hashes
are checked again after inspection. There is no Blender, CUDA, PyTorch, or NVIDIA
dependency in this identification step.

Verification passed: native label/text-index mapping, all seven clip checks, six
unchanged source hashes, byte-identical JSON on repeat, rejection of an output
inside the extract, and rejection of a truncated GMD. Result SHA-256:
`a6780af9627d958b7bd8135893db5a081e4e0752fc046acf62898b7b287f02a0`.

## Live preparation, 2026-09-15

The supplied 145.277-second video, `C:/Users/akifs/Videos/Monster Hunter- World -
2026-09-15 11-36-39 AM.mp4`, shows The Admiral Blows In and its Gallery title.
It is a visual reference, without verified LMT frame alignment.

The existing portable RenderDoc 1.46 was launched through the current MO2
Default profile, using `tools/prepare_renderdoc_capture.py`. MHW PID 24472
loaded both `renderdoc.dll` and `usvfs_x64.dll`; its overlay reported D3D12 and
F12 / Print Screen capture shortcuts. The current session reached Gallery.
The PID and RenderDoc target ID are session-specific, not persistent settings.

Artifacts are isolated in `corpus_scans/duplicate_rules/live_20260915/`:

- `verification.json` and `launch.json`: source hashes, enabled mod list,
  effective loose-file checks, launcher paths and capture template.
- `probe.json`: successful target-control connection, PID 24472 / target 38920.
- `smoke_capture.json`: one title-screen frame, 83027, saved as a 1,141,436,801-byte
  RDC in `captures/`. Despite the `evc0034` filename prefix, this is only a setup
  test and **not a captured cutscene or duplicate-track pose reference**.
- `smoke_replay.json`: OpenFile and OpenCapture both succeeded; D3D12 replay
  exposed 790 root actions. `smoke_thumbnail.png` visually confirms the title screen.
- `video/overview.png`: contact sheet from the user's recording.

MO2 INI and Default modlist hashes still matched their pre-launch values after
the test. None of the three target LMT/SDL files had a loose MO2 override.
This does not qualify packed archives or runtime plugin effects. Hunter geometry
and palette extraction were subsequently checked below; exact clip/time alignment
and coordinate-space reconstruction remain necessary before deriving rules.

`prepare_renderdoc_capture.py` requires the existing system Python 3.10+ and
uses machine-specific MO2/game/extract/RenderDoc paths. Without `--launch` it
only verifies; `--launch` refuses while MHW is already running. Example from
the checkout: `python tools/prepare_renderdoc_capture.py --output
corpus_scans/duplicate_rules/live_20260915 --launch`.

`renderdoc_capture_control.py` runs under the existing `qrenderdoc.exe --python`.
Set `MHW_RD_PROJECT` to the checkout and `MHW_RD_REQUEST` to an absolute JSON
request path within its `corpus_scans` directory. Request keys are `mode`
(`probe` or `capture`), `report` (absolute JSON destination under `corpus_scans`),
and `expected_pid` (required for capture). Capture requests take one frame,
ignore prior capture announcements, and report a bounded timeout if no new
capture arrives. Connections never force takeover of another client.
Both modes were exercised against the live session. RenderDoc's embedded
Python is 3.8 and its script namespace does not supply `__file__`.

These are external research utilities: no Blender add-on dependency, PyTorch,
CUDA, or NVIDIA requirement was introduced. Research captures establish neither
the duplicate evaluation rule nor animation-baking performance.

## Captured hunter references

The user identified the equipment as innerwear and cloth scarf. Blender 4.5.10
at `D:/blender-4.5.10-windows-x64` and the existing MHW Model Editor parsed the
native Innerwear 500 and 501 MOD3 files. Complete vertex-buffer SHA-256 matches
identify the captured body as **Innerwear 501**, with an 86-bone source skeleton.
Meshes 0, 1 and 2 matched. This verifies body geometry, not the source animation
bank, scarf simulation, or every character component.

The user-provided Otis tools in `D:/world tools/MHW_CameraTools_v100c` were already
injected into the game. The Image Quality / Game speed slider successfully held
poses at zero; the numeric reduced playback rate was not calibrated. Keyboard
timestop/frame-skip inputs were unreliable and were not used as timing evidence.
The native scene camera was used. After capture, Game speed was switched OFF
and the scene returned to Gallery. Game and camera client were left running.

All captures remain under `corpus_scans/duplicate_rules/live_20260915`:

| Label | Render frame | Recorded content | Matched body draws |
| --- | ---: | --- | ---: |
| `smoke_capture` | 83027 | Title screen; setup only | Not extracted |
| `opening_01` | 197082 | First replay, NPC close-up; context only | 18 |
| `opening_slow_02` | 272494 | Second replay, opening wide shot, hunter from behind | 15 |
| `hunter_hold_03` | 279576 | Held opening hunter close-up | 18 |
| `hunter_hold_repeat_04` | 292604 | Repeat of the same held pose | 18 |
| `hunter_later_05` | 429461 | Held later hunter close-up with crystal | 18 |

Every listed RDC replayed successfully as D3D12. `capture_ledger.json` records
the capture sizes and SHA-256 hashes, source/configuration preservation checks,
thumbnail paths and unresolved timing. **Use `poses/*_v2/extraction.json`**:
version 2 reads each palette independently at its draw event and deduplicates
saved files by content hash. Earlier extraction folders cached by resource
identity, which cannot independently establish agreement across draw events.
The RDC files themselves are unchanged.

`comparison_hunter/comparison.json` compares the four selected hunter captures.
With the earlier workflow's explicit layout interpretation (little-endian
float32, three rows of four values per joint, `iMatrixIndex` in joints), all
86-joint slices are finite and byte-identical across matched draws within each
capture. The two frozen opening captures also have byte-identical slices and
identical model-world constants, despite different render frame numbers.
The opening wide shot and later crystal pose differ from the held opening pose.
The raw difference magnitudes are **not animation errors**: timing and transform
space have not been aligned.

Raw palettes, all reflected vertex-shader constants, draw identifiers, buffer
offsets, geometry hashes and model-world matrices remain available. Compressed
NumPy arrays preserve the selected raw joint rows for **every** matched draw.
No root removal, bind conversion, blending, or track selection is applied.
The palette layout still needs shader verification and a bind-space reconstruction
before these rows can be compared quantitatively with Blender motion. Procedural
contributions and unweighted bones also need qualification. No capture is yet
assigned an authoritative LMT entry or frame, and no runtime duplicate rule has
been established.

## Research utility integration

These scripts live outside the add-on's import/export execution path:

- `tools/prepare_renderdoc_geometry.py`: run with Blender `--background --python`
  and arguments after `--`: repeat `--source <native MOD3>` and specify
  `--output <new geometry JSON under corpus_scans>`. Requires the separately
  installed MHW Model Editor; does not import a scene or save preferences.
- `tools/extract_renderdoc_joints.py`: run with RenderDoc 1.46 `qrenderdoc --python`.
  Set `MHW_RD_PROJECT` and `MHW_RD_REPLAY_REQUEST`. The request JSON contains
  absolute `capture`, `geometry`, and new `output` directory paths under
  `corpus_scans`. Matches complete vertex blocks, preserves palettes and constants,
  and does not control the game. Vertex buffers larger than 64 MiB are skipped
  and reported. Matching uses index count and vertex contents; it does not yet
  verify the draw's exact index-buffer contents or reconstruct skinned positions.
- `tools/compare_renderdoc_joints.py`: run with system Python and NumPy,
  repeat `--extraction <v2 extraction.json>`, specify `--source-index 1` for the
  recorded two-source geometry report, and `--output <new directory under
  corpus_scans>`. Requires successful version-2 extraction, verifies geometry
  and palette hashes, bounds and finiteness, and rejects existing outputs.

Live capture, all five cutscene replays, full vertex matches, frozen-pose
repeatability, per-draw comparisons and Python syntax checks were exercised.
The two MO2 configuration files, three target animation/scene files and two
native MOD3 files retained their recorded hashes. Production bake outputs,
pinned snapshots and installed game assets were not edited. No baking-agent
API change or NVIDIA dependency is needed to consume this research evidence.

## User free-camera capture pass, 12:35–12:41

The user supplied `C:/Users/akifs/Videos/Monster Hunter- World - 2026-09-15
12-41-55 PM.mp4`, a 412.032-second 2560x1440 recording at 60 FPS. The visible
Gallery title confirms **The Admiral Blows In**. Sampled video frames and all
RDC thumbnails show expanded hunter coverage through opening movement,
conversation, crystal-holding poses and the departure. Some views have partial
occlusion; the number of distinct LMT animations covered is not established.

There are **31 additional RDCs**, totaling 108,560,455,346 bytes. All opened
successfully for embedded thumbnail extraction and were hashed without moving
or editing them. The video's RenderDoc overlay increases from 6 to 37 saved
captures, matching the 31 new files. Manually read overlay frame numbers at
sampled timestamps locate every new RDC within a bounded recording interval;
these intervals are not LMT frame ranges or wall-clock estimates.

The research snapshot is `corpus_scans/duplicate_rules/live_20260915/user_124155/`:

- `README.md` and `review.json`: complete 31-capture index, video intervals,
  verification levels, hashes, and limitations.
- `captures_01.jpg` through `captures_03.jpg`: visual index of every RDC.
- `video_01.jpg`, `video_02.jpg`, `video_alignment.json`: recording samples and
  the transcribed overlay evidence linking the recording to the RDCs.
- `poses/frame*/extraction.json`: six selected version-2 palette extractions.
- `comparison/comparison.json` and NPZ files: all per-draw joint slices and
  model-world constants for that selection.

Render frames **605776, 617442, 631350, 637439, 647900 and 652472** replayed
successfully as D3D12. Complete native Innerwear 501 vertex hashes matched
12, 18, 18, 18, 15 and 18 body draws respectively, **99 draws total**. Each
selected capture's 86-joint slices are finite and byte-identical across its
matched draws; the six selected captures have six different slice hashes.
The remaining **25 RDCs have header/thumbnail validation only**. No claim of
all-capture replay validation, exact clip alignment, or resolved duplicate
evaluation follows from this pass. The coordinate-space qualifications above
still apply. Only isolated research outputs and this documentation were written.
