"""Serial supplemental fetches in killable processes; committed picks stay intact."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from run_stage import _kill_tree


def fetch_tickers(tickers, timeout_sec=45, budget_sec=360, worker_command=None):
    if timeout_sec <= 0 or budget_sec <= 0:
        raise ValueError("fetch budgets must be positive")
    tickers = list(dict.fromkeys(tickers))
    deadline = time.monotonic() + budget_sec
    results = {}
    # FinMind calls must remain serial under the project's rate-limit contract.
    with tempfile.TemporaryDirectory(prefix="tw-deep-dive-") as folder:
        root = Path(folder)
        for index, ticker in enumerate(tickers):
            remaining = deadline - time.monotonic()
            error = "deep dive budget: supplemental data unavailable"
            if remaining > 0:
                output = root / f"{index}.json"
                command = worker_command(ticker, output) if worker_command else [
                    sys.executable, str(Path(__file__).resolve()), "--worker", ticker, "--out", str(output)]
                with (root / f"{index}.log").open("wb") as log:
                    proc = subprocess.Popen(command, stdout=log, stderr=log)
                    try:
                        rc = proc.wait(timeout=min(timeout_sec, remaining))
                        if rc == 0:
                            data = json.loads(output.read_text(encoding="utf-8"))
                            if not isinstance(data, dict) or data.get("stock_id") != ticker:
                                raise ValueError("worker returned a different ticker")
                            results[ticker] = data
                        else:
                            error = "deep dive fetch: supplemental worker failed"
                    except subprocess.TimeoutExpired:
                        _kill_tree(proc)
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
                        error = "deep dive timeout: supplemental data unavailable"
                    except (OSError, ValueError):
                        error = "deep dive fetch: invalid supplemental result"
            results.setdefault(ticker, {"stock_id": ticker, "fetch_errors": [error]})
            print(f"  [{index+1}/{len(tickers)}] {ticker} supplemental "
                  f"{'WARNING' if results[ticker].get('fetch_errors') else 'OK'}", flush=True)
    return results


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    import analyze_stock
    data = analyze_stock.fetch_all(args.worker)
    args.out.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
