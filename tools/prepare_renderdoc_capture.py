"""Prepare/launch the existing RenderDoc through the current MO2 virtual filesystem.

Default is read-only verification. --launch starts MHW only if it is closed.
No profile selections, installed assets, graphics settings, or global hooks change.
Outputs are restricted to this checkout's ignored corpus_scans directory.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r'D:\SteamLibrary\steamapps\common\Monster Hunter World')
MO2 = Path(r'C:\Modding\MO2\ModOrganizer.exe')
MODLIST = Path(r'D:\MO2\MHW\profiles\Default\modlist.txt')
CONFIG = MO2.parent / 'ModOrganizer.ini'
EXTRACT = Path(r'D:\mh world modding\whole game extract\chunk')
RD = Path(r'D:\mh world modding\base body\Panam_MHW_Base_v10\tools\renderdoc\RenderDoc_1.46_64\renderdoccmd.exe')
TARGET_FILES = (
    'event/evc0034/pl000_00/pl000_00.lmt',
    'event/evc0034/evc0034.sdl',
    'event/evc0034/evc0034_camera.sdl',
)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def game_pids():
    result = subprocess.check_output(
        ['tasklist.exe', '/FI', 'IMAGENAME eq MonsterHunterWorld.exe', '/FO', 'CSV', '/NH'],
        creationflags=subprocess.CREATE_NO_WINDOW, text=True)
    return [int(row[1]) for row in csv.reader(result.splitlines())
            if len(row) > 1 and row[0].lower() == 'monsterhunterworld.exe']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--inside-mo2', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(PROJECT / 'corpus_scans'):
        parser.error('Output must be inside this checkout/corpus_scans.')
    out.mkdir(parents=True, exist_ok=True)
    if not args.inside_mo2:
        child_args = [str(Path(__file__).resolve()), '--inside-mo2', '--output', str(out)]
        if args.launch:
            child_args.append('--launch')
        command = [str(MO2), 'run', '-c', str(GAME), '-a',
                   subprocess.list2cmdline(child_args), sys.executable]
        mode = 'launch' if args.launch else 'verify'
        with (out / f'mo2_{mode}.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen(command, cwd=str(MO2.parent), stdout=log,
                                     stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        print(json.dumps({'mo2_request_pid': child.pid, 'mode': mode, 'output': str(out)}))
        return

    report = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'mode': 'launch' if args.launch else 'verify', 'files': []}
    destination = out / ('launch.json' if args.launch else 'verification.json')

    def save():
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        report['usvfs_loaded'] = bool(kernel.GetModuleHandleW('usvfs_x64.dll'))
        if not report['usvfs_loaded']:
            raise RuntimeError('MO2 virtual filesystem is not loaded.')
        before = {str(p): sha(p) for p in (CONFIG, MODLIST)}
        if 'selected_profile=@ByteArray(Default)' not in CONFIG.read_text(encoding='utf-8-sig'):
            raise RuntimeError('The prepared Default profile is no longer selected.')
        report['configuration_hashes'] = before
        report['enabled_mods'] = [line[1:] for line in MODLIST.read_text(encoding='utf-8-sig').splitlines()
                                  if line.startswith('+')]
        for relative in TARGET_FILES:
            native = EXTRACT / relative
            virtual = GAME / 'nativePC' / relative
            expected = sha(native)
            actual = sha(virtual) if virtual.is_file() else None
            row = dict(path=relative, native_sha256=expected, virtual_loose_sha256=actual,
                       state=('no_loose_override' if actual is None else
                              'original_loose_copy' if actual == expected else 'changed_loose_override'))
            report['files'].append(row)
            if actual is not None and actual != expected:
                raise RuntimeError(f'Target scene has a changed animation/context override: {relative}')
        report['asset_check_limit'] = (
            'Checks MO2 loose overrides against the native extract. Packed game archives and '
            'runtime plugin effects are not qualified by this preparation step.')
        report['renderdoccmd'] = str(RD)
        report['renderdoccmd_sha256'] = sha(RD)
        report['game_sha256'] = sha(GAME / 'MonsterHunterWorld.exe')
        report['game_pids_before'] = game_pids()
        report['configuration_unchanged'] = before == {str(p): sha(p) for p in (CONFIG, MODLIST)}
        if not report['configuration_unchanged']:
            raise RuntimeError('MO2 configuration changed during preparation.')
        report['status'] = 'verified'
        save()
        if args.launch:
            if report['game_pids_before']:
                raise RuntimeError('MHW is already running; close it normally before capture launch.')
            captures = out / 'captures'
            captures.mkdir(exist_ok=True)
            stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            template = captures / f'evc0034_{stamp}'
            command = [str(RD), 'capture', '-d', str(GAME), '-c', str(template),
                       str(GAME / 'MonsterHunterWorld.exe')]
            report['capture_command'] = command
            report['capture_template'] = str(template)
            with (out / f'launch_{stamp}.log').open('w', encoding='utf-8') as log:
                child = subprocess.Popen(command, cwd=str(GAME), stdout=log,
                                         stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            report['launcher_pid'] = child.pid
            report['status'] = 'capture_launch_requested'
            save()
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        save()
        raise


if __name__ == '__main__':
    main()
