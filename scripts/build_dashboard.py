"""One-page dashboard backed by certified nightly and actual publication evidence."""
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pipeline_state as ps

REPORTS_DIR = ps.REPORTS
PUBLIC_DATA = ps.PUBLIC / "data"
DASHBOARD_PATH = REPORTS_DIR / "dashboard.md"
DASHBOARD_PUBLIC_PATH = PUBLIC_DATA / "dashboard.md"
TASKS = ["daily-report", "market-screen", "yfinance", "health-check", "company-refresh", "sync-legacy", "marker-watchdog", "publish", "postflight"]


def fetch_cron_lastruns():
    command = "$names = " + ",".join("'tw-invest-suite-" + n + "'" for n in TASKS) + "; @($names | ForEach-Object { $t=Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue; $i=Get-ScheduledTaskInfo -TaskName $_ -ErrorAction SilentlyContinue; [pscustomobject]@{task=$_; state=[string]$t.State; last_run=if($i){$i.LastRunTime.ToString('o')}else{$null}; rc=if($i){[long]$i.LastTaskResult}else{$null}} }) | ConvertTo-Json -Compress"
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode:
        raise RuntimeError("Scheduler query failed")
    return json.loads(r.stdout)


def evaluate(marker, publication, issues, in_progress=False):
    if not marker and not in_progress:
        issues.append(("CRITICAL", "本次 nightly 尚無有效完成證據"))
    if not marker or publication.get("nightly_id") != marker.get("nightly_id") or publication.get("status") != "verified":
        issues.append(("WARNING", "本次 GitHub Pages 發布尚未驗證；HTTP 200 不等於資料已更新"))
    return "CRITICAL" if any(s == "CRITICAL" for s, _ in issues) else "WARNING" if issues else "OK"


def render_dashboard():
    issues = []
    marker = None
    in_progress = False
    try:
        marker = ps.verify_marker()
        if marker.get('maintenance_data_date') and marker['maintenance_data_date'] != marker['data_date']:
            issues.append(('WARNING', f"融資維持率來源日 {marker['maintenance_data_date']}，報價資料日 {marker['data_date']}；來源落後一個交易日"))
        if marker.get("render_data_issues"):
            issues.append(("WARNING", f"{len(marker['render_data_issues'])} 個股資料不完整，頁面已標示；fresh={marker['fresh_render_count']} ／ rendered={marker['render_count']}"))
        if marker.get("watchlist_fetch_errors"):
            issues.append(("WARNING", f"{len(marker['watchlist_fetch_errors'])} 個 watchlist ticker 補充資料不完整；各卡片列出失敗來源"))
        if marker.get("render_numeric_issues"):
            issues.append(("WARNING", f"{len(marker['render_numeric_issues'])} 個股的估值／基本面來源含無效數值，已標為缺漏並在頁面警示"))
    except Exception as e:
        current = ps.read_json(ps.STATE) if ps.STATE.exists() else {}
        in_progress = ps.owner_running(current)
        issues.append(("WARNING" if in_progress else "CRITICAL", "nightly 執行中，等待完成" if in_progress else str(e)))
    try:
        snapshot = ps.db_snapshot()
    except Exception as e:
        snapshot = {}
        issues.append(("CRITICAL", f"DB integrity: {e}"))
    try:
        publication = ps.read_json(ps.RUNTIME / "_debug" / "publication_result.json")
    except Exception:
        publication = {}
    try:
        cron = fetch_cron_lastruns()
    except Exception as e:
        cron = []
        issues.append(("CRITICAL", str(e)))
    import db_client as db
    with db.get_cursor() as c:
        c.execute("SELECT Ticker,COUNT(*) AS n FROM metadata_quarantine WHERE resolved_at IS NULL GROUP BY Ticker")
        quarantine = c.fetchall()
    for item in quarantine:
        issues.append(("WARNING" if item["Ticker"] == "7768" else "CRITICAL", f"Quarantine {item['Ticker']}: {item['n']} open; PENDING J 需處理，未自動豁免新增列"))
    for task in cron:
        if task["rc"] is None:
            issues.append(("CRITICAL", f"{task['task']}: missing task/result"))
        elif task["state"] != "Running" and task["rc"] != 0:
            severity = "CRITICAL" if task["task"].endswith(("daily-report", "market-screen")) else "WARNING"
            issues.append((severity, f"{task['task']}: rc={task['rc']}; 請見當次檢查明細"))
    post_path = ps.RUNTIME / "_debug" / "postflight_latest.json"
    if post_path.exists():
        post = ps.read_json(post_path)
        if marker and post.get("nightly_id") == marker["nightly_id"] and not post.get("overall_pass"):
            issues.append(("CRITICAL", "本次 postflight 未通過"))
    status = evaluate(marker, publication, issues, in_progress)
    icons = {"CRITICAL": "🔴", "WARNING": "🟡", "OK": "🟢"}
    lines = ["# tw-invest-suite Daily Dashboard", f"**Generated**: {datetime.now().isoformat(timespec='seconds')}",
             f"**OVERALL**: {icons[status]} {status}", "",
             f"**Data date**: {snapshot.get('data_date', 'UNKNOWN')}",
             f"**DB picks**: {snapshot.get('picks_count', '?')} active; run_id={snapshot.get('run_id', '?')}",
             f"**OHLCV coverage**: {snapshot.get('ohlcv_rows', '?')} rows ／ {snapshot.get('ohlcv_tickers', '?')} tickers",
             f"**Nightly**: {marker['nightly_id'] if marker else 'UNVERIFIED'}",
             f"**Optional degraded**: {marker.get('degraded_stages', '?') if marker else '?'}",
             f"**Publication**: {publication.get('status', 'pending')} ／ data_date={publication.get('data_date', '?')}",
             f"**Verified at**: {publication.get('verified_at', 'not yet')}",
             f"**Published commit**: {publication.get('published_commit', 'not yet')}", "", "## Action items"]
    lines += [f"- {icons[severity]} {message}" for severity, message in issues] or ["- 無"]
    lines += ["", "## Cron results", "| Task | State | LastRun | RC |", "|---|---|---|---|"]
    lines += [f"| {t['task']} | {t['state']} | {t['last_run']} | {t['rc']} |" for t in cron]
    lines += ["", "## Scope", "- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。",
              "- chips／sectors／concepts 為手動更新頁面，未列為每日更新成功證據。",
              "- FinMind weekly、Weekly Shareholding 1330、cloudflared：保留 PENDING，未宣稱已修復。", ""]
    return "\n".join(lines), status


def main():
    try:
        md, status = render_dashboard()
    except Exception as e:
        status = "CRITICAL"
        md = f"# tw-invest-suite Daily Dashboard\n**Generated**: {datetime.now().isoformat()}\n**OVERALL**: 🔴 CRITICAL\n\nDashboard failed: {e}\n"
    for path in (DASHBOARD_PATH, DASHBOARD_PUBLIC_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(md, encoding="utf-8")
        tmp.replace(path)
    print(f"dashboard: {status} ({DASHBOARD_PATH})")
    return {"OK": 0, "WARNING": 1, "CRITICAL": 2}[status]


if __name__ == "__main__":
    sys.exit(main())
