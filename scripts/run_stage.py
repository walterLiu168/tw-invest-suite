#!/usr/bin/env python3
"""D056 P1+ fix: Reliable stage executor for PowerShell.

PowerShell's Start-Process ExitCode returns null when stdout/stderr are
redirected to files (or even via pipes). This wrapper uses Python's
subprocess.run which captures exit code reliably, then exits with that
code. PowerShell reads the wrapper's exit code as if it were the inner
script's exit code.

Usage (from PowerShell):
    $p = Start-Process python -ArgumentList "run_stage.py", "--label", "stage5",
                                                       "--out", "stdout.log",
                                                       "--err", "stderr.log",
                                                       "--timeout", "1800",
                                                       "script_path.py", "arg1", "arg2"
                              -RedirectStandardOutput "wrapper_stdout.log" `
                              -RedirectStandardError "wrapper_stderr.log" `
                              -NoNewWindow -PassThru
    Wait-Process $p -Timeout 1800 -ErrorAction SilentlyContinue
    if (-not $p.HasExited) { $p.Kill($true) }
    $p.Refresh()
    $exitCode = $p.ExitCode  # NOW RELIABLE

The wrapper writes labels to its stderr (with [STDOUT]/[STDERR] tags)
so the user can see which output is which.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


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
            try:
                rc = proc.wait(timeout=args.timeout)
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
