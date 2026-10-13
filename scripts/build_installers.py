"""Build a platform-native frozen bundle and installer from an explicit allowlist."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/pr11-artifacts')
    parser.add_argument('--max-glibc', help='Fail a Linux target-baseline build requiring a newer GLIBC')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or platform.machine().lower() not in {'x86_64', 'amd64'}:
        raise RuntimeError('Build with native Python 3.12 x64')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build = ROOT / 'work/pr11-build'
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    licenses = build / 'licenses'
    licenses.mkdir()
    versions = {}
    # Only the locked, isolated build environment supplies dependencies.
    for dist in distributions():
        name = dist.metadata['Name']
        versions[name] = dist.version
        dest = licenses / name
        dest.mkdir()
        (dest / 'METADATA').write_text(dist.read_text('METADATA') or '', encoding='utf-8')
        for entry in dist.files or []:
            if 'license' in str(entry).lower() or Path(str(entry)).name.upper().startswith(('COPYING', 'NOTICE')):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = dest.joinpath(*[part for part in Path(str(entry)).parts if part not in {'.', '..'}])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    candidates = [Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE',
                  Path(sys.base_prefix) / 'lib/python3.12/LICENSE.txt']
    python_license = next((p for p in candidates if p.is_file()), None)
    if python_license is None:
        raise RuntimeError('CPython license file is required in the build interpreter')
    shutil.copyfile(python_license, licenses / 'CPython-LICENSE.txt')
    if sys.platform == 'linux':
        for package in ('libstdc++6', 'libgcc-s1', 'zlib1g'):
            copyright_file = Path('/usr/share/doc') / package / 'copyright'
            if not copyright_file.is_file():
                raise RuntimeError('Bundled system-library copyright is required: ' + package)
            shutil.copyfile(copyright_file, licenses / (package + '-copyright'))
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    app_version = (ROOT / 'packaging/VERSION').read_text().strip()
    info = {'version': app_version, 'source_sha': sha, 'dirty': dirty,
            'python': sys.version, 'platform': platform.platform(), 'dependencies': versions,
            'signed': False, 'resources': json.loads((ROOT / 'packaging/resources.json').read_text()),
            'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for folder in ['standalone', 'utils', 'modules']
                              for p in sorted((ROOT / folder).rglob('*.py'))
                              if ' ' not in p.name}}
    info['source_hashes']['app.py'] = hashlib.sha256((ROOT / 'app.py').read_bytes()).hexdigest()
    info['source_hashes']['engcost_launcher.py'] = hashlib.sha256((ROOT / 'engcost_launcher.py').read_bytes()).hexdigest()
    (build / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--workpath', build / 'pyinstaller', '--distpath', output / 'bundle', ROOT / 'packaging/engcost.spec')
    bundle = output / 'bundle/Engcost'
    if sys.platform == 'win32':
        makensis = shutil.which('makensis') or str(Path(os.environ['ProgramFiles(x86)']) / 'NSIS/makensis.exe')
        run(makensis, f'/DBUNDLE={bundle}', f'/DOUTPUT={output / "Engcost-"}{app_version}-Setup.exe',
            ROOT / 'packaging/windows/engcost.nsi')
    elif sys.platform == 'linux':
        symbols = set()
        for path in bundle.rglob('*'):
            if not path.is_file():
                continue
            with path.open('rb') as stream:
                elf = stream.read(4) == b'\x7fELF'
            if elf:
                table = subprocess.check_output(['readelf', '--version-info', str(path)], text=True)
                symbols.update(re.findall(r'GLIBC_(\d+\.\d+)', table))
        parts = lambda value: tuple(map(int, value.split('.')))
        maximum = max(symbols, key=parts)
        if args.max_glibc and parts(maximum) > parts(args.max_glibc):
            raise RuntimeError('Bundle exceeds target GLIBC baseline: ' + maximum)
        required_glibc = max(['2.35', maximum], key=parts)
        info['abi'] = {'maximum_glibc_symbol': maximum, 'package_minimum_glibc': required_glibc,
                       'target_baseline_gate': args.max_glibc}
        (build / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
        shutil.copyfile(build / 'build-info.json', bundle / '_internal/build-info.json')
        stage = build / 'deb'
        appdir = stage / 'opt/engcost'
        shutil.copytree(bundle, appdir)
        control = stage / 'DEBIAN'
        control.mkdir()
        template = (ROOT / 'packaging/linux/control').read_text()
        (control / 'control').write_text(template.replace('@VERSION@', app_version).replace('@GLIBC@', required_glibc))
        for script in ('prerm', 'preinst', 'postinst', 'postrm'):
            shutil.copyfile(ROOT / 'packaging/linux' / script, control / script)
            (control / script).chmod(0o755)
        for source, target in [('packaging/linux/engcost.desktop', 'usr/share/applications/engcost.desktop'),
                               ('packaging/icons/engcost.png', 'usr/share/icons/hicolor/256x256/apps/engcost.png')]:
            path = stage / target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, path)
        # Immutable, system-owned package content. Only the launcher writes user data.
        for p in stage.rglob('*'):
            if p.is_dir():
                p.chmod(0o755)
            elif p.name not in {'Engcost', 'preinst', 'prerm', 'postinst', 'postrm'}:
                p.chmod(0o644)
        run('dpkg-deb', '--root-owner-group', '--build', stage, output / f'engcost_{app_version}_amd64.deb')
    else:
        raise RuntimeError('Only Windows/Linux native installers are supported')
    shutil.copyfile(build / 'build-info.json', output / 'build-info.json')
    checksums = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != 'SHA256SUMS':
            checksums.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
    (output / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')


if __name__ == '__main__':
    main()
