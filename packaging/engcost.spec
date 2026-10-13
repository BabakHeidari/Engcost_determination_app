# Build definitions must never import the operational Flask application.
import hashlib
import json
from pathlib import Path
import sys

root = Path(SPECPATH).parent
manifest = json.loads((root / 'packaging/resources.json').read_text())
datas = []
for item in manifest:
    source = root / item['path']
    if hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
        raise RuntimeError('Unreviewed resource: ' + item['path'])
    datas.append((str(source), str(Path(item['path']).parent)))
datas += [(str(root / 'work/pr11-build/build-info.json'), '.'),
          (str(root / 'work/pr11-build/licenses'), 'licenses')]
a = Analysis([str(root / 'engcost_launcher.py')], pathex=[str(root)],
             binaries=[], datas=datas, hiddenimports=['app', 'waitress', 'msvcrt' if sys.platform == 'win32' else 'fcntl'],
             hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'matplotlib', 'scipy', 'IPython', 'pytest', 'playwright', 'notebook'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Engcost',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=sys.platform != 'win32',
          icon=str(root / 'packaging/icons/engcost.ico') if sys.platform == 'win32' else None,
          version=str(root / 'packaging/windows/version.txt') if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Engcost')
