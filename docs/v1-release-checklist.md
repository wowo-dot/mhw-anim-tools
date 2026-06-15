# MHW Anim Tools V1.0 Release Checklist

This checklist defines the release gate for the first public version of
`mhw_anim_tools`.

The goal of `v1.0.0` is not "feature-complete forever." The goal is a
trustworthy Blender 4.5+ workflow for Monster Hunter World animation editing
where users can import, inspect, edit, export, and reimport LMT data with
embedded TIML safely and predictably.

## Current status snapshot

What is already true today:

- the new add-on has a working clean-room LMT core reader/decoder
- supported LMT action import works in Blender 4.5 with MHW-style armatures
- supported LMT export works through the new source-aware merge path
- attached TIML controllers can be imported, analyzed, edited, and written back
  conservatively inside source-backed LMT export
- import-all-actions and source-container impact analysis already exist
- unit tests and smoke tools cover the core rewrite path far beyond the first
  grindstone sample

What is not ready to call "release done" yet:

- broader real-asset validation and manual Blender validation across a
  representative spread
- workflow docs and fresh-install docs
- final public-repo cleanup and release packaging

See also:

- `docs/v1-validation-matrix.md`

## V1.0 scope

`v1.0.0` must include:

- reliable `LMT` import/read/inspect
- reliable `LMT` edit/export/reimport for supported track families
- reliable embedded `TIML` import/read/edit/write inside source-backed LMT export
- multi-action workflow support inside one source `.lmt`
- batch workflow support where it materially improves real editing use
- import-all-actions workflow for source `.lmt` files
- clear diagnostics and safe blocking when the tool cannot preserve semantics

`v1.0.0` does **not** require:

- `EFX` authoring/import/export
- experimental format coverage presented as stable
- lossy fallback behavior hidden behind a successful export button

## Release principles

Before public release, the tool should be:

- honest about unsupported cases
- deterministic on repeated import/export cycles
- safe for source-backed LMT/TIML workflows
- understandable to maintain
- installable and usable on a clean Blender 4.5 setup

## Release gates

### 1. LMT import is trustworthy

- [ ] selected-action import works reliably on real game assets
- [ ] imported actions bind correctly to MHW-style armatures
- [ ] root motion remains correct on supported rigs
- [ ] quaternion handling is stable and does not introduce preview flips
- [x] diagnostics clearly report skipped tracks, unsupported buffers, and binding failures
- [x] real-asset smoke coverage exists beyond grindstone

Current status note:

- selected-action import, armature binding, and pose-space adaptation are
  implemented and have both synthetic and live MOD3 smoke coverage
- embedded TIML suite assets now exercise real LMT import paths beyond
  `stm730_084_00`
- the remaining release gate is confidence: root motion, quaternion stability,
  and broader manual playback checks still need representative real-asset signoff

### 2. LMT export is trustworthy

- [x] supported edited actions export without traceback
- [x] exported `.lmt` files reimport successfully in this tool
- [x] exported `.lmt` files preserve untouched sibling actions in source-backed mode
- [x] export blocks unsafe standalone cases instead of silently dropping data
- [x] duplicate `bone_id + usage` track identities are rejected clearly
- [ ] buffer-family promotion/preservation/fallback behavior is documented and tested
- [ ] real-asset export/reimport validation covers a representative asset spread

Current status note:

- the writer/export-prep chain is now conservative, validated, and source-aware
- standalone export intentionally blocks unsafe TIML/container cases
- writer/read-decode roundtrip coverage exists, but final v1 confidence still
  depends on a wider real-asset export/reimport matrix and user-facing workflow
  documentation for what is preserved, promoted, or blocked

### 3. Embedded TIML workflow is trustworthy

- [x] attached TIML payloads import into controller actions reliably
- [x] controller analysis correctly reports:
  - [x] value-only transforms
  - [x] rebuild-capable transforms
  - [x] blocked transforms
  - [x] shared-payload scope across sibling source actions
- [x] unchanged TIML controllers preserve raw source payloads
- [x] value-only TIML edits write back without destroying advanced source semantics
- [x] supported simple-source structural edits rebuild safely
- [x] unsupported structural edits block clearly and intentionally
- [x] shared embedded TIML payloads update safely across all linked source actions
- [ ] real-asset TIML edit/export/reimport validation passes on multiple files

Current status note:

