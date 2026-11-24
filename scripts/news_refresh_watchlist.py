"""Re-render watchlist.html with the freshest available news.

Runs outside the main nightly pipeline. It re-renders only the live
C:\\Groove-Lab\\watchlist.html from the latest canonical stock_news rows.
The certified public/watchlist.html and public/data/watchlist-full.json
remain untouched, so the D056-3 marker and GitHub Pages release stay valid.

Important:
- No download, no per-ticker HTML render, no full publish chain.
- C:\\Groove-Lab\\watchlist.html is the live groovelab page and is overwritten.
- No GitHub Pages push and no certified public artifact is modified.
- The dedicated news DB tasks (OpenAlice News Refresh / RSS Refresh /
  AI-Telegram Stock News Auto Refresh) keep stock_news fresh; this
  script just picks up their newest entries.

Output:
  reports\\news_refresh_watchlist_<timestamp>.log   (line-by-line)
  _debug\\news_refresh_status.json                  (last-run status)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

RUNTIME = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNTIME))

DEBUG = RUNTIME / "_debug"
DEBUG.mkdir(exist_ok=True)
STATUS = DEBUG / "news_refresh_status.json"
PYTHON = r"C:\Python314\python.exe"
RENDER_SCRIPT = RUNTIME / "render_full_watchlist.py"
LOG_DIR = RUNTIME / "reports"
LOG_DIR.mkdir(exist_ok=True)
RENDER_TIMEOUT_SECONDS = 12 * 60


def _read_status() -> dict:
    if STATUS.is_file():
        try:
            return json.loads(STATUS.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _write_status(payload: dict) -> None:
    tmp = STATUS.with_name(f"{STATUS.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS)


def _resolve_data_date() -> str:
    """Latest data_date from the canonical daily OHLCV table.

    Mirrors pipeline_state.db_snapshot() so render_full_watchlist.py's
    snapshot/data_date check matches.
    """
    import db_client as db
    with db.get_cursor() as cur:
        cur.execute("SELECT MAX(Date) AS d FROM daily_data2_full")
        row = cur.fetchone()
    if not row or not row.get("d"):
        raise RuntimeError("daily_data2_full is empty; cannot refresh watchlist news")
    return str(row["d"])


def main() -> int:
    started_at = datetime.now()
    status = _read_status()
    prior = {
        "last_status": status.get("last_status"),
        "last_finished_at": status.get("last_finished_at"),
        "last_data_date": status.get("last_data_date"),
        "last_log": status.get("last_log"),
    }

    log_path = LOG_DIR / f"news_refresh_watchlist_{started_at:%Y%m%d_%H%M%S}.log"
    log_f = log_path.open("w", encoding="utf-8")
    log_f.write(f"# news_refresh_watchlist started {started_at.isoformat()}\n")
    log_f.flush()

    try:
        data_date = _resolve_data_date()
    except Exception as exc:
        log_f.write(f"FATAL: resolve data_date failed: {exc}\n")
        log_f.close()
        _write_status({**prior, "last_status": "failed",
                       "last_finished_at": datetime.now().isoformat(timespec="seconds"),
                       "last_error": f"resolve data_date: {exc}"})
        return 2

    # Price/pick identity remains tied to the canonical trading data date.
    # The live Groovelab page gets a separate news cutoff so a delayed price
    # provider does not hide news published today. Full nightly runs do not
    # set TW_NEWS_DATE and therefore remain reproducible at TW_DATA_DATE.
    news_target_date = datetime.now().date().isoformat()
    env = os.environ.copy()
    env.pop("TW_DATA_DATE", None)
    env["TW_NEWS_DATE"] = news_target_date
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [PYTHON, "-X", "utf8", str(RENDER_SCRIPT), "--groove-only"]
    log_f.write(f"$ {' '.join(cmd)}\n")
    log_f.write(f"  workdir={RUNTIME}\n")
    log_f.write(f"  data_date={data_date} (from daily_data2_full.MAX(Date))\n")
    log_f.write(f"  news_target_date={news_target_date} (live page cutoff)\n")
    log_f.flush()

    proc = subprocess.Popen(
        cmd,
        cwd=str(RUNTIME),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
    )
    output = ""
    timed_out = False
    try:
        output, _ = proc.communicate(timeout=RENDER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="backslashreplace")
        output = partial
        # Kill the complete renderer tree so the Scheduler timeout cannot
        # leave an orphan that overwrites the live page later.
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True, text=True, timeout=30,
        )
        try:
            tail, _ = proc.communicate(timeout=30)
            output += tail or ""
        except subprocess.TimeoutExpired:
            proc.kill()
            tail, _ = proc.communicate()
            output += tail or ""
    finally:
        if output:
            log_f.write(output)
        if timed_out:
            log_f.write(f"\nFATAL: renderer exceeded {RENDER_TIMEOUT_SECONDS} seconds\n")
        log_f.flush()
        log_f.close()

    exit_code = 124 if timed_out else proc.returncode

    finished_at = datetime.now()
    payload = {
        **prior,
        "last_started_at": started_at.isoformat(timespec="seconds"),
        "last_finished_at": finished_at.isoformat(timespec="seconds"),
        "last_data_date": data_date,
        "last_news_target_date": news_target_date,
        "last_log": str(log_path),
        "last_exit_code": exit_code,
        "output_mode": "groove-only",
        "timeout_seconds": RENDER_TIMEOUT_SECONDS,
    }
    if exit_code == 0:
        payload["last_status"] = "ok"
    else:
        payload["last_status"] = f"failed(exit={exit_code})"
    _write_status(payload)
    return 0 if exit_code == 0 else (exit_code or 1)


if __name__ == "__main__":
    sys.exit(main())
