"""Install pinned Playwright and verified screenshot assets under project work/."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    ("https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css", "bootstrap.min.css", "3017df4a76db5f01c2b99b603d88b03106df13bcfe18e67b7c13c2341d3a67df"),
    ("https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js", "bootstrap.bundle.min.js", "82f64f62bb03c1bc1824b0f9c9e05f70dba33e146818e63cdf5c306c8cf3dedd"),
    ("https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/css/all.min.css", "fontawesome/all.min.css", "c22cfb6520a7fdbb738632834019acf47c78b1279462c0eb4cb83bae83ecb5a7"),
    ("https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-solid-900.woff2", "fontawesome/fa-solid-900.woff2", "9fc85f3a4544ab0d570c7f8f9bbb88db8d92c359b2707580ea8b07c75673eae2"),
    ("https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-regular-400.woff2", "fontawesome/fa-regular-400.woff2", "2bccecf0bc7e96cd5ce4003abeb3ae9ee4a3d19158c4e6edfd2df32d2f0d5721"),
    ("https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-brands-400.woff2", "fontawesome/fa-brands-400.woff2", "3a8924cd5203a28628716aedb5cef0943da4c3b44e3ffcee90ab06387b41c490"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium-path', type=Path, help='Validate this installed Chromium instead of downloading one')
    args = parser.parse_args()
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-browser.txt")],
                   env={**os.environ, 'PIP_CACHE_DIR': str(ROOT / 'work/pip-cache')}, check=True)
    for url, relative, digest in ASSETS:
        path = ROOT / "work" / "vendor" / relative
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        with urlopen(url, timeout=60) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError("Presentation asset integrity mismatch: " + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    cache = ROOT / "work" / "browser-cache"
    cache.mkdir(parents=True, exist_ok=True)
    if args.chromium_path:
        executable = args.chromium_path.resolve(strict=True)
        result = subprocess.run([str(executable), '--version'], text=True, capture_output=True, check=True)
        if not any(name in result.stdout for name in ('Chromium', 'Chrome')):
            raise RuntimeError('Selected executable is not Chromium/Chrome')
        print(result.stdout.strip())
        print('Test override: DASHBOARD_CHROMIUM_PATH=' + str(executable))
    else:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(cache)}, check=True)
    print("Browser and presentation asset cache: " + str(ROOT / "work"))


if __name__ == "__main__":
    main()
