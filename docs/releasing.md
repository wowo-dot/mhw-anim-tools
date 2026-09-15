# Publishing and verifying a release

The installed updater reads
`https://api.github.com/repos/wowo-dot/mhw-anim-tools/releases/latest` and uses
that release's tag archive. Pushing a branch does not change this feed. Publish
a normal release and mark it Latest after its target commit passes Python CI
and the package checks. Keep the tag fixed once published.

Update `bl_info`, the README, installation/quickstart pages and release notes
together. Public release notes are a concise changelog of additions, changes
and fixes. Keep benchmarks, validation reports, dependencies and limitations
in the relevant technical documentation.

`tools/build_release.py --output NEW_DIRECTORY` builds committed HEAD; it
rejects uncommitted changes to packaged tracked files. Use `--ref v1.1.0` to
reproduce that release from a later checkout. It uses canonical Git bytes with
LF line endings, independent of the host's `core.autocrlf` setting. The ZIP has
the valid `mhw_anim_tools` module root, runtime JSON catalogs, docs, integration
examples and a file-hash manifest. Game assets and local research outputs are
excluded.

Validate the ZIP using Blender 4.5.10:

```powershell
blender --background --factory-startup --python-exit-code 1 --python tools/test_release_blender.py -- PACKAGE.zip NEW_TEST_DIRECTORY
```

`tools/test_updater_blender.py` exercises the actual released updater in a new
isolated directory. It never uses the installed add-on folder. Supply the
previous release ZIP, the new manifest, and a fresh output directory:

```powershell
blender --background --factory-startup --python-exit-code 1 --python tools/test_updater_blender.py -- --baseline-zip OLD_PACKAGE.zip --manifest build_manifest.json --output NEW_UPDATER_TEST_DIRECTORY
```

Before publication, add `--archive LOCAL_TAG_ARCHIVE.zip` for a rehearsal. Build
that archive with `git -c core.autocrlf=false -c core.eol=lf archive`. After
publication, omit `--archive` to verify the public feed, download, backup,
installation, every packaged file, reload and registration of the new helper
operator. Confirm the new version reports no further update.

Upload only the install ZIP as a release asset. Keep `SHA256SUMS.txt`,
`build_manifest.json` and the verification receipt with the local build records.
Download the public asset and compare its SHA256 with the tested ZIP.

## v1.1.0 publication evidence

The source tag points to `31106bbc3df1310fab268a34acc12db411415fb7`.
The published package SHA256 is
`06ac5e683504820334332889ff775ea33dfb0b08459e9f808555cc439af90acd`.
An initial package used CRLF for `LICENSE`; publication checks caught it and
the asset/manifest were corrected to canonical LF. All runtime files were
unchanged. The tag was not moved.

The live v1.0.2-to-v1.1.0 update passes all 122 package file hashes, backup,
reload, registration and subsequent update-status checks. The local receipt
is `corpus_scans/releases/v1.1.0/release_verification.json`.
