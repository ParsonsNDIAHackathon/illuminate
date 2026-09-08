#!/usr/bin/env python3
"""Repeatable, dependency-free latency smoke test for the deterministic demo graph."""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(base_url: str, method: str, path: str, body: dict | None, timeout_s: float) -> tuple[float, int, bytes]:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path, data=payload, method=method,
        headers={"Content-Type": "application/json", "X-Illuminate-User": "performance-harness"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            content = response.read()
            return (time.perf_counter() - started) * 1000, response.status, content
    except urllib.error.HTTPError as exc:
        detail = exc.read(800).decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {method} {path}: {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"timed out after {timeout_s:.1f}s for {method} {path}") from exc


def replace(value, root_id: str):
    if isinstance(value, str):
        return value.replace("{root_id}", root_id)
    if isinstance(value, dict):
        return {k: replace(v, root_id) for k, v in value.items()}
    if isinstance(value, list):
        return [replace(v, root_id) for v in value]
    return value


def assert_expected(content: bytes, expected: dict) -> None:
    value = json.loads(content)
    for part in expected["field"].split("."):
        if not isinstance(value, dict) or part not in value:
            raise RuntimeError(f"response is missing expected field {expected['field']}")
        value = value[part]
    if "equals" in expected and value != expected["equals"]:
        raise RuntimeError(f"{expected['field']} was {value!r}, expected {expected['equals']!r}")
    if "min_items" in expected and (not isinstance(value, list) or len(value) < expected["min_items"]):
        count = len(value) if isinstance(value, list) else "not a list"
        raise RuntimeError(f"{expected['field']} had {count} items, expected at least {expected['min_items']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure deterministic judged-path latency against a local Illuminate stack.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--environment", choices=("replit", "docker", "local"), default="local")
    parser.add_argument("--samples", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--start-command", help="Optional shell command to start the stack; its time to readiness is recorded.")
    parser.add_argument("--reset-fixture", action="store_true",
                        help="DESTRUCTIVE: reset the local graph from committed offline fixtures before measuring.")
    args = parser.parse_args()
    config = json.loads((ROOT / "config/mission-performance-budgets.json").read_text())
    samples = args.samples or config["timing_policy"]["samples"]
    timeout_s = config["timing_policy"]["request_timeout_ms"] / 1000
    startup_timeout_s = config["timing_policy"]["startup_timeout_ms"] / 1000

    process = None
    ready_started = time.perf_counter()
    if args.start_command:
        process = subprocess.Popen(args.start_command, cwd=ROOT, shell=True, start_new_session=True)
    last_error = ""
    try:
        while (time.perf_counter() - ready_started) < startup_timeout_s:
            try:
                _, status, content = request(args.base_url, "GET", "/api/health", None, 1)
                health = json.loads(content)
                if status == 200 and health.get("ok"):
                    break
                last_error = f"health response was not ready: {health}"
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.2)
        else:
            print(f"FAIL readiness: API not ready after {startup_timeout_s:.1f}s; last error: {last_error}", file=sys.stderr)
            return 2
        startup_ready_ms = round((time.perf_counter() - ready_started) * 1000, 2)

        if args.reset_fixture:
            fixture_command = config["fixture"]["command"]
            print(f"Resetting deterministic fixture: {fixture_command}")
            completed = subprocess.run(fixture_command, cwd=ROOT, shell=True, timeout=300)
            if completed.returncode:
                print(f"FAIL fixture reset: command exited {completed.returncode}", file=sys.stderr)
                return 2

        try:
            workspace_req = urllib.request.Request(args.base_url.rstrip("/") + "/api/workspace")
            with urllib.request.urlopen(workspace_req, timeout=timeout_s) as response:
                workspace = json.load(response)
            root_id = workspace.get("root_id")
            expected_fixture = config["fixture"]
            if root_id != expected_fixture["root_id"] or workspace.get("root_label") != expected_fixture["root_label"]:
                raise RuntimeError(
                    f"expected deterministic fixture {expected_fixture['root_label']} ({expected_fixture['root_id']}), "
                    f"got {workspace.get('root_label')} ({root_id}); pass --reset-fixture"
                )
        except Exception as exc:
            print(f"FAIL fixture discovery: {exc}", file=sys.stderr)
            return 2

        results, failed = [], False
        for spec in config["operations"]:
            path, body = replace(spec["path"], root_id), replace(spec.get("body"), root_id)
            expected = replace(spec["expect"], root_id)
            timings, sizes = [], []
            try:
                for _ in range(samples):
                    elapsed, status, content = request(args.base_url, spec["method"], path, body, timeout_s)
                    if status != 200:
                        raise RuntimeError(f"unexpected status {status}")
                    assert_expected(content, expected)
                    timings.append(round(elapsed, 2))
                    sizes.append(len(content))
                maximum = max(timings)
                passed = maximum <= spec["target_ms"]
                failed |= not passed
                row = {**spec, "path": path, "samples_ms": timings, "median_ms": round(statistics.median(timings), 2),
                       "max_ms": maximum, "payload_bytes_max": max(sizes), "passed": passed}
                results.append(row)
                marker = "PASS" if passed else "SLOW"
                print(f"{marker} {spec['name']}: median={row['median_ms']:.2f}ms max={maximum:.2f}ms "
                      f"payload={row['payload_bytes_max']}B target={spec['target_ms']}ms")
                if not passed:
                    print(f"  Diagnose {spec['method']} {path}; inspect query plan, result cardinality, and payload size.", file=sys.stderr)
            except Exception as exc:
                failed = True
                results.append({**spec, "path": path, "passed": False, "error": str(exc)})
                print(f"FAIL {spec['name']}: {exc}; operation={spec['method']} {path}", file=sys.stderr)

        report = {"environment": args.environment, "fixture": config["fixture"], "root_id": root_id,
                  "startup_ready_ms": startup_ready_ms if args.start_command else None,
                  "ready_probe_ms": startup_ready_ms, "fixture_reset": args.reset_fixture, "results": results}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        return 1 if failed else 0
    finally:
        if process is not None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)


if __name__ == "__main__":
    raise SystemExit(main())