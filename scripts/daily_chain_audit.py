"""Read-only daily certification audit for the tw-invest-suite / AI-Telegram chain.

The audit is deliberately independent of ChatGPT.  It reads the official
calendar, the canonical DB, release receipts, public manifests, AI-Telegram
receipts and Windows Task Scheduler settings.  It never runs the production
pipeline and never fabricates a date, marker or delivery receipt.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from typing import Any

try:
    from market_calendar import expected_session, is_session
except ImportError:  # package import in tests; never invent a weekday calendar
    from scripts.market_calendar import expected_session, is_session

try:
    import pipeline_state as ps
except ImportError:  # package import in tests
    from scripts import pipeline_state as ps


EXIT_HEALTHY = 0
EXIT_DEGRADED = 10
EXIT_FAILED = 20
EXIT_INTERNAL = 30
MARKER_VERSION = "D056-3"


@dataclass
class AuditConfig:
    source_root: Path
    runtime_root: Path
    public_root: Path
    ai_root: Path
    state_root: Path
    remote_urls: list[str] = field(default_factory=list)
    scheduler_tasks: list[str] = field(default_factory=list)
    notify: bool = False


def _first_existing(*paths: str | Path) -> Path:
    for raw in paths:
        p = Path(raw).expanduser()
        if p.exists():
            return p
    return Path(paths[0]).expanduser()


def resolve_config(config_path: Path | None = None, notify: bool = False) -> AuditConfig:
    source = _first_existing(r"C:\Users\icemo\Projects\tw-invest-suite")
    runtime = _first_existing(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
    public = _first_existing(r"C:\Groove-Lab", r"E:\Groove-Lab")
    ai = _first_existing(r"D:\CODEX\AI-Telegram", r"E:\CODEX\AI-Telegram")
    state = public / "automation" / "audit"
    cfg = {
        "source_root": str(source),
        "runtime_root": str(runtime),
        "public_root": str(public),
        "ai_root": str(ai),
        "state_root": str(state),
        "remote_urls": [
            "https://walterLiu168.github.io/tw-invest-suite/data",
            "https://groovelab.dev/data",
        ],
        "scheduler_tasks": [
            "AI-Telegram Daily Report 22-47",
            "AI-Telegram Enrichment Update 18-25",
            "AI-Telegram Pattern Scan 18-30",
            "AI-Telegram Scheduled Pipeline",
            "tw-invest-suite-market-screen",
            "tw-invest-suite-daily-report",
            "tw-invest-suite-daily-chain-audit",
        ],
    }
    if config_path and config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                cfg.update({k: v for k, v in loaded.items() if v is not None})
        except (OSError, json.JSONDecodeError):
            pass
    return AuditConfig(
        source_root=Path(cfg["source_root"]),
        runtime_root=Path(cfg["runtime_root"]),
        public_root=Path(cfg["public_root"]),
        ai_root=Path(cfg["ai_root"]),
        state_root=Path(cfg["state_root"]),
        remote_urls=list(cfg.get("remote_urls", [])),
        scheduler_tasks=list(cfg.get("scheduler_tasks", [])),
        notify=notify,
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def latest_nonempty_json(directory: Path, pattern: str) -> tuple[Path | None, Any]:
    candidates = [p for p in directory.glob(pattern) if p.is_file() and p.stat().st_size > 2]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        value = load_json(p)
        if value is not None:
            return p, value
    return None, None


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def json_path(root: Path, name: str) -> Path:
    return root / "_debug" / name


def run_ps_json(script: str, timeout: int = 30) -> tuple[Any, str, int]:
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc), 1
    raw = (proc.stdout or "").strip()
    try:
        return json.loads(raw) if raw else None, proc.stderr.strip(), proc.returncode
    except json.JSONDecodeError:
        return None, raw[-2000:], proc.returncode


def scheduler_snapshot(tasks: list[str]) -> dict[str, Any]:
    encoded = json.dumps(tasks).replace("'", "''")
    command = (
        "$names='" + encoded + "' | ConvertFrom-Json; $out=@(); "
        "foreach($n in $names){$t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue; "
        "if($null -eq $t){$out += [pscustomobject]@{task=$n;found=$false};continue}; "
        "$i=Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue; "
        "$xml=[xml](Export-ScheduledTask -TaskName $n); "
        "$out += [pscustomobject]@{task=$n;found=$true;state=[string]$t.State;" 
        "logon=[string]$xml.Task.Principals.Principal.LogonType;" 
        "wakeToRun=([string]$xml.Task.Settings.WakeToRun -eq 'true');" 
        "startWhenAvailable=([string]$xml.Task.Settings.StartWhenAvailable -eq 'true');" 
        "multipleInstances=[string]$xml.Task.Settings.MultipleInstancesPolicy;" 
        "executionLimit=[string]$xml.Task.Settings.ExecutionTimeLimit;" 
        "lastRun=[string]$i.LastRunTime;lastResult=[int64]$i.LastTaskResult}}; "
        "$out | ConvertTo-Json -Compress"
    )
    value, detail, rc = run_ps_json(command)
    return {"available": rc == 0 and value is not None, "tasks": value or [], "detail": detail}


def _powercfg(*args: str) -> dict[str, Any]:
    """Run powercfg and capture stdout; never raises."""
    try:
        p = subprocess.run(["powercfg", *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return {"returncode": p.returncode, "output": (p.stdout or p.stderr or "").strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": -1, "output": str(exc)}


def _kernel_power_events(limit: int = 60) -> dict[str, Any]:
    """Last real sleep (event 42) and last resume (event 1) from Kernel-Power.

    Readable without elevation, unlike `powercfg /waketimers`.
    """
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$ev = Get-WinEvent -FilterHashtable @{LogName='System';"
        " ProviderName='Microsoft-Windows-Kernel-Power'} -MaxEvents " + str(limit) + ";"
        "$rows = @(); foreach ($e in $ev) { if ($e.Id -in 42,1,107) {"
        " $rows += [pscustomobject]@{ id=[int]$e.Id; when=$e.TimeCreated.ToString('o') } } };"
        "$rows | ConvertTo-Json -Compress"
    )
    value, detail, rc = run_ps_json(script)
    rows = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    sleeps = sorted((r for r in rows if r.get("id") == 42), key=lambda r: r.get("when", ""))
    resumes = sorted((r for r in rows if r.get("id") == 1), key=lambda r: r.get("when", ""))
    return {
        "available": rc == 0 and bool(rows),
        "detail": detail,
        "last_sleep": sleeps[-1]["when"] if sleeps else None,
        "last_resume": resumes[-1]["when"] if resumes else None,
        "sleep_events": len(sleeps),
        "resume_events": len(resumes),
    }


def wake_timer_snapshot() -> dict[str, Any]:
    """Evidence about physical sleep/wake and the timers that should wake the box.

    `powercfg /waketimers` needs an elevated shell, so it cannot be the only
    source: an unelevated scheduled task would always report the evidence as
    unreadable.  Collect instead the sources that do not need elevation, and
    state plainly whether the box has ever slept.
    """
    lastwake = _powercfg("/lastwake")
    states = _powercfg("/a")
    armed = _powercfg("/waketimers")
    events = _kernel_power_events()
    boot = ""
    try:
        import datetime as _dt
        boot = _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    except Exception:
        boot = ""
    wake_records = None
    for token in lastwake.get("output", "").replace("\n", " ").split():
        if token.isdigit():
            wake_records = int(token)
            break
    available = bool(lastwake.get("returncode") == 0 or events.get("available"))
    state = "unknown"
    if wake_records == 0 and not events.get("resume_events"):
        state = "never_resumed"
    elif events.get("resume_events"):
        state = "resume_observed"
    elif events.get("last_sleep"):
        state = "slept_without_clean_resume"
    return {
        "available": available,
        "state": state,
        "wake_records": wake_records,
        "lastwake": lastwake.get("output", "")[-600:],
        "sleep_states": states.get("output", "")[-600:],
        "waketimers_requires_elevation": armed.get("returncode") != 0,
        "waketimers_output": armed.get("output", "")[-600:],
        "kernel_power": events,
        "checked_at": boot,
    }


def scheduler_findings(rows: list[dict[str, Any]]) -> list[str]:
    findings = []
    native = {"AI-Telegram Enrichment Update 18-25",
              "tw-invest-suite-market-screen", "tw-invest-suite-daily-report",
              "tw-invest-suite-daily-chain-audit"}
    for row in rows:
        name = str(row.get("task") or "")
        if not row.get("found"):
            findings.append(f"Task Scheduler 任務不存在：{name}")
            continue
        if name == "AI-Telegram Scheduled Pipeline" and row.get("logon") not in {"S4U", "ServiceAccount"}:
            findings.append("AI primary 未使用 S4U/ServiceAccount（僅報告，不自動修改）")
        if name in native:
            if row.get("logon") not in {"S4U", "ServiceAccount"}:
                findings.append(f"原生自動任務未使用 S4U/ServiceAccount：{name}")
            if not row.get("wakeToRun"):
                findings.append(f"原生自動任務未啟用 WakeToRun：{name}")
            if not row.get("startWhenAvailable"):
                findings.append(f"原生自動任務未啟用 StartWhenAvailable：{name}")
    return findings


def db_snapshot(target: str) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "unavailable", "target_date": target}
    try:
        # S4U tasks do not always inherit the interactive process environment.
        # Load the already-configured user-scoped variable from HKCU without
        # writing it to any receipt or log. No credential is stored here.
        if not os.environ.get("TW_DB_PASSWORD") and os.name == "nt":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    value, _ = winreg.QueryValueEx(key, "TW_DB_PASSWORD")
                if value:
                    os.environ["TW_DB_PASSWORD"] = str(value)
            except (OSError, ImportError):
                pass
        import db_client as db  # type: ignore
        with db.get_cursor() as cur:
            cur.execute("SELECT MAX(Date) AS latest_date, COUNT(*) AS row_count, COUNT(DISTINCT Ticker) AS ticker_count FROM daily_data2_full")
            row = cur.fetchone() or {}
            result.update({"status": "ok", "latest_date": str(row.get("latest_date") if isinstance(row, dict) else row[0]),
                           "rows": int(row.get("row_count") if isinstance(row, dict) else row[1] or 0),
                           "tickers": int(row.get("ticker_count") if isinstance(row, dict) else row[2] or 0)})
            cur.execute("SELECT COUNT(DISTINCT Date) AS days FROM daily_data2_full WHERE Date <= %s", (target,))
            r = cur.fetchone() or {}
            result["price_days"] = int(r.get("days") if isinstance(r, dict) else r[0] or 0)
            cur.execute("SHOW COLUMNS FROM daily_data2_full")
            cols = [str((x.get("Field") if isinstance(x, dict) else x[0])) for x in cur.fetchall()]
            lower = {c.lower(): c for c in cols}
            required = ["foreignnet", "investmentnet", "dealernet", "marginbalance", "shortbalance"]
            result["columns"] = {name: lower.get(name) for name in required}
            result["daytrade_columns"] = [c for c in cols if "daytrade" in c.lower()]
            result["shares_column"] = next((lower[k] for k in ("sharesoutstanding_shares", "sharesoutstanding", "shares") if k in lower), None)
            cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('stock_shareholding','shareholding_daily','finmind_taiwan_shareholding','finmind_taiwan_stock_shareholding')")
            r = cur.fetchone() or {}
            result["shareholding_tables"] = int(r.get("n") if isinstance(r, dict) else r[0] or 0)
    except Exception as exc:  # no credentials or DB unavailable is evidence, not a crash
        result["detail"] = type(exc).__name__
    return result


def canonical_history_snapshot(cfg: AuditConfig, target: str, marker: dict[str, Any]) -> dict[str, Any]:
    """Read actual same-run source verification, never infer it from price counts."""
    receipt_path = json_path(cfg.runtime_root, "maintenance_fetch.json")
    receipt = load_json(receipt_path) or {}
    findings = []
    # One rule, three consumers: the catch-up, the guard and this audit all ask
    # pipeline_state.maintenance_claim_holds() whether the maintenance receipt
    # still certifies this marker.  A weekend re-render inherits the receipt of
    # the run that certified the same canonical inputs, and that inheritance can
    # be several generations deep - so compare the canonical digest, not the
    # nightly id alone.
    if not ps.maintenance_claim_holds(marker, receipt):
        findings.append("canonical maintenance identity 不一致或缺失")
    six = {"price", "inst", "margin", "daytrade", "shareholding", "shares"}
    five = six - {"price"}
    if (receipt.get("status") != "ok" or receipt.get("canonical_refresh_date") != target
            or set(receipt.get("canonical_datasets", [])) != six
            or receipt.get("source_value_mismatches") != 0
            or receipt.get("api_errors") != 0):
        findings.append("canonical 六來源逐欄驗證未通過")
    for prefix in ("price", "chips"):
        if (receipt.get(f"{prefix}_history_sessions", 0) < 30
                or receipt.get(f"{prefix}_history_mismatches") != 0):
            findings.append(f"{prefix} 30-session 來源驗證未通過")
    if set(receipt.get("chips_history_datasets", [])) != five:
        findings.append("五條歷史籌碼來源清單缺失")
    # Cross-check receipt against the actual normal maintenance stdout.  The log
    # must belong to the run that wrote the receipt - on a weekend re-render that
    # is the inherited run, not the marker.
    receipt_run = receipt.get("nightly_id")
    logs = sorted((cfg.runtime_root / "_debug" / "stage_logs").glob(
        f"*_{receipt_run}_stage1_finmind_maint.log")) if receipt_run else []
    content = "\n".join(p.read_text(encoding="utf-8-sig", errors="replace") for p in logs)
    source_lanes = set(re.findall(r"^SOURCE_VERIFY dataset=(\w+) date=" + re.escape(target)
                                + r" tickers=[1-9]\d* mismatch=0$", content, re.M))
    price = re.search(r"^HISTORY_VERIFY date=" + re.escape(target)
                      + r" sessions=(\d+) rows=([1-9]\d*) revised=\d+ mismatch=0$", content, re.M)
    chips = re.search(r"^CHIPS_HISTORY_VERIFY date=" + re.escape(target)
                      + r" sessions=(\d+) datasets=([\w,]+) rows=([1-9]\d*) revised=\d+ mismatch=0$", content, re.M)
    db_readback = re.search(r"^DB_VERIFY phase=canonical range=" + re.escape(target + ".." + target)
                           + r" expected=([1-9]\d*) complete=(\d+) missing=0(?: |$)", content, re.M)
    if (source_lanes != six or not price or int(price[1]) < 30 or not chips
            or int(chips[1]) < 30 or set(chips[2].split(",")) != five
            or not db_readback or db_readback[1] != db_readback[2]
            or int(price[1]) != receipt.get('price_history_sessions')
            or int(chips[1]) != receipt.get('chips_history_sessions')
            or int(db_readback[1]) != receipt.get('canonical_refresh_rows')):
        findings.append("canonical 同批次逐欄／DB讀回 log 證據缺失")
    return {"status": "verified" if not findings else "unverified", "receipt_path": str(receipt_path),
            "nightly_id": receipt.get("nightly_id"), "data_date": receipt.get("requested_date"),
            "price_history_sessions": int(price[1]) if price else None,
            "chips_history_sessions": int(chips[1]) if chips else None,
            "price_rows_checked": int(price[2]) if price else None,
            "chips_rows_checked": int(chips[3]) if chips else None,
            "log_paths": [str(p) for p in logs], "findings": findings}


def artifact_snapshot(cfg: AuditConfig, target: str) -> dict[str, Any]:
    root = cfg.runtime_root
    marker = load_json(json_path(root, "last_completed.json")) or {}
    publication = load_json(json_path(root, "publication_result.json")) or {}
    postflight = load_json(json_path(root, "postflight_latest.json")) or {}
    pipeline = load_json(json_path(root, "pipeline_run.json")) or {}
    manifest = {}
    for candidate in (cfg.public_root / "data" / f"publish_manifest_{target}.json", cfg.public_root / "data" / f"publish_manifest_{target.replace('-', '')}.json"):
        loaded = load_json(candidate)
        if isinstance(loaded, dict):
            manifest = loaded
            break
    receipts = load_json(json_path(root, "all_reports_receipt.json")) or {}
    identity = {
        "marker_version": marker.get("marker_version"), "marker_status": marker.get("status"),
        "data_date": marker.get("data_date"), "nightly_id": marker.get("nightly_id"),
        "run_id": marker.get("run_id"), "publication_status": publication.get("status"),
        "report_status": publication.get("report_status"), "postflight_exit": publication.get("postflight_exit"),
        "postflight_pass": postflight.get("overall_pass"), "pipeline_status": pipeline.get("status"),
    }
    findings: list[str] = []
    if marker.get("marker_version") != MARKER_VERSION or marker.get("status") != "ok": findings.append("D056-3 marker 未通過")
    if marker.get("data_date") != target: findings.append("marker data_date 與目標不一致")
    if publication.get("nightly_id") != marker.get("nightly_id") or publication.get("data_date") != target: findings.append("publication identity 不一致")
    if publication.get("status") != "verified" or publication.get("report_status") != "verified" or publication.get("postflight_exit") != 0: findings.append("publication/postflight 未 certified")
    if (postflight.get("overall_pass") is not True or postflight.get("data_date") != target
            or postflight.get("nightly_id") != marker.get("nightly_id")):
        findings.append("postflight 缺失、失敗或批次不一致")
    for label, receipt in (("manifest", manifest), ("all_reports", receipts)):
        if (not marker.get("nightly_id") or receipt.get("nightly_id") != marker.get("nightly_id")
                or receipt.get("data_date") != target):
            findings.append(f"{label} identity 不一致")
    if receipts.get("status") != "ok" or len(receipts.get("artifacts") or []) < 50:
        findings.append("all_reports 收據未通過或不足 50 份")
    groove = load_json(json_path(root, "groove_publication_result.json")) or {}
    if (groove.get("status") != "verified" or groove.get("nightly_id") != marker.get("nightly_id")
            or groove.get("data_date") != target or groove.get("run_id") != marker.get("run_id")):
        findings.append("groovelab 發布收據缺失或批次不一致")
    artifact_count = 0
    hashes_bad = 0
    if isinstance(manifest, dict):
        entries = manifest.get("artifacts") or manifest.get("files") or []
        if isinstance(entries, dict): entries = list(entries.values())
        for item in entries if isinstance(entries, list) else []:
            rel = (item.get("path") or item.get("relative_path") or item.get("file") or item.get("gh_path")) if isinstance(item, dict) else None
            if not rel: continue
            p = cfg.public_root / str(rel)
            artifact_count += 1
            expected = item.get("sha256") if isinstance(item, dict) else None
            if not expected or not p.is_file() or p.stat().st_size == 0 or sha256_file(p) != expected: hashes_bad += 1
    if artifact_count < 50: findings.append(f"manifest artifacts={artifact_count} (<50)")
    if hashes_bad: findings.append(f"manifest missing/hash_mismatch={hashes_bad}")
    return {"identity": identity, "manifest": {"artifact_count": artifact_count, "hashes_bad": hashes_bad}, "reports_receipt": receipts, "findings": findings}


def ai_snapshot(cfg: AuditConfig, target: str) -> dict[str, Any]:
    output = cfg.ai_root / "output"
    docs = cfg.ai_root / "docs"
    gate_path, gate = latest_nonempty_json(cfg.ai_root / "logs", f"canonical_universe_{target}_*.json")
    state = load_json(output / "pipeline_state" / "telegram_delivery_state.json") or {}
    four = [docs / f"daily_report_{target.replace('-', '')}_{suffix}.md"
            for suffix in ("01_market", "02_review", "03_best_by_bucket", "04_watchlist")]
    four = [p for p in four if p.is_file() and p.stat().st_size > 0]
    chips = docs / f"chips_summary_{target.replace('-', '')}.md"
    chip_result = load_json(json_path(cfg.runtime_root, "chip_telegram_result.json")) or {}
    ledger = load_json(json_path(cfg.runtime_root, "chip_telegram_deliveries.json")) or {}
    findings: list[str] = []
    if not isinstance(gate, dict) or gate.get("target_date") != target or not gate.get("available_tickers"):
        findings.append("canonical gate 缺失或資料日不一致")
    if len(four) < 4: findings.append(f"dated Telegram reports={len(four)} (<4)")
    if not chips.is_file() or chips.stat().st_size == 0: findings.append("chips summary 缺少或空白")
    marker = load_json(json_path(cfg.runtime_root, "last_completed.json")) or {}
    message_id = chip_result.get("message_id")
    if chip_result.get("status") not in {"sent", "already_sent", "verified"} or type(message_id) is not int or message_id <= 0:
        findings.append("chips Telegram receipt 無正整數 message_id")
    # A receipt may legitimately name an earlier run: the chips summary is sent
    # once per session, so a re-run of the same session reuses the delivery.  The
    # reuse has to be explicit (reused_for_nightly_id), otherwise a receipt that
    # simply claims the wrong run is the same failure.
    identity_ok = (chip_result.get("nightly_id") == marker.get("nightly_id")
                   or chip_result.get("reused_for_nightly_id") == marker.get("nightly_id"))
    if (chip_result.get("data_date") != target or not marker.get("nightly_id")
            or not identity_ok):
        findings.append("chips Telegram receipt 日期或批次不一致")
    key = f"{target}:{chip_result.get('chat_hash', '')}"
    entry = ledger.get(key) if isinstance(ledger, dict) else None
    fields = ("data_date", "nightly_id", "chat_hash", "message_id", "message_sha256")
    # A weekend re-render reproduces the same chips summary for the same session
    # and must not send a duplicate Telegram message.  The delivery ledger keeps
    # the run that actually sent it; the receipt names the run that observed the
    # existing delivery.  Every other delivery identity field still has to match.
    compare = [k for k in fields if k != "nightly_id" or not chip_result.get("already_sent")]

    def agrees(field):
        # The ledger is keyed by date, so an entry written before the receipt grew
        # a data_date field still agrees with the receipt about that date.
        if not isinstance(entry, dict):
            return False
        value = entry.get(field, chip_result.get(field))
        return bool(chip_result.get(field)) and value == chip_result.get(field)

    if (not isinstance(entry, dict) or entry.get("status") != "sent"
            or any(not agrees(k) for k in compare)):
        findings.append("chips ledger 缺失或與 receipt 不一致（不重送）")
    return {"gate": {"path": str(gate_path) if gate_path else None, "value": gate}, "reports": len(four), "chips_summary": chips.is_file(), "chip_result": chip_result, "ledger": ledger, "delivery_state_entries": len(state) if isinstance(state, dict) else 0, "findings": findings}


def remote_snapshot(cfg: AuditConfig, target: str, nightly_id: str | None) -> dict[str, Any]:
    checks = []
    for base in cfg.remote_urls:
        url = base.rstrip("/") + f"/publish_manifest_{target}.json"
        item: dict[str, Any] = {"url": url, "status": "unavailable"}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "tw-invest-suite-daily-chain-audit/1.0"})
            with urllib.request.urlopen(request, timeout=20) as resp:
                body = resp.read()
            data = json.loads(body.decode("utf-8-sig"))
            item.update({"status": "ok", "data_date": data.get("data_date"), "nightly_id": data.get("nightly_id"), "rawSHA": hashlib.sha256(body).hexdigest()})
            local_sha = sha256_file(cfg.public_root / "data" / f"publish_manifest_{target}.json")
            if not local_sha or item["rawSHA"] != local_sha:
                item["status"] = "mismatch"
            if data.get("data_date") != target or (nightly_id and data.get("nightly_id") != nightly_id): item["status"] = "mismatch"
        except Exception as exc:
            # Some older deployments omit hyphens from the manifest filename.
            if url.endswith(f"publish_manifest_{target}.json"):
                fallback = base.rstrip("/") + f"/publish_manifest_{target.replace('-', '')}.json"
                try:
                    request = urllib.request.Request(fallback, headers={"User-Agent": "tw-invest-suite-daily-chain-audit/1.0"})
                    with urllib.request.urlopen(request, timeout=20) as resp:
                        body = resp.read()
                        data = json.loads(body.decode("utf-8-sig"))
                    item.update({"status": "ok", "url": fallback, "data_date": data.get("data_date"), "nightly_id": data.get("nightly_id"), "rawSHA": hashlib.sha256(body).hexdigest()})
                    local_sha = sha256_file(cfg.public_root / 'data' / f'publish_manifest_{target}.json')
                    if not local_sha or item['rawSHA'] != local_sha:
                        item['status'] = 'mismatch'
                    if data.get("data_date") != target or (nightly_id and data.get("nightly_id") != nightly_id): item["status"] = "mismatch"
                    checks.append(item)
                    continue
                except Exception:
                    pass
            item["detail"] = type(exc).__name__
        checks.append(item)
    return {"checks": checks, "findings": [f"remote {x['url']}={x['status']}" for x in checks if x["status"] != "ok"]}


def runtime_consistency_snapshot(cfg: AuditConfig) -> dict[str, Any]:
    names = ["daily_chain_audit.py", "run_daily_chain_audit.cmd", "register_daily_chain_audit.ps1", "daily_chain_audit_config.json"]
    rows = []
    for name in names:
        source = sha256_file(cfg.source_root / "scripts" / name)
        runtime = sha256_file(cfg.runtime_root / name)
        rows.append({"file": name, "source_sha256": source, "runtime_sha256": runtime, "match": bool(source and runtime and source == runtime)})
    return {"files": rows, "findings": [f"runtime mismatch: {x['file']}" for x in rows if not x["match"]]}


def fingerprint(report: dict[str, Any]) -> str:
    stable = {"status": report.get("status"), "target_date": report.get("target_date"), "findings": report.get("findings", [])}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def markdown(report: dict[str, Any]) -> str:
    lines = [f"# Daily Chain Audit {report['checked_at']}", "", f"- 狀態：**{report['status']}**", f"- 目標交易資料日：`{report['target_date']}`", f"- 今日交易日：`{report['current_session']}`", f"- 指紋：`{report['fingerprint']}`", "", "## Identity", ""]
    for k, v in report.get("artifacts", {}).get("identity", {}).items(): lines.append(f"- {k}: `{v}`")
    lines += ["", "## Findings", ""]
    lines += [f"- {x}" for x in report.get("findings", [])] or ["- 無"]
    lines += ["", "## Canonical history / forward validation", "",
              f"- Canonical history: `{json.dumps(report.get('canonical_history', {}), ensure_ascii=False)}`",
              f"- Forward validation: `{json.dumps(report.get('forward_validation', {}), ensure_ascii=False)}`"]
    lines += ["", "## Evidence", "", f"- DB: `{json.dumps(report.get('db', {}), ensure_ascii=False)}`", f"- Manifest: `{json.dumps(report.get('artifacts', {}).get('manifest', {}), ensure_ascii=False)}`", f"- AI: `{json.dumps(report.get('ai', {}), ensure_ascii=False)}`", f"- Scheduler: `{json.dumps(report.get('scheduler', {}), ensure_ascii=False)}`", f"- Wake timers (設定與實際事件分開): `{json.dumps(report.get('wake_timers', {}), ensure_ascii=False)}`", f"- Remote: `{json.dumps(report.get('remote', {}), ensure_ascii=False)}`"]
    return "\n".join(lines) + "\n"


def notify_if_changed(cfg: AuditConfig, report: dict[str, Any], previous: dict[str, Any] | None) -> None:
    if not cfg.notify or not previous or previous.get("fingerprint") == report.get("fingerprint"):
        return
    if report.get("status") not in {"FAILED", "DEGRADED", "RECOVERED", "COMPLETE"}:
        return
    try:
        sys.path.insert(0, str(cfg.ai_root))
        from telegram_sender import send_message  # type: ignore
        text = f"Daily Chain Audit {report['status']}\n資料日 {report['target_date']}\n" + "\n".join(report.get("findings", [])[:8])
        send_message(text, idempotency_key=f"daily-chain-audit:{report['target_date']}:{report['fingerprint']}")
    except Exception:
        pass


def date_at_least(value: Any, target: str) -> bool:
    try:
        return date.fromisoformat(str(value)[:10]) >= date.fromisoformat(target)
    except (TypeError, ValueError):
        return False


def acceptable_prediction_fallback(
    prediction: dict[str, Any], forward: dict[str, Any], *, target: str, current: str
) -> bool:
    """Accept one-session fallback when the official landed target is current."""
    return (
        prediction.get('status') == 'ok'
        and prediction.get('quality') == 'complete'
        and prediction.get('fallback') is True
        and prediction.get('expected_session') == current
        and prediction.get('data_date') == target
        and forward.get('latest_source_prediction_date') == target
        and date_at_least(forward.get('price_as_of'), target)
    )


def prediction_covers_target(prediction: dict[str, Any], forward: dict[str, Any], target: str) -> bool:
    # The forward job can already observe today's prices before today's nightly
    # inference. Its relative stale flag does not invalidate yesterday's audit.
    return (prediction.get('status') == 'ok'
            and date_at_least(prediction.get('data_date'), target)
            and date_at_least(forward.get('latest_source_prediction_date'), target)
            and date_at_least(forward.get('price_as_of'), target))


def audit(cfg: AuditConfig) -> dict[str, Any]:
    today = date.today()
    target = expected_session(today - timedelta(days=1))
    current = expected_session(today)
    db = db_snapshot(target)
    artifacts = artifact_snapshot(cfg, target)
    ai = ai_snapshot(cfg, target)
    nightly_id = artifacts.get("identity", {}).get("nightly_id")
    marker = load_json(json_path(cfg.runtime_root, "last_completed.json")) or {}
    history = canonical_history_snapshot(cfg, target, marker)
    forward = load_json(cfg.ai_root / 'output' / 'forward_validation' / 'summary.json') or {}
    prediction = load_json(cfg.ai_root / 'output' / 'daily_prediction_refresh' / 'latest.json') or {}
    prediction_attempt = load_json(cfg.ai_root / 'output' / 'daily_prediction_refresh' / 'latest_attempt.json') or {}
    model_inputs = load_json(cfg.ai_root / 'output' / 'model_input_refresh' / 'latest.json') or {}
    scheduler = scheduler_snapshot(cfg.scheduler_tasks)
    wake = wake_timer_snapshot()
    remote = remote_snapshot(cfg, target, nightly_id)
    consistency = runtime_consistency_snapshot(cfg)
    findings = list(artifacts.get("findings", [])) + list(ai.get("findings", [])) + list(remote.get("findings", [])) + list(consistency.get("findings", [])) + history["findings"]
    if not date_at_least(forward.get('price_as_of'), target):
        findings.append('forward ledger 尚未更新至目標資料日')
    if (forward.get('signal_stale') and not prediction_covers_target(prediction, forward, target)
            and not acceptable_prediction_fallback(
            prediction, forward, target=target, current=current)):
        findings.append('forward ledger 原始模型預測已過期；未產生新預測')
    if prediction.get('quality') == 'partial_auxiliary':
        findings.append('模型預測已更新，輔助來源缺項已標示：' + str(len(prediction.get('missing_optional_features', []))) + ' 個因子')
    if prediction_attempt.get('status') == 'failed':
        findings.append('最近一次模型推論失敗：' + str(prediction_attempt.get('error') or 'unknown error'))
    if model_inputs.get('status') in {'failed', 'degraded'}:
        findings.append('模型輔助輸入刷新未完整：' + str(model_inputs.get('status')))
    elif model_inputs and not date_at_least(model_inputs.get('data_date'), target):
        findings.append('模型輔助輸入日期落後目標交易日')
    if db.get("status") != "ok": findings.append("DB read-only check unavailable")
    elif db.get("latest_date") and db.get("latest_date") < target: findings.append("DB latest date 落後目標")
    task_rows = scheduler.get("tasks") if isinstance(scheduler.get("tasks"), list) else []
    if not scheduler.get("available"):
        findings.append("Task Scheduler 證據無法讀取")
    if not wake.get("available"):
        findings.append("電源喚醒計時器證據無法讀取；尚未驗證實際睡眠喚醒")
    elif wake.get("state") == "never_resumed":
        findings.append(
            "本機自上次開機後未曾從睡眠喚醒（powercfg /lastwake 記錄數 "
            f"{wake.get('wake_records')}；最後一次 sleep 事件 "
            f"{wake.get('kernel_power', {}).get('last_sleep')} 之後是硬重開而非喚醒）；"
            "實際睡眠喚醒尚未發生，需要一次受控睡眠才能驗證")
    elif wake.get("state") == "slept_without_clean_resume":
        findings.append(
            "曾於 " + str(wake.get("kernel_power", {}).get("last_sleep"))
            + " 進入睡眠，但沒有乾淨的喚醒記錄；喚醒後是否有排程執行仍未證明")
    elif wake.get("state") == "resume_observed":
        findings.append("偵測到睡眠後喚醒事件，但喚醒後的排程執行紀錄仍需另行核對")
    findings.extend(scheduler_findings(task_rows))
    if db.get("status") == "ok":
        if db.get("price_days", 0) < 30: findings.append("價格歷史不足 30 個交易日")
    if not is_session(today):
        status = "HEALTHY" if not findings else "DEGRADED"
    elif db.get("status") != "ok":
        status = "DEGRADED"
    elif db.get("latest_date") in {None, "None"} or (db.get("latest_date") and db.get("latest_date") < target):
        status = "WAITING_FOR_LANDED_SESSION" if not artifacts.get("findings") else "DEGRADED"
    else:
        status = "HEALTHY" if not findings else "DEGRADED"
    return {"checked_at": datetime.now().astimezone().isoformat(), "status": status, "target_date": target, "current_session": current, "db": db, "canonical_history": history, "forward_validation": forward, "daily_prediction": prediction, "daily_prediction_attempt": prediction_attempt, "model_input_refresh": model_inputs, "artifacts": artifacts, "ai": ai, "scheduler": scheduler, "wake_timers": wake, "remote": remote, "runtime_consistency": consistency, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only daily chain audit")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        assert fingerprint({"status": "HEALTHY", "target_date": "2026-01-01", "findings": []})
        assert isinstance(load_json(Path(__file__)), type(None))
        print("daily_chain_audit self-test: ok")
        return 0
    cfg = resolve_config(args.config, notify=args.notify and not args.no_notify)
    try:
        report = audit(cfg)
        report["fingerprint"] = fingerprint(report)
        cfg.state_root.mkdir(parents=True, exist_ok=True)
        previous = load_json(cfg.state_root / "latest.json")
        if previous and previous.get("status") == "DEGRADED" and report.get("status") == "HEALTHY": report["status"] = "RECOVERED"
        report["fingerprint"] = fingerprint(report)
        (cfg.state_root / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (cfg.state_root / "latest.md").write_text(markdown(report), encoding="utf-8")
        history = cfg.state_root / "history"; history.mkdir(exist_ok=True)
        (history / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{report['fingerprint']}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        notify_if_changed(cfg, report, previous if isinstance(previous, dict) else None)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if report["status"] in {"HEALTHY", "WAITING_FOR_LANDED_SESSION", "RECOVERED", "COMPLETE"}: return EXIT_HEALTHY
        return EXIT_DEGRADED if report["status"] == "DEGRADED" else EXIT_FAILED
    except Exception as exc:
        print(json.dumps({"status": "INTERNAL_ERROR", "error": type(exc).__name__}, ensure_ascii=False))
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
