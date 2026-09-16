"""Read-only DB/cache integration; render only into a new isolated directory."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cross_source_runner as csr
import pipeline_state as ps
from render_only import _render_one


def normalized(path):
    body = path.read_text(encoding="utf-8")
    return re.sub(r"2026-09-16 \d{2}:\d{2}", "generation-time", body)


def main():
    root = Path(tempfile.mkdtemp(prefix="tw-worker-acceptance-", dir=ps.REPO.parent))
    serial, parallel = root / "serial", root / "parallel"
    serial.mkdir(); parallel.mkdir()
    os.environ["TW_DATA_DATE"] = ps.db_snapshot()["data_date"]
    tickers = ["2330", "2317", "2303", "2454"]
    data = {t: csr.assemble(t, use_yfinance=False, fetch_news=False, cache_only=True) for t in tickers}
    start = time.monotonic()
    for t in tickers:
        result = _render_one(t, data[t], str(serial), os.environ["TW_DATA_DATE"])
        if result != (t, True): raise RuntimeError(result)
    serial_sec = time.monotonic() - start
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_render_one, t, data[t], str(parallel), os.environ["TW_DATA_DATE"]) for t in tickers]
        for t, future in zip(tickers, futures):
            result = future.result(timeout=120)
            if result != (t, True): raise RuntimeError(result)
    for t in tickers:
        if normalized(serial / f"{t}.html") != normalized(parallel / f"{t}.html"):
            raise RuntimeError(f"serial/process output mismatch: {t}")
    print(f"WORKER_ACCEPTANCE root={root} tickers={len(tickers)} serial_sec={serial_sec:.1f} parallel_sec={time.monotonic()-start:.1f}", flush=True)


if __name__ == "__main__":
    main()
