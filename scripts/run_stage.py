#!/usr/bin/env python3
"""File-based stage logs, a reliable exit sidecar and periodic deadline evidence.

The PowerShell caller must redirect this wrapper's own stdout/stderr to files
too. Read --exit-code-file after the wrapper exits; do not use Process.ExitCode
or Process.Kill(bool) under PowerShell 5.1. Timeout kills the entire child tree.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from pipeline_state import atomic_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="stage label for log tagging")
    ap.add_argument("--out", required=True, help="stdout log file path")
    ap.add_argument("--err", required=True, help="stderr log file path")
    ap.add_argument("--exit-code-file", required=True, help="sidecar file to write exit code (PowerShell can't read .ExitCode when stdout is redirected)")
    ap.add_argument("--timeout", type=int, default=1800, help="timeout in seconds")
    ap.add_argument("--workdir", default=None, help="working directory")
    ap.add_argument("script", help="python script to run")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="args for the script")
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.err).parent.mkdir(parents=True, exist_ok=True)
    Path(args.exit_code_file).parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, args.script] + args.args
    workdir = args.workdir or os.getcwd()
    heartbeat_path = Path(args.exit_code_file).with_suffix(".heartbeat.json")
    started = time.time()
    heartbeat = {"label": args.label, "wrapper_pid": os.getpid(), "started_epoch": started,
                 "timeout_sec": args.timeout, "state": "running"}

    def beat(state):
        heartbeat.update(state=state, updated_epoch=time.time())
        atomic_json(heartbeat_path, heartbeat)

    print(f"[wrapper:{args.label}] start timeout={args.timeout}s workdir={workdir}", file=sys.stderr)
    print(f"[wrapper:{args.label}] cmd={cmd}", file=sys.stderr)

    try:
        with open(args.out, "wb") as fout, open(args.err, "wb") as ferr:
            proc = subprocess.Popen(
                cmd,
                stdout=fout,
                stderr=ferr,
                cwd=workdir,
                env=os.environ.copy(),
            )
            heartbeat["child_pid"] = proc.pid
            beat("running")
            try:
                deadline = time.monotonic() + args.timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(cmd, args.timeout)
                    try:
                        rc = proc.wait(timeout=min(15, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise
                        beat("running")
            except subprocess.TimeoutExpired:
                print(f"[wrapper:{args.label}] TIMEOUT after {args.timeout}s — killing process tree", file=sys.stderr)
                _kill_tree(proc)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                rc = -1  # signal timeout
    except Exception as e:
        print(f"[wrapper:{args.label}] FATAL: {e}", file=sys.stderr)
        # Still write a sidecar file so PowerShell can read something
        try:
            Path(args.exit_code_file).write_text("99", encoding="utf-8")
        except Exception:
            pass
        sys.exit(99)

    # Write sidecar file BEFORE exiting. PowerShell reads this file to get the actual exit code.
    try:
        heartbeat["exit_code"] = rc
        beat("finished")
        Path(args.exit_code_file).write_text(str(rc), encoding="utf-8")
    except Exception as e:
        print(f"[wrapper:{args.label}] WARN: cannot write exit_code_file: {e}", file=sys.stderr)

    print(f"[wrapper:{args.label}] done exit_code={rc} (also written to {args.exit_code_file})", file=sys.stderr)
    sys.exit(rc)


def _kill_tree(proc):
    """Kill process tree on Windows using taskkill."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
