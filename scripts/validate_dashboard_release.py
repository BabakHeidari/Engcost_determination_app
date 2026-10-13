"""Run release checks in a disposable copy, never the operational checkout.

The copy includes source data for legacy regression fixtures. Its profile store
is deliberately initialized empty BEFORE pytest imports app.py. Tests prepare
their own operational fixtures. Evidence is retained under work/ by default.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LEGACY_BROWSER = ["tests/test_dashboard_frontend.py", "tests/test_dashboard_sensitivity_frontend.py"]
PRIMARY_BROWSER = ["tests/test_dashboard_visual_frontend.py", "tests/test_dashboard_release_frontend.py", "tests/test_product_creation_frontend.py"]


def inventory(roots):
    """Compare file bytes and file/directory mtimes, excluding access times."""
    result = {}
    for root in roots:
        if not root.exists():
            result[str(root)] = None
            continue
        for path in [root, *sorted(root.rglob("*"))]:
            stat = path.lstat()
            result[str(path)] = {"mtime_ns": stat.st_mtime_ns, "mode": stat.st_mode,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
                "link": os.readlink(path) if path.is_symlink() else None}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["backend", "browser", "compatibility", "all"], default="all")
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "work/pr10-evidence")
    parser.add_argument("--name", default="candidate")
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    run_root = ROOT / "work/pr10-runs"
    run_root.mkdir(parents=True, exist_ok=True)
    before = inventory([ROOT / "Data", ROOT / "instance"])
    with tempfile.TemporaryDirectory(prefix=args.name + "-", dir=run_root) as folder:
        checkout = Path(folder) / "checkout"
        checkout.mkdir()
        excluded = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "work")
        for name in ("app.py", "engcost_launcher.py", "standalone", "packaging", "AGENTS.md", "README.md", "modules", "utils", "templates",
                     "static", "tests", "docs", "scripts", "Data", "Data_Better_Structure"):
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, checkout / name, ignore=excluded)
            elif source.exists():
                shutil.copy2(source, checkout / name)
        # Only integrity-checked presentation bytes are copied from scratch.
        # Business JavaScript always comes from the shipped static/ directory.
        if (ROOT / "work/vendor").is_dir():
            shutil.copytree(ROOT / "work/vendor", checkout / "work/vendor")
        profile = Path(folder) / "profiles.json"
        env = os.environ.copy()
        env.update(APP_DATA_FILE=str(profile), APP_SECRET_KEY="pr10-isolated-fixture-only",
                   PYTHONPATH=str(checkout), PYTHONDONTWRITEBYTECODE="1", DASHBOARD_REQUIRE_BROWSER="1")
        subprocess.run([sys.executable, "-c", "from pathlib import Path; from utils.profile_store import ProfileDataStore; "
                        "import os; ProfileDataStore(Path(os.environ['APP_DATA_FILE'])).initialize({})"],
                       cwd=checkout, env=env, check=True)
        suites = ["backend", "browser", "compatibility"] if args.suite == "all" else [args.suite]
        results = {}
        overall = 0
        for suite in suites:
            report = evidence / f"{args.name}-{suite}.xml"
            command = [sys.executable, "-m", "pytest", "-q", "--tb=short", f"--junitxml={report}"]
            if suite == "backend":
                command += ["tests", *[f"--ignore={p}" for p in LEGACY_BROWSER + PRIMARY_BROWSER]]
            else:
                command += PRIMARY_BROWSER if suite == "browser" else LEGACY_BROWSER
            with (evidence / f"{args.name}-{suite}.txt").open("w", encoding="utf-8") as log:
                process = subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT)
            totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
            if report.exists():
                for child in ET.parse(report).getroot().iter("testsuite"):
                    for key in totals:
                        totals[key] += int(child.attrib.get(key, 0))
            results[suite] = {"command": command, "exit_code": process.returncode, "junit": str(report), **totals}
            print(json.dumps({suite: results[suite]}, ensure_ascii=False), flush=True)
            overall = max(overall, process.returncode)
            # A missing optional browser must not turn a release gate green.
            if suite in {"browser", "compatibility"} and (totals["skipped"] or not totals["tests"]):
                print("BLOCKER: required browser cases were skipped or not collected", file=sys.stderr)
                overall = max(overall, 1)
        after = inventory([ROOT / "Data", ROOT / "instance"])
        unchanged = before == after
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
        source_hashes = {}
        # Hash the exact disposable source that pytest executed, rather than a
        # working tree that may have changed while the isolated run was active.
        for source_root in [checkout / "app.py", *[checkout / p for p in ("modules", "utils", "static/js", "templates", "tests", "scripts")]]:
            paths = [source_root] if source_root.is_file() else sorted(source_root.rglob("*"))
            for path in paths:
                if path.is_file() and path.suffix in {".py", ".js", ".html"}:
                    source_hashes[str(path.relative_to(checkout))] = hashlib.sha256(path.read_bytes()).hexdigest()
        metadata = {"base_sha": "fc373ca92e97c91d3d3b4a1a181096cbdf733c37", "checkout_sha": revision,
                    "source_sha256": source_hashes, "python": sys.version,
                    "platform": platform.platform(), "suites": results, "operational_inventory_unchanged": unchanged,
                    "operational_entries": len(before), "dependencies": {
                        dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()}}
        (evidence / f"{args.name}-summary.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if not unchanged:
            print("BLOCKER: original operational inventory changed", file=sys.stderr)
            overall = max(overall, 1)
        return overall


if __name__ == "__main__":
    raise SystemExit(main())
