"""Build a deterministic release ZIP from committed files without installing it."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    snapshot=subprocess.check_output(['git','archive','--format=zip',commit],cwd=root)
    with zipfile.ZipFile(io.BytesIO(snapshot)) as source_archive:
        source={name:source_archive.read(name) for name in source_archive.namelist() if not name.endswith('/')}
    tree=ast.parse(source['__init__.py'].decode('utf-8'))
    info=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='bl_info' for t in node.targets))
    version='.'.join(map(str,info['version']))
    files=[root/'__init__.py',root/'LICENSE',root/'README.md']
    for folder in ('core','blender_adapter','integration','ui'):
        files.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.json'))
    files.extend(p for p in (root/'docs').rglob('*') if p.is_file() and p.suffix in ('.md','.json','.png'))
    files.extend(root/'tools'/name for name in ('duplicate_pose_bake_integration.py','bake_throughput_integration.py'))
    names=sorted(p.relative_to(root).as_posix() for p in files)
    subprocess.run(['git','diff','--exit-code','HEAD','--',*names],cwd=root,check=True,stdout=subprocess.DEVNULL)
    # Git's canonical bytes match the updater's tag archive on every platform,
    # regardless of a Windows checkout's CRLF conversion.
    hashes={name:hashlib.sha256(source[name]).hexdigest() for name in names}
    manifest=dict(version=version,status='release package',
                  base_commit=commit,
                  files=hashes)
    manifest_bytes=json.dumps(manifest,indent=2).encode('utf-8')
    package=output/f'mhw_anim_tools-v{version}.zip'
    def add(archive,name,data):
        entry=zipfile.ZipInfo('mhw_anim_tools/'+name,date_time=(2026,9,15,0,0,0))
        entry.compress_type=zipfile.ZIP_DEFLATED
        entry.external_attr=0o100644<<16
        archive.writestr(entry,data)
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name in sorted(hashes):
            add(archive,name,source[name])
        add(archive,'BUILD_MANIFEST.json',manifest_bytes)
    digest=hashlib.sha256(package.read_bytes()).hexdigest()
    (output/'build_manifest.json').write_bytes(manifest_bytes)
    (output/'SHA256SUMS.txt').write_text(f'{digest}  {package.name}\n')
    print(json.dumps(dict(path=str(package),sha256=digest,bytes=package.stat().st_size,files=len(hashes)),indent=2))


if __name__=='__main__':
    main()
