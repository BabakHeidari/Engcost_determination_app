"""Native CI only: reinstall a running package and uninstall without data loss."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smoke_installed import Native, fixture, snapshot


def durable(root):
    return {key:value for key,value in snapshot(root).items() if key.startswith(('Data/', 'instance/'))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--installer',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    executable=args.executable.resolve();installer=args.installer.resolve();output=args.output.resolve()
    # Fresh hosted CI profile only. Never replace an existing user's selection.
    from standalone.workspace import user_locations
    config,_=user_locations()
    if (config/'selection.json').exists():
        raise RuntimeError('Lifecycle validation requires a fresh disposable OS user')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='engcost-lifecycle-') as folder:
        root=Path(folder);workspace=root/'workspace';fixture(workspace)
        config.mkdir(parents=True,exist_ok=True)
        (config/'selection.json').write_text(json.dumps({'schema':1,'workspace':str(workspace)}))
        native=Native(executable,config,root,dict(os.environ))
        before=durable(workspace)
        native.launch();native.wait_business()
        baseline=durable(workspace)
        if os.name=='nt':
            command=[str(installer),'/S','/D='+str(executable.parent)]
        else:
            command=['sudo','dpkg','-i',str(installer)]
        try:
            # Replace a running installed package through its actual installer.
            subprocess.run(command,check=True,timeout=120)
            native.process.wait(timeout=60);assert native.process.returncode==0
            assert durable(workspace)==baseline
            native.launch();native.wait_business();native.login();native.stop()
            baseline=durable(workspace)
            subprocess.run(command,check=True,timeout=120)  # compatible-package reinstall
            assert durable(workspace)==baseline
            native.launch();native.wait_business()
            if os.name=='nt':
                subprocess.run([str(executable.parent/'Uninstall.exe'),'/S'],check=True,timeout=120)
                # NSIS copies itself to TEMP; wait for the owned executable to disappear.
                import time
                deadline=time.monotonic()+60
                while executable.exists() and time.monotonic()<deadline:time.sleep(.1)
                assert not executable.exists()
            else:
                subprocess.run(['sudo','dpkg','-r','engcost'],check=True,timeout=120)
            native.process.wait(timeout=60);assert native.process.returncode==0
            assert durable(workspace)==baseline
            result={'running_reinstall':'passed','compatible_reinstall':'passed','uninstall_retains_data':'passed',
                    'independent_prior_version_rollback':'pending: first packaging version; same-package reinstall tested',
                    'original_business_bytes_retained':all(durable(workspace).get(k)==v for k,v in before.items() if k.startswith('Data/'))}
            (output/'installer-lifecycle.json').write_text(json.dumps(result,indent=2)+'\n')
        finally:
            if native.process and native.process.poll() is None:
                native.process.terminate();native.process.wait(timeout=60)
            for name in ('selection.json','instance.json'):(config/name).unlink(missing_ok=True)


if __name__=='__main__':main()
