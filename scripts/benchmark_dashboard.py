#!/usr/bin/env python3
"""Reproduce request timings and request-local work with isolated V2 inputs.

Example: python scripts/benchmark_dashboard.py --output work/pr10-evidence/backend.json
No operational application startup, credentials, writes, or cross-request source
caches are needed. Timings are observations, never pass/fail SLA assertions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import cProfile
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def percentile(values, proportion):
    """Nearest-rank percentile; no extrapolation from the measured sample."""
    return sorted(values)[max(0, math.ceil(len(values) * proportion) - 1)]


def inventory(root):
    return {str(path.relative_to(root)): (
        "file", hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    ) if path.is_file() else ("directory", path.stat().st_mtime_ns)
            for path in [root, *root.rglob("*")]}


def source_hashes(repository):
    files = [repository / "app.py", *(repository / "modules").rglob("*.py"),
             *(repository / "utils").rglob("*.py")]
    return {str(path.relative_to(repository)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def backend_revision_differences(repository, git_repository, revision):
    names = subprocess.check_output(["git", "-C", str(git_repository), "ls-tree", "-r", "--name-only", revision],
                                    text=True).splitlines()
    expected = {name for name in names if name == "app.py" or
                (name.startswith(("modules/", "utils/")) and name.endswith(".py"))}
    captured = source_hashes(repository)
    changed = set(captured).symmetric_difference(expected)
    for name in set(captured).intersection(expected):
        original = subprocess.check_output(["git", "-C", str(git_repository), "show", f"{revision}:{name}"])
        if hashlib.sha256(original).hexdigest() != captured[name]:
            changed.add(name)
    return sorted(changed)


def revision_metadata(repository, archive_revision):
    """Do not accidentally describe an archive using its parent Git checkout."""
    result = subprocess.run(["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
                            text=True, capture_output=True)
    own_checkout = result.returncode == 0 and Path(result.stdout.strip()).resolve() == repository
    if own_checkout:
        if archive_revision:
            raise ValueError("--archive-revision is only valid for a source archive")
        revision = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
        changed_backend = backend_revision_differences(repository, repository, revision)
        return {"source_kind": "git_checkout",
                "revision": revision,
                "tracked_changes": bool(subprocess.check_output(["git", "-C", str(repository), "diff", "--name-only"], text=True).strip()),
                "backend_sources_match_revision": not changed_backend,
                "changed_backend_sources": changed_backend}
    if not archive_revision:
        return {"source_kind": "source_archive", "revision": None, "tracked_changes": None}
    # The harness checkout supplies Git objects solely to verify provenance;
    # selected application imports still come exclusively from the archive.
    harness_repository = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "-C", str(harness_repository), "rev-parse",
                                        "--verify", archive_revision + "^{commit}"], text=True).strip()
    changed = backend_revision_differences(repository, harness_repository, revision)
    if changed:
        raise ValueError(f"Source archive differs from {revision}: {', '.join(changed)}")
    return {"source_kind": "verified_source_archive", "revision": revision,
            "tracked_changes": False, "archive_backend_sources_verified": True,
            "backend_sources_match_revision": True, "changed_backend_sources": []}


def build_cases(fixture, client):
    response = client.get("/api/dashboard/sensitivity/parameters", query_string=fixture.selection)
    if response.status_code != 200:
        raise RuntimeError(f"Fixture registry failed: {response.status_code}")
    parameters = response.get_json()["parameters"]
    materials = [p for p in parameters if p["parameter_id"].startswith("material:")]
    pools = [p for p in parameters if p["parameter_id"].startswith("pool:")]
    share = next(p for p in parameters if p["parameter_id"].startswith("category_share:"))
    prediction = next(p for p in parameters if p["parameter_id"].startswith("prediction:"))
    material = materials[0]["parameter_id"]
    scenarios = [{"id": "A", "overrides": [{"parameter_id": material, "mode": "percent_change", "value": "10"}]},
                 {"id": "B", "overrides": [{"parameter_id": "pool:Payroll", "mode": "percent_change", "value": "20"}]}]
    base = {**fixture.selection, "scenarios": scenarios}
    all_selection = {**fixture.selection, "category": "__ALL__", "subcategory": "__ALL__", "product": "__ALL__"}
    tornado = [*pools, share, prediction, *materials[:2]]
    return [
        ("all_selected_cost_analysis", "GET", "/api/cost_analysis", all_selection, fixture.dimensions["configuration_population"], 0),
        ("all_selected_cost_visuals", "GET", "/api/dashboard/cost-analysis/visuals", all_selection, fixture.dimensions["configuration_population"], 0),
        ("baseline_a_b", "POST", "/api/dashboard/sensitivity/visual-analysis", {**base, "experiment": None}, 3, 0),
        ("one_factor_41", "POST", "/api/dashboard/sensitivity/visual-analysis", {**base, "experiment": {
            "type": "one_factor", "axes": [{"parameter_id": material, "mode": "absolute", "values": [str(i * 5) for i in range(41)]}]}}, 44, 41),
        ("tornado_10", "POST", "/api/dashboard/sensitivity/visual-analysis", {**base, "experiment": {
            "type": "tornado", "ranges": [{"parameter_id": p["parameter_id"], "mode": "percent_change", "low": "-10", "high": "10"} for p in tornado]}}, 23, 20),
        ("two_factor_11x11", "POST", "/api/dashboard/sensitivity/visual-analysis", {**base, "experiment": {
            "type": "two_factor", "axes": [
                {"parameter_id": material, "mode": "absolute", "values": [str(i * 20) for i in range(11)]},
                {"parameter_id": "pool:Payroll", "mode": "absolute", "values": [str(i * 400) for i in range(11)]}]}}, 124, 121),
    ]


class RequestMeasurement:
    def __init__(self, fixture):
        self.fixture = fixture
        self.source_reads = Counter()
        self.source_byte_reads = 0
        self.profile_reads = Counter()
        self.source_read_attempts = Counter()
        self.engines = 0
        self.baselines = 0
        self.input_objects = set()
        self.loader_objects = set()

    def __enter__(self):
        import utils.costing_engine as engine
        import utils.dashboard_analysis as analysis
        import utils.dashboard_sensitivity as sensitivity
        import utils.dashboard_visual_sensitivity as visual

        self.stack = ExitStack()
        real_read = Path.read_bytes
        real_text = Path.read_text
        real_open = Path.open
        real_source = engine.CostInputLoader._read
        real_calculate = engine.calculate_cost

        def read(path):
            if self.fixture.data in path.parents or path == self.fixture.bindings:
                self.source_reads[path] += 1
                self.source_byte_reads += 1
            return real_read(path)

        def read_text(path, *args, **kwargs):
            if self.fixture.data in path.parents or path == self.fixture.bindings:
                self.source_reads[path] += 1
            return real_text(path, *args, **kwargs)

        def open_file(path, mode="r", *args, **kwargs):
            if path == self.fixture.profiles and mode.startswith("r"):
                self.profile_reads["profiles.json"] += 1
            return real_open(path, mode, *args, **kwargs)

        def source(loader, path):
            self.loader_objects.add(id(loader))
            self.source_read_attempts[path] += 1
            return real_source(loader, path)

        def calculate(inputs, overrides=None):
            self.engines += 1
            self.baselines += overrides is None
            self.input_objects.add(id(inputs))
            return real_calculate(inputs, overrides)

        self.stack.enter_context(patch.object(Path, "read_bytes", read))
        self.stack.enter_context(patch.object(Path, "read_text", read_text))
        self.stack.enter_context(patch.object(Path, "open", open_file))
        self.stack.enter_context(patch.object(engine.CostInputLoader, "_read", source))
        for module in (analysis, sensitivity, visual):
            self.stack.enter_context(patch.object(module, "calculate_cost", calculate))
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)

    def counters(self):
        return {"engine_calls": self.engines, "baseline_engine_calls": self.baselines,
                "captured_input_objects": len(self.input_objects), "request_loader_objects": len(self.loader_objects),
                "source_read_calls": sum(self.source_reads.values()), "unique_source_reads": len(self.source_reads),
                "repeated_source_reads": sum(count - 1 for count in self.source_reads.values()),
                "loader_read_attempts": sum(self.source_read_attempts.values()),
                "request_local_source_reuses": sum(self.source_read_attempts.values()) - self.source_byte_reads,
                "profile_file_reads": sum(self.profile_reads.values()),
                "unique_profile_file_reads": len(self.profile_reads),
                "repeated_profile_file_reads": sum(count - 1 for count in self.profile_reads.values())}


def request(fixture, client, case):
    name, method, endpoint, payload, engine_calls, points = case
    with RequestMeasurement(fixture) as measured:
        started = time.perf_counter_ns()
        response = client.get(endpoint, query_string=payload) if method == "GET" else client.post(endpoint, json=payload)
        raw = response.get_data()
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
    body = response.get_json()
    if response.status_code != 200 or body.get("state", body.get("analysis", {}).get("state")) != "OK":
        raise RuntimeError(f"{name} failed: HTTP {response.status_code}")
    counters = measured.counters()
    if counters["engine_calls"] != engine_calls or counters["repeated_source_reads"] or counters["request_loader_objects"] != 1:
        raise RuntimeError(f"{name} work invariant failed: {counters}")
    if method == "POST":
        if counters["captured_input_objects"] != 1 or counters["baseline_engine_calls"] != 1:
            raise RuntimeError(f"{name} did not share one input capture")
        if body["evaluation_budget"]["executed"] != engine_calls:
            raise RuntimeError(f"{name} execution budget differs from observed engine calls")
        experiment = body["experiment"]
        if points and (len(experiment["points"]) != points or experiment["invalid_count"]):
            raise RuntimeError(f"{name} fixture must have {points} valid points")
    else:
        report = body.get("analysis", body)
        if report["coverage"]["calculated"] != fixture.dimensions["configuration_population"]:
            raise RuntimeError(f"{name} excluded synthetic configurations")
    return {"latency_ms": round(elapsed, 6), "response_bytes": len(raw), **counters}


def summarize(samples):
    times = [sample["latency_ms"] for sample in samples]
    return {"sample_count": len(samples), "p50_ms": round(percentile(times, .50), 3),
            "p95_ms": round(percentile(times, .95), 3), "min_ms": round(min(times), 3),
            "max_ms": round(max(times), 3), "mean_ms": round(statistics.mean(times), 3),
            **{key: {"min": min(sample[key] for sample in samples), "max": max(sample[key] for sample in samples)}
               for key in samples[0] if key != "latency_ms"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive-revision", help="Verify an application source archive against this Git revision")
    parser.add_argument("--first-samples", type=int, default=30)
    parser.add_argument("--warm-samples", type=int, default=30)
    parser.add_argument("--profile", action="store_true")
    arguments = parser.parse_args()
    if min(arguments.first_samples, arguments.warm_samples) < 1:
        parser.error("sample counts must be positive")
    repository = arguments.repository.resolve()
    sys.path.insert(0, str(repository))
    from dashboard_benchmark_fixture import install_fixture, create_app
    from decimal import getcontext

    metadata = {"python": platform.python_version(), "python_implementation": platform.python_implementation(),
                "platform": platform.platform(), "machine": platform.machine(),
                "logical_cpu_count": os.cpu_count(),
                "decimal_context": str(getcontext()),
                "packages": {name: version(name) for name in ("Flask", "Werkzeug", "pandas", "openpyxl")},
                **revision_metadata(repository, arguments.archive_revision),
                "clock": "time.perf_counter_ns", "percentiles": "nearest_rank",
                "timed_scope": "isolated Flask test-client request through response serialization; instrumentation included",
                "first_request_definition": "first request to a fresh Flask app and authenticated client; Python imports and fixture installation excluded; OS page cache not flushed",
                "warmed_request_definition": "requests 2 onward to one Flask app/client; every request still reads fresh operational inputs using a new loader",
                "transport": "in-process Flask test client; no network or browser rendering"}
    metadata["source_sha256"] = source_hashes(repository)
    metadata["harness_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in (Path(__file__), Path(__file__).with_name("dashboard_benchmark_fixture.py"))}
    evidence = {"schema_version": 1, "environment": metadata, "cases": {}}
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dashboard-benchmark-") as temporary:
        fixture = install_fixture(Path(temporary))
        before = inventory(fixture.root)
        _, registry_client = create_app(fixture)
        cases = build_cases(fixture, registry_client)
        evidence["fixture"] = fixture.dimensions
        for case in cases:
            name = case[0]
            first = []
            for _ in range(arguments.first_samples):
                _, client = create_app(fixture)
                first.append(request(fixture, client, case))
            _, client = create_app(fixture)
            request(fixture, client, case)  # explicitly excluded warm-up
            warm = [request(fixture, client, case) for _ in range(arguments.warm_samples)]
            evidence["cases"][name] = {"method": case[1], "endpoint": case[2], "points": case[5],
                                       "first_request": {"summary": summarize(first), "samples": first},
                                       "warmed_request": {"summary": summarize(warm), "samples": warm}}
            print(f"{name}: first p50/p95={summarize(first)['p50_ms']}/{summarize(first)['p95_ms']} ms; "
                  f"warm p50/p95={summarize(warm)['p50_ms']}/{summarize(warm)['p95_ms']} ms", flush=True)
            if arguments.profile:
                profiler = cProfile.Profile()
                profiler.enable()
                request(fixture, client, case)
                profiler.disable()
                statistics_ = pstats.Stats(profiler)
                top = sorted(statistics_.stats.items(), key=lambda item: item[1][3], reverse=True)[:25]
                evidence["cases"][name]["profile_top_cumulative"] = [
                    {"function": f"{Path(key[0]).name}:{key[1]}:{key[2]}", "primitive_calls": value[0],
                     "calls": value[1], "self_seconds": round(value[2], 6), "cumulative_seconds": round(value[3], 6)}
                    for key, value in top]
            if inventory(fixture.root) != before:
                raise RuntimeError(f"{name} wrote isolated operational/profile inputs")
        evidence["fixture_unchanged"] = inventory(fixture.root) == before
        if not evidence["fixture_unchanged"]:
            raise RuntimeError("A benchmark request wrote isolated operational/profile inputs")
    if source_hashes(repository) != metadata["source_sha256"]:
        raise RuntimeError("Benchmarked source files changed during the run; repeat with stable sources")
    arguments.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
