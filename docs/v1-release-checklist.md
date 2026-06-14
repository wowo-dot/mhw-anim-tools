# MHW Anim Tools V1.0 Release Checklist

This checklist defines the release gate for the first public version of
`mhw_anim_tools`.

The goal of `v1.0.0` is not "feature-complete forever." The goal is a
trustworthy Blender 4.5+ workflow for Monster Hunter World animation editing
where users can import, inspect, edit, export, and reimport LMT data with
embedded TIML safely and predictably.

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
- [ ] diagnostics clearly report skipped tracks, unsupported buffers, and binding failures
- [ ] real-asset smoke coverage exists beyond grindstone

### 2. LMT export is trustworthy

- [ ] supported edited actions export without traceback
- [ ] exported `.lmt` files reimport successfully in this tool
- [ ] exported `.lmt` files preserve untouched sibling actions in source-backed mode
- [ ] export blocks unsafe standalone cases instead of silently dropping data
- [ ] duplicate `bone_id + usage` track identities are rejected clearly
- [ ] buffer-family promotion/preservation/fallback behavior is documented and tested
- [ ] real-asset export/reimport validation covers a representative asset spread

### 3. Embedded TIML workflow is trustworthy

- [ ] attached TIML payloads import into controller actions reliably
- [ ] controller analysis correctly reports:
  - [ ] value-only transforms
  - [ ] rebuild-capable transforms
  - [ ] blocked transforms
  - [ ] shared-payload scope across sibling source actions
- [ ] unchanged TIML controllers preserve raw source payloads
- [ ] value-only TIML edits write back without destroying advanced source semantics
- [ ] supported simple-source structural edits rebuild safely
- [ ] unsupported structural edits block clearly and intentionally
- [ ] shared embedded TIML payloads update safely across all linked source actions
- [ ] real-asset TIML edit/export/reimport validation passes on multiple files

### 4. Multi-action and batch workflow is ready

- [ ] import-all-actions exists for source `.lmt` files
- [ ] imported actions remain traceable back to source entry IDs and source containers
- [ ] batch-oriented workflow does not break per-action diagnostics
- [ ] export path for multiple actions inside a source container is explicit and predictable
- [ ] users can tell which edited action/controller will affect which source entries
- [ ] basic batch smoke coverage exists for import and source-backed export

### 5. UI/UX is ready for public users

- [ ] sidebar remains focused on workflow shortcuts and status, not crowded editing UI
- [ ] detailed TIML inspection lives in the proper inspector surface
- [ ] import, analyze, and export flows surface actionable status text
- [ ] failures show diagnostics instead of raw tracebacks
- [ ] target armature and source-context behavior is clear to a first-time user
- [ ] install-from-zip test passes on a clean Blender profile

### 6. Documentation is minimally complete

- [ ] README describes the tool's actual supported scope, not aspirational scope
- [ ] installation instructions are correct
- [ ] one basic LMT workflow is documented
- [ ] one TIML-in-LMT workflow is documented
- [ ] known limitations are listed honestly
- [ ] release notes explain what is safe, what is blocked, and why

### 7. Public repository cleanup is complete

- [ ] public-facing docs do not market the project as a FreeHK patch/port
- [ ] code comments avoid unnecessary `FreeHK` / `freehk` naming where not historically required
- [ ] local-only legacy comparison helpers are removed from the public repo or moved behind clearly internal naming
- [ ] public module names, operator names, and docs reflect `mhw_anim_tools`
- [ ] license/readme text accurately describes the clean-room architecture and current dependencies

Current known public-cleanup references to revisit before release:

- `D:\Freehkwowo\mhw_anim_tools\core\formats\lmt\semantics.py`
- `D:\Freehkwowo\mhw_anim_tools\tools\compare_legacy_lmt.py`

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