- this is the strongest part of the current v1 path after core LMT import/export
- value-only, shared-payload, and simple-source structural workflows all have
  targeted tests and live smoke tools
- the remaining gap is not basic capability; it is corpus breadth and release
  confidence across more real assets and edit shapes

### 4. Multi-action and batch workflow is ready

- [x] import-all-actions exists for source `.lmt` files
- [x] imported actions remain traceable back to source entry IDs and source containers
- [ ] batch-oriented workflow does not break per-action diagnostics
- [x] export path for multiple actions inside a source container is explicit and predictable
- [x] users can tell which edited action/controller will affect which source entries
- [x] basic batch smoke coverage exists for import and source-backed export

Current status note:

- the workflow path exists and is already much safer than the original
  one-action-only assumptions
- what remains is hardening around batch ergonomics and making sure diagnostics
  stay readable when many imported actions/controllers coexist in one scene

### 5. UI/UX is ready for public users

- [x] sidebar remains focused on workflow shortcuts and status, not crowded editing UI
- [x] detailed TIML inspection lives in the proper inspector surface
- [x] import, analyze, and export flows surface actionable status text
- [x] failures show diagnostics instead of raw tracebacks
- [ ] target armature and source-context behavior is clear to a first-time user
- [ ] install-from-zip test passes on a clean Blender profile

Current status note:

- the add-on now has a sane UI contract, and TIML no longer threatens to take
  over the sidebar
- the remaining work here is first-time-user clarity, install validation, and a
  short documented workflow instead of more UI surface area

### 6. Documentation is minimally complete

- [x] README describes the tool's actual supported scope, not aspirational scope
- [ ] installation instructions are correct
- [ ] one basic LMT workflow is documented
- [ ] one TIML-in-LMT workflow is documented
- [x] known limitations are listed honestly
- [ ] release notes explain what is safe, what is blocked, and why

Current status note:

- README scope honesty is in a decent place now
- release docs are still thin, and v1 needs one clean user workflow for basic
  LMT editing plus one for TIML-in-LMT editing before we call it public-ready

### 7. Public repository cleanup is complete

- [x] public-facing docs do not market the project as a FreeHK patch/port
- [ ] code comments avoid unnecessary `FreeHK` / `freehk` naming where not historically required
- [ ] local-only legacy comparison helpers are removed from the public repo or moved behind clearly internal naming
- [x] public module names, operator names, and docs reflect `mhw_anim_tools`
- [x] license/readme text accurately describes the clean-room architecture and current dependencies

Current known public-cleanup references to revisit before release:

- `core/formats/lmt/semantics.py`
- `tools/compare_legacy_lmt.py`

Current status note:

- the repo already reads like a rewrite much more than a patch pile
- before public release we still need one deliberate cleanup pass for legacy
  comparison helpers, comment wording, and anything that feels private/internal

### 8. Release engineering is ready

- [ ] git history is in a presentable state for public launch
- [ ] version number and changelog are prepared
- [ ] release zip is tested from a fresh install
- [ ] GitHub repository visibility can be switched to public cleanly
- [ ] Nexus release package and description are prepared

## Priority order before release

1. Finish trustworthy `LMT` + embedded `TIML` read/edit/write
2. Finish multi-action and import-all-actions workflow
3. Expand real-game validation and smoke coverage
4. Clean public-facing repository references and docs
5. Do release-candidate packaging, install, and documentation pass
6. Publish `v1.0.0`

## Immediate next release-confidence tasks

1. Fill the validation matrix with current automated results from the real-asset
   TIML suites and selected LMT smoke runs
2. Run a representative manual Blender pass across the release-candidate asset
   set
3. Document one basic LMT edit/export workflow and one TIML-in-LMT workflow
4. Do a clean-profile install test from a zip package
5. Perform the public repo cleanup pass before switching visibility

## Explicit non-goals before v1.0

Do not delay `v1.0.0` for:

- `EFX`
- speculative UI redesign
- broad feature creep unrelated to reliable LMT/TIML workflows
- perfect coverage of every rare legacy edge case before we have a stable public base

## Definition of done for v1.0

We can confidently make the repository public and publish a Nexus release when:

- supported LMT/TIML workflows succeed reliably on real assets
- unsupported workflows fail safely and explain why
- users can batch-import and manage multi-action source files sanely
- documentation matches reality
- the public repo looks like an original maintainable project, not a legacy patch pile
