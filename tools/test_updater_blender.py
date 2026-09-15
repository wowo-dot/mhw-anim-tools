"""Exercise a released updater in a fresh private folder, never the real install.

Run with Blender --background --factory-startup --python-exit-code 1 --python
this_file -- --baseline-zip OLD.zip --manifest build_manifest.json --output NEW.
Omit --archive to query and install from the public latest-release endpoint.
Use --archive TAG_ARCHIVE.zip for an offline release-feed rehearsal.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-zip', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    expected = json.loads(args.manifest.read_text(encoding='utf-8'))
    expected_version = tuple(int(part) for part in expected['version'].split('.'))
    tag = 'v' + expected['version']

    with zipfile.ZipFile(args.baseline_zip) as archive:
        for name in archive.namelist():
            assert name.startswith('mhw_anim_tools/') and '..' not in Path(name).parts
            assert (output / name).resolve().is_relative_to(output)
        archive.extractall(output)
    install_root = (output / 'mhw_anim_tools').resolve()
    assert install_root.is_relative_to(output)
    assert install_root != Path(__file__).resolve().parents[1]
    assert not (install_root / '.git').exists()
    sys.path.insert(0, str(output))
    old_addon = importlib.import_module('mhw_anim_tools')
    old_preferences = importlib.import_module('mhw_anim_tools.ui.addon_preferences')
    assert Path(old_addon.__file__).resolve() == install_root / '__init__.py'
    assert old_preferences.ADDON_ROOT.resolve() == install_root
    baseline_version = tuple(old_addon.bl_info['version'])
    assert baseline_version < expected_version
    updater = old_preferences.GitHubAddonUpdater()
    updater.configure(current_version=baseline_version)
    if args.archive:
        # Exercise the unchanged release parser and installer while substituting
        # only network I/O until the release has been published.
        archive_path = args.archive.resolve()
        updater._request_json = lambda _url: dict(
            tag_name=tag, name='MHW Anim Tools ' + tag,
            zipball_url=archive_path.as_uri(),
            html_url='https://github.com/wowo-dot/mhw-anim-tools/releases/tag/' + tag,
        )
        updater._download_zip = lambda _url, target: shutil.copy2(archive_path, target)

    release = updater.check_now()
    assert release.version_text == tag, release
    assert release.source_kind == 'release'
    assert updater.update_ready and not updater.error
    backup = Path(updater.install_update()).resolve()
    assert backup.is_relative_to(output)
    assert (backup / '__init__.py').read_bytes() == args_baseline_init(args.baseline_zip)
    assert updater.pending_reload and not updater.update_ready
    for name, digest in expected['files'].items():
        assert hashlib.sha256((install_root / name).read_bytes()).hexdigest() == digest, name
    for name in list(sys.modules):
        if name == 'mhw_anim_tools' or name.startswith('mhw_anim_tools.'):
            del sys.modules[name]
    importlib.invalidate_caches()
    new_addon = importlib.import_module('mhw_anim_tools')
    assert tuple(new_addon.bl_info['version']) == expected_version
    new_addon.register()
    try:
        assert hasattr(bpy.types.Scene, 'mhw_anim_tools')
        assert bpy.ops.mhw_anim_tools.build_pose_helper.get_rna_type()
        new_preferences = importlib.import_module('mhw_anim_tools.ui.addon_preferences')
        new_updater = new_preferences.GitHubAddonUpdater()
        new_updater.configure(current_version=expected_version)
        assert not new_updater.pending_reload
        # Recheck using the same feed, without downloading/installing again.
        if args.archive:
            new_updater._request_json = updater._request_json
        assert new_updater.check_now().version_text == tag
        assert not new_updater.update_ready
    finally:
        new_addon.unregister()
    report = dict(
        mode='archive rehearsal' if args.archive else 'public latest release',
        blender=bpy.app.version_string,
        baseline_version=baseline_version,
        release=release.version_text,
        download_url=release.download_url,
        verified_files=len(expected['files']),
        backup=str(backup),
        checks=['old updater detects release', 'backup matches old install',
                'install matches package manifest', 'pending reload and reimport',
                'new addon register/unregister', 'helper UI registered',
                'new version reports no further update'],
    )
    (output / 'updater_test.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


def args_baseline_init(package):
    with zipfile.ZipFile(package) as archive:
        return archive.read('mhw_anim_tools/__init__.py')


if __name__ == '__main__':
    main()
