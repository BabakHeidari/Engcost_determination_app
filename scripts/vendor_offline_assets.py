"""Restore reviewed production assets using pinned archive/member hashes.

Build-machine tool only. Never executed by the launcher or customer packages.
"""
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = json.loads((ROOT / "packaging/vendor-manifest.json").read_text())
    archives = {}
    for item in records:
        target = ROOT / item["path"]
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]:
            continue
        url = item.get("source", "")
        if not url.startswith("https://registry.npmjs.org/"):
            raise RuntimeError("Repository-owned resource differs: " + item["path"])
        if url not in archives:
            with urlopen(url, timeout=60) as response:
                raw = response.read()
            if hashlib.sha256(raw).hexdigest() != item["archive_sha256"]:
                raise RuntimeError("Archive integrity mismatch")
            archives[url] = raw
        with tarfile.open(fileobj=io.BytesIO(archives[url]), mode="r:gz") as archive:
            content = archive.extractfile(item["member"]).read()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError("Asset integrity mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


if __name__ == "__main__":
    main()
