# tw-pipeline-gui + tw-invest-suite 完整變更審查與交接

- 審查日期：2026-10-08（Asia/Taipei）
- Source：`C:\Users\icemo\Projects\tw-invest-suite\scripts\`
- Runtime：`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\`
- 範圍：新聞 freshness、Groove-only render、publish 等待、21:30 trigger、Scheduler 註冊、GUI 手動觸發與 source/runtime integrity。
- 狀態：程式修正與實測完成；nightly 的 2026-10-07 上游行情仍未落地，屬獨立營運狀態，不以本修正偽造或越過 gate。

## Findings

### CRITICAL

- **[已修正] (`render_full_watchlist.py:1812,1997-2026`) 新聞專用刷新原本會走完整 renderer，可能覆寫 certified `public/watchlist.html` 與 `public/data/watchlist-full.json`。**
  - 修法：新增 `--groove-only`，只原子更新 `C:\Groove-Lab\watchlist.html`；certified artifacts 僅在完整 nightly 模式寫入。
  - 證據：2026-10-08 實測前後兩個 certified SHA256 完全不變，Groove HTML SHA256 改變。

- **[已修正] (`tw-pipeline-trigger-2130.bat:19`) `powershell.exe -Verb RunAs` 不是合法的 powershell.exe 參數，舊 launcher 無法可靠觸發 UAC。**
  - 修法：由外層 PowerShell 使用 `Start-Process -Verb RunAs -Wait -PassThru`，並傳回 elevated process exit code。

- **[已修正] (`trigger-2130-elevated.ps1:8-48`) 手工重建 Task XML 會遺失既有設定，且 action/description 特殊字元可能破壞 XML。**
  - 修法：使用 `ExportScheduledTask` 取得完整 XML，只改 CalendarTrigger 的 `StartBoundary`，再以 Task Scheduler COM `RegisterTask` 保留其餘欄位；S4U logon type 使用正確 COM 數值。

### MAJOR

- **[已修正] (`db_client.py:483`) DB 回傳欄位是 `url`，renderer 讀取 `link`，可能產生沒有可點連結的新聞。**
  - 修法：SQL 使用 `url AS link`；2026-10-08 抽查 201 筆匹配新聞，連結完整率 100%。

- **[已修正] (`render_full_watchlist.py:1052,1851-1879`) Groove 即時新聞曾綁定 OHLCV `data_date`；行情延遲時會排除已入庫的今日新聞。**
  - 修法：新增獨立 `TW_NEWS_DATE`。Groove-only 使用台北當日；完整 nightly 未設定該變數時仍使用 certified `TW_DATA_DATE`，保留可重現性。

- **[已修正] (`render_full_watchlist.py:1873-1889`) 每張卡片各自掃描新聞造成 24 次相同的大查詢。**
  - 修法：24 檔一次 bounded batch query，再將結果分派到卡片。

- **[已修正] (`render_full_watchlist.py:1076-1095`) FinMind fallback 原本可默默帶回過期 30 日新聞。**
  - 修法：fallback 僅接受目標日前五日，並明確標示 `FinMind fallback`；沒有資料時顯示缺資料註記。

- **[已修正] (`news_refresh_watchlist.py:40,125-156`) wrapper 的 blocking stdout read 無內部 timeout，renderer 卡住時只能等 Scheduler 強制終止。**
  - 修法：改用 `communicate(timeout=720)`；超時以 `taskkill /T /F` 清除完整 process tree，留下 failed status 與 log。

- **[已修正] (`news_refresh_watchlist.py:52-56`) status 原地寫入可能在中斷時留下半個 JSON。**
  - 修法：同目錄 temporary file + `os.replace` 原子換檔。

- **[已修正] (`register_news_refresh.ps1:13-20,23-34`) SelfCheck 原本被 elevation gate 擋住，且 `$env:USERNAME` 不一定是完整 Scheduler principal。**
  - 修法：SelfCheck 在 elevation gate 前執行；註冊使用 `WindowsIdentity.Name`；保留 8 triggers、Wake、StartWhenAvailable、IgnoreNew、15 分鐘上限。

- **[已修正] (`pipeline_state.py:53`) 新增 runtime script 未納入受管來源雜湊。**
  - 修法：`news_refresh_watchlist.py` 加入 `SOURCE_FILES`；目前 `source_hashes()` 共 70 筆。

- **[營運風險] 2026-10-08 的兩次完整 Groove-only render 均成功，但 24 檔中有 20 檔 supplemental fetch warning。**
  - 影響：canonical DB 新聞、選股與 HTML 生成成功；個別外部補充欄位可能降級。應在 GUI/log 顯示 warning count，不應把它解讀成 certified nightly 全面健康。

### MINOR

- **[已修正] (`publish_ghpages_daily.ps1:2-14`) 舊註解把 22:50 + 130 分鐘寫成 00:00。**
  - 修法：修正為 01:00 deadline。21:30 + 91.6 分鐘約 23:02；publisher 22:50 開始等待，正常會約 23:02 繼續，仍早於 01:00。

- **[已修正] (`TwPipelineMonitor.ps1:791-824`) GUI fallback 可重複啟動相同 Python。**
  - 修法：啟動前以 `Win32_Process.CommandLine` 檢查既有 `news_refresh_watchlist.py`；若存在則顯示人類可讀訊息並停止。

- **[已修正] (`TwPipelineMonitor.ps1:94,817`) GUI 說明與實際 3–8 分鐘耗時不一致，且「只本地」容易誤解 Groove live mirror。**
  - 修法：說明為更新 Groove 即時 watchlist、保留 certified artifacts、不推 GitHub Pages，並顯示 3–8 分鐘。

- **[既有產物] `git diff --check` 的 trailing whitespace 位於 generated HTML，不在本次 Python/PowerShell/BAT 程式修正。**
  - 修法：不要手改 generated HTML；若要清除，應修 generator 並由完整 certified pipeline 重建。

## 排程與狀態驗證

| 項目 | 2026-10-08 實測結果 |
|---|---|
| daily-report trigger | 已套用 21:30，Ready、Wake、StartWhenAvailable |
| news-refresh triggers | 08、10、12、14、16、18、20、22，共 8 個 |
| news-refresh S4U smoke | 從 Task Scheduler 啟動並完成；狀態 `ok` |
| news data identity | OHLCV `2026-10-06`；live news cutoff `2026-10-08` |
| DB 抽查 | 24 picks；23 檔有五日內 canonical news；201 筆匹配；所有 link 有值 |
| Groove output | 含 `2026-10-08`；無 FinMind fallback；無缺新聞註記 |
| Certified isolation | `public/watchlist.html` 與 `public/data/watchlist-full.json` SHA256 均未變 |
| Source/runtime | `db_client.py`、`render_full_watchlist.py`、`news_refresh_watchlist.py`、`pipeline_state.py`、`publish_ghpages_daily.ps1` 對齊 |
| PowerShell | 4 個相關 `.ps1` parse error 為 0，且皆有 UTF-8 BOM |
| BAT | 3 個 launcher 均為 ASCII、無 BOM |

## SHA256 證據


| 檔案 | SHA256 |
|---|---|
| `db_client.py` | `831FAB32F63BD9173D2A838FFA43248188EFB85A53CA5B051D76DF06FE022ECC` |
| `render_full_watchlist.py` | `F51F978D7380FB4A0544EBDC08003B3E940BAA7343210C011B179E23A154D131` |
| `news_refresh_watchlist.py` | `2406F9DAA052516D72D076361D001A4DD84B41E109F8C156F9AD1D40F1EA8891` |
| `register_news_refresh.ps1` | `715167CEE8C670225000A9FFF9121DD84C3DCF15665B675F4C28D9C93D30BB42` |
| `publish_ghpages_daily.ps1` | `71C08867D3BE63EFDBD418A41B9755AA9743243DD6C8D049E1FD8BE8B6D21402` |
| `pipeline_state.py` | `100258BEDA85E3BBBF6556D52C7E71DF3CBFE94896BB96922A3FD07E2EF1A10C` |
| `TwPipelineMonitor.ps1` | `CE4201CBE31C71B36F19D9AC8559972977DF67AD086CDF43F6A1EFD918BFB8B3` |
| `trigger-2130-elevated.ps1` | `C4DD52BBA93380E0A649A2F241AB3E015771E87CC40E0268E332A5D5E341290D` |
| `tw-pipeline-trigger-2130.bat` | `2304BC895BFF3A1BB5C492FBE32AE885B98FC8376D36F97C43BFCC6019C66D92` |
| `register_news_refresh.bat` | `113449FF2FB9D900D0BDABDC8B06E8A521965531B40AC42D41B2EC2C5CD228A2` |


## 驗證清單

- [x] Python source/runtime `py_compile` 通過。
- [x] `pipeline_state.source_hashes()` 可計算 70 個受管來源。
- [x] 核心 source/runtime SHA256 一致。
- [x] `db_client.news_for_tickers()` 使用半開區間，publication 與 crawl cutoff 都受目標日限制。
- [x] DB 欄位 `url AS link`，實際新聞連結完整。
- [x] Groove-only 以 `TW_NEWS_DATE=2026-10-08` 取即時新聞。
- [x] Full nightly 未設定 `TW_NEWS_DATE` 時仍以 certified data date 渲染。
- [x] FinMind fallback 僅限五日內並明示來源。
- [x] 24 檔 canonical news 使用一次 batch query。
- [x] wrapper 具 12 分鐘 timeout、process-tree cleanup、atomic status。
- [x] Scheduler 具 8 個 trigger、15 分鐘上限、Wake、StartWhenAvailable、IgnoreNew。
- [x] S4U 任務由 Task Scheduler 真實啟動並成功完成。
- [x] GUI fallback 有 duplicate-process guard，且不阻塞 UI thread。
- [x] 21:30 trigger helper 保留原 Task XML 的 action/principal/settings。
- [x] 22:50 publisher + 130 分鐘的絕對 deadline 為 01:00；正常 nightly 約 23:02 完成。
- [x] Groove HTML 實際更新，certified HTML/JSON SHA256 不變。
- [ ] 2026-10-07 canonical OHLCV/provider 尚未落地；下一次 nightly 必須繼續 fail closed，不能用新聞日期冒充交易資料日。
- [ ] 觀察下一次 21:30 full nightly 與 22:50 publish 的真實 end-to-end receipt；目前上一輪因 upstream stale 而失敗。
- [ ] 將 `fetch_errors=20` 以「補充資料降級」呈現在 GUI，避免只顯示整體成功。

## 風險與維護規則

1. `TW_NEWS_DATE` 只供 Groove 即時頁使用；full nightly 的 certified reports 必須保持 `TW_DATA_DATE`。
2. 不得讓 news-refresh 寫入 `public/watchlist.html` 或 `public/data/watchlist-full.json`。
3. 不得因新聞新鮮就宣告 OHLCV、chips、模型或 certified release 新鮮。
4. Scheduler 的成功必須由 status timestamp、log、輸出 SHA 與產物內容共同確認。
5. daily-report 與 publish 的上一輪仍是 upstream stale；需等 provider 落地後由正常自動鏈恢復。

## 修正版本

以下為所有需要修正檔案在 2026-10-08 驗證完成後的完整內容。可直接逐檔比對或覆蓋；覆蓋 source 後，受管 runtime 檔案必須再做 SHA256 對齊。


### db_client.py

來源：`C:\Users\icemo\Projects\tw-invest-suite\scripts\db_client.py`

```python
"""
MySQL data layer for tw-invest-suite.

Reuses existing tables in the user's `tw_elec` database:
- `daily_data2_full`        — daily OHLCV + institutional + margin + technicals (primary)
- `industry_type`           — ticker → industry mapping
- `chipscore_daily`         — chip-derived signals (Inv_FirstIn, VolumeBurst, etc.)
- `stock_features`          — return features (ret_1d … ret_240d, foreign_net_ratio, etc.)
- `stock_news`              — news with sentiment_score, related_tickers
- `topn_daily`              — daily TopN picks with reason

Goal: never call an external API if DB has the data. Fallback to FinMind/TWSE
only when DB is stale or the dataset is missing.
"""
import os
import math
import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, List, Optional, Tuple

import pymysql
import pymysql.cursors


DB_CONFIG = {
    "host": os.environ.get("TW_DB_HOST", "localhost"),
    "user": os.environ.get("TW_DB_USER", "root"),
    "database": os.environ.get("TW_DB_NAME", "tw_elec"),
    "charset": "utf8mb4",
}


def get_db_config(**overrides):
    """Return a connection config without embedding a credential in source."""
    password = os.environ.get("TW_DB_PASSWORD", "").strip()
    if not password:
        # S4U scheduler tasks do not inherit the interactive process environment.
        # Fall back to the user-scoped environment variable already configured in
        # HKCU\Environment so the credential stays out of source.
        if os.name == "nt":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    value, _ = winreg.QueryValueEx(key, "TW_DB_PASSWORD")
                if value:
                    os.environ["TW_DB_PASSWORD"] = str(value)
                    password = str(value).strip()
            except (OSError, ImportError):
                pass
    if not password:
        raise RuntimeError(
            "TW_DB_PASSWORD is required; set it in the protected runtime environment"
        )
    config = {**DB_CONFIG, "password": password}
    config.update(overrides)
    return config


def connect(**overrides):
    """Open a MySQL connection using the protected runtime configuration."""
    return pymysql.connect(**get_db_config(**overrides))


@contextmanager
def get_conn():
    conn = connect(cursorclass=pymysql.cursors.DictCursor)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor():
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------- date helpers ----------

_REPORT_DATE = ContextVar("tw_report_date", default=None)


def query_date():
    return _REPORT_DATE.get() or os.environ.get("TW_DATA_DATE") or None


@contextmanager
def report_date(target_date):
    """Bound all report history queries without leaking dates between threads."""
    from datetime import date
    target_date = str(target_date)[:10] if target_date else None
    if target_date:
        date.fromisoformat(target_date)
    token = _REPORT_DATE.set(target_date)
    try:
        yield
    finally:
        _REPORT_DATE.reset(token)

def latest_date(table: str = "daily_data2_full") -> str:
    """Return the most recent date in the given table (str YYYY-MM-DD)."""
    with get_cursor() as cur:
        cur.execute(f"SELECT MAX(Date) AS d FROM {table}")
        row = cur.fetchone()
    return str(row["d"]) if row and row["d"] else ""


def is_stale(table: str = "daily_data2_full", max_age_days: int = 3) -> bool:
    """True if the latest date in the table is more than `max_age_days` old."""
    from datetime import datetime, timedelta
    ld = latest_date(table)
    if not ld:
        return True
    latest = datetime.strptime(ld, "%Y-%m-%d").date()
    return (datetime.now().date() - latest) > timedelta(days=max_age_days)


# ---------- core screener queries ----------

def market_snapshot(target_date: Optional[str] = None) -> List[Dict]:
    """Latest snapshot of every ticker in daily_data2_full.

    Returns one row per ticker with OHLCV, institutional net, margin, technicals.
    """
    if not target_date:
        target_date = latest_date("daily_data2_full")
    sql = f"""
        SELECT
            Ticker, Date, Open, High, Low, Close, change_pct, Volume,
            ForeignNet, InvestmentNet, DealerNet, ThreeNet,
            MarginBalance, ShortBalance,
            ForeignRatio, SharesOutstanding_shares,
            sma_13, sma_27, sma_54, atr_14, rsi_14, is_gap
        FROM daily_data2_full
        WHERE Date = %s
          AND Close > 0
          AND Ticker REGEXP '^[0-9]{{4}}$|^[0-9]{{4}}[A-Z]$'
        ORDER BY Ticker
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date,))
        return cur.fetchall()


def ticker_history(ticker: str, days: int = 240, as_of: Optional[str] = None) -> List[Dict]:
    """Last `days` trading days of OHLCV for one ticker (asc by date)."""
    sql = """
        SELECT Date, Open, High, Low, Close, Volume,
               ForeignNet, InvestmentNet, DealerNet, ThreeNet,
               MarginBalance, ShortBalance,
               sma_13, sma_27, sma_54, rsi_14, atr_14
        FROM daily_data2_full
        WHERE Ticker = %s AND (%s IS NULL OR Date <= %s)
        ORDER BY Date DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cutoff = as_of or query_date()
        cur.execute(sql, (ticker, cutoff, cutoff, days))
        rows = cur.fetchall()
    return list(reversed(rows))  # ascending by date


def market_cap_estimate(ticker: str) -> Optional[float]:
    """Estimate market cap from shares_master × latest close price.

    Returns None if shares or price not available.
    """
    sql_shares = "SELECT shares_outstanding FROM shares_master WHERE ticker = %s"
    sql_price = "SELECT Close FROM daily_data2_full WHERE Ticker = %s ORDER BY Date DESC LIMIT 1"
    with get_cursor() as cur:
        cur.execute(sql_shares, (ticker,))
        r = cur.fetchone()
        if not r or not r.get("shares_outstanding"):
            return None
        shares = float(r["shares_outstanding"])
        cur.execute(sql_price, (ticker,))
        pr = cur.fetchone()
        if not pr or not pr.get("Close"):
            return None
        price = float(pr["Close"])
    return shares * price


def ticker_features(ticker: str, latest_n: int = 1) -> List[Dict]:
    """Return `latest_n` rows of stock_features for the ticker (most recent)."""
    sql = """
        SELECT * FROM stock_features
        WHERE ticker = %s
        ORDER BY date DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, latest_n))
        return cur.fetchall()


def chip_features(ticker: str, latest_n: int = 5) -> List[Dict]:
    """Recent chip-derived signals from chipscore_daily."""
    sql = """
        SELECT * FROM chipscore_daily
        WHERE Ticker = %s
        ORDER BY Date DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, latest_n))
        return cur.fetchall()


def industry_for(ticker: str) -> str:
    """Look up industry classification. Empty string if not found."""
    with get_cursor() as cur:
        cur.execute("SELECT industry FROM industry_type WHERE ticker = %s LIMIT 1", (ticker,))
        row = cur.fetchone()
    return row["industry"] if row else ""


def all_industries() -> Dict[str, Dict[str, str]]:
    """ticker → {industry, company} (full table)."""
    with get_cursor() as cur:
        cur.execute("SELECT ticker, industry, company FROM industry_type")
        return {r["ticker"]: {"industry": r["industry"], "company": r["company"]} for r in cur.fetchall()}


def close_on_or_before(ticker: str, cutoff_date: str) -> Optional[float]:
    """Most recent close for a ticker on or before cutoff_date. For long-term return calc."""
    sql = """
        SELECT Close FROM daily_data2_full
        WHERE Ticker = %s AND Date <= %s AND Close > 0
        ORDER BY Date DESC LIMIT 1
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, cutoff_date))
        row = cur.fetchone()
    return float(row["Close"]) if row and row.get("Close") else None


def long_term_returns_batch(tickers: List[str], target_date: str) -> Dict[str, Dict[str, float]]:
    """Compute returns against prior ~20/60/120/240/500 calendar-day dates.

    Each endpoint is the latest valid close on/before its date cutoff.
    One current query and five historical queries, each batching all tickers.
    """
    if not tickers:
        return {}
    from datetime import datetime, timedelta
    end = datetime.strptime(target_date, "%Y-%m-%d")
    cutoffs = {
        "ret_20d": (end - timedelta(days=20)).strftime("%Y-%m-%d"),
        "ret_60d": (end - timedelta(days=60)).strftime("%Y-%m-%d"),
        "ret_120d": (end - timedelta(days=120)).strftime("%Y-%m-%d"),
        "ret_240d": (end - timedelta(days=240)).strftime("%Y-%m-%d"),
        "ret_500d": (end - timedelta(days=500)).strftime("%Y-%m-%d"),
    }
    out: Dict[str, Dict[str, float]] = {t: {} for t in tickers}
    # Get current close for all tickers in one query
    placeholders = ",".join(["%s"] * len(tickers))
    sql = f"""
        SELECT Ticker, Close FROM daily_data2_full
        WHERE Ticker IN ({placeholders}) AND Date = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (*tickers, target_date))
        cur_close = {r["Ticker"]: float(r["Close"]) for r in cur.fetchall() if r.get("Close")}
    # For each cutoff, query the historical close
    for label, cutoff in cutoffs.items():
        universe = " UNION ALL ".join(["SELECT %s AS Ticker"] + ["SELECT %s"] * (len(tickers) - 1))
        sql = f"""
            SELECT u.Ticker, p.Close FROM ({universe}) u
            LEFT JOIN daily_data2_full p ON p.Ticker = u.Ticker AND p.Date = (
                SELECT p2.Date FROM daily_data2_full p2
                WHERE p2.Ticker = u.Ticker AND p2.Date <= %s AND p2.Close > 0
                ORDER BY p2.Date DESC LIMIT 1
            )
        """
        with get_cursor() as cur:
            cur.execute(sql, (*tickers, cutoff))
            prior = {r["Ticker"]: float(r["Close"]) for r in cur.fetchall() if r.get("Close")}
        for t in tickers:
            if t in cur_close and t in prior and prior[t] > 0:
                out[t][label] = (cur_close[t] - prior[t]) / prior[t]
    return out


# Compatibility keys ret_*d / excess_return_*d in existing reports and DB
# mean calendar-day raw PRICE return, never total or benchmark excess return.
RETURN_DEFINITION = "calendar_day_raw_price_return_v1"


def signal_flags(rows: List[Dict], target_date: str) -> Dict:
    """2x prior-20 volume; KD(9, 1/3, 1/3), seeded 50 on bounded 60 sessions.

    Unknown/invalid observations reset KD rather than silently bridging gaps.
    """
    rows = sorted((r for r in rows if str(r['Date'])[:10] <= target_date), key=lambda r: r['Date'])[-60:]
    result = {"VolumeBurst": None, "KD_GoldenCross": None}
    if not rows or str(rows[-1]['Date'])[:10] != target_date:
        return result
    def number(value):
        try:
            value = float(value)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None
    volumes = [number(r.get('Volume')) for r in rows[-21:]]
    if len(volumes) == 21 and all(v is not None and v >= 0 for v in volumes) and sum(volumes[:-1]) > 0:
        result['VolumeBurst'] = int(volumes[-1] >= 2 * sum(volumes[:-1]) / 20)
    window, previous, k, d = [], None, 50.0, 50.0
    for row in rows:
        h, l, c = (number(row.get(key)) for key in ('High', 'Low', 'Close'))
        result['KD_GoldenCross'] = None
        if None in (h, l, c) or not (0 < l <= c <= h):
            window, previous, k, d = [], None, 50.0, 50.0
            continue
        window = (window + [(h, l)])[-9:]
        if len(window) < 9:
            continue
        high, low = max(v[0] for v in window), min(v[1] for v in window)
        if high == low:
            previous, k, d = None, 50.0, 50.0
            continue
        k = (2 * k + 100 * (c - low) / (high - low)) / 3
        d = (2 * d + k) / 3
        if previous is not None:
            result['KD_GoldenCross'] = int(previous[0] <= previous[1] and k > d)
        previous = (k, d)
    return result


def screen_signal_features(target_date: str) -> Dict[str, Dict]:
    """One bounded canonical history read; no API, future rows or per-stock SQL."""
    with get_cursor() as cur:
        cur.execute("SELECT DISTINCT Date FROM daily_data2_full WHERE Date <= %s ORDER BY Date DESC LIMIT 60", (target_date,))
        dates = [r['Date'] for r in cur.fetchall()]
        if not dates:
            return {}
        cur.execute("SELECT Ticker, Date, High, Low, Close, Volume FROM daily_data2_full WHERE Date BETWEEN %s AND %s ORDER BY Ticker, Date", (min(dates), target_date))
        grouped = {}
        for row in cur.fetchall():
            grouped.setdefault(row['Ticker'], []).append(row)
    return {ticker: signal_flags(rows, target_date) for ticker, rows in grouped.items()}


def refresh_chip_signals(cur, target_date: str) -> int:
    """Fill the existing derived columns; caller owns the write transaction."""
    flags = screen_signal_features(str(target_date)[:10])
    values = [(v['VolumeBurst'], v['KD_GoldenCross'], target_date, t) for t, v in flags.items()]
    if values:
        cur.executemany("UPDATE chipscore_daily SET VolumeBurst=%s, KD_GoldenCross=%s WHERE Date=%s AND Ticker=%s", values)
    return len(values)


def recent_news(ticker: str, limit: int = 5) -> List[Dict]:
    """Latest news mentioning the ticker. related_tickers is a JSON array string."""
    sql = """
        SELECT id, title, source, published_at, sentiment_score, summary
        FROM stock_news
        WHERE related_tickers LIKE %s
          AND (%s IS NULL OR published_at < DATE_ADD(%s, INTERVAL 1 DAY))
        ORDER BY published_at DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cutoff = query_date()
        cur.execute(sql, (f'%"{ticker}"%', cutoff, cutoff, limit))
        return cur.fetchall()


def shares_outstanding(ticker: str) -> Optional[int]:
    """Most recent SharesOutstanding_shares for a ticker. Try daily_data2_full,
    then shares_master (broader coverage)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT SharesOutstanding_shares FROM daily_data2_full
               WHERE Ticker = %s AND SharesOutstanding_shares IS NOT NULL
               ORDER BY Date DESC LIMIT 1""",
            (ticker,),
        )
        row = cur.fetchone()
        if row and row.get("SharesOutstanding_shares"):
            return int(row["SharesOutstanding_shares"])
        # Fallback to shares_master
        cur.execute(
            """SELECT SharesOutstanding_shares FROM shares_master
               WHERE Ticker = %s LIMIT 1""",
            (ticker,),
        )
        row = cur.fetchone()
    return int(row["SharesOutstanding_shares"]) if row and row.get("SharesOutstanding_shares") else None


def all_shares_outstanding() -> Dict[str, int]:
    """Bulk lookup ticker → shares outstanding (from shares_master)."""
    with get_cursor() as cur:
        cur.execute("SELECT Ticker, SharesOutstanding_shares FROM shares_master")
        return {r["Ticker"]: int(r["SharesOutstanding_shares"])
                for r in cur.fetchall() if r.get("SharesOutstanding_shares")}


# ---------- batch queries (for fast full-market scans) ----------

def all_latest_chipscore(target_date: Optional[str] = None) -> Dict[str, Dict]:
    """ticker → chip row (most recent date). One round-trip."""
    if not target_date:
        target_date = latest_date("chipscore_daily")
    sql = f"""
        SELECT * FROM chipscore_daily
        WHERE Date = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date,))
        return {r["Ticker"]: r for r in cur.fetchall()}


def all_latest_features(target_date: Optional[str] = None) -> Dict[str, Dict]:
    """ticker → feature row (most recent date). One round-trip."""
    if not target_date:
        # Find the latest date present in stock_features
        with get_cursor() as cur:
            cur.execute("SELECT MAX(date) AS d FROM stock_features")
            target_date = str(cur.fetchone()["d"])
    sql = """
        SELECT * FROM stock_features
        WHERE date = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date,))
        return {r["ticker"]: r for r in cur.fetchall()}


def assert_feature_freshness(target_date: str, tickers: List[str],
                             min_coverage: float = 0.95) -> Dict:
    """Fail closed when stock_features is absent or stale for the screen."""
    expected = sorted({str(t) for t in tickers if t})
    if not expected:
        raise RuntimeError("stock_features freshness gate: empty ticker universe")
    placeholders = ",".join(["%s"] * len(expected))
    sql = f"""
        SELECT COUNT(DISTINCT ticker) AS n, MAX(date) AS d,
               SUM(CASE WHEN volume_ratio_20d IS NOT NULL AND volume_ratio_20d >= 0 THEN 1 ELSE 0 END) AS valid_volume_ratio
        FROM stock_features
        WHERE date = %s AND ticker IN ({placeholders})
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date, *expected))
        row = cur.fetchone() or {}
    count = int(row.get("n") or 0)
    actual_date = str(row.get("d") or "")[:10]
    coverage = count / len(expected)
    if actual_date != str(target_date)[:10] or coverage < min_coverage:
        raise RuntimeError(
            "stock_features freshness gate failed: "
            f"date={actual_date or 'missing'} expected={target_date} "
            f"rows={count}/{len(expected)} coverage={coverage:.1%} "
            f"required={min_coverage:.1%}"
        )
    valid = int(row.get('valid_volume_ratio') or 0)
    if valid / len(expected) < min_coverage:
        raise RuntimeError(f"stock_features consumed-field gate failed: volume_ratio_20d={valid}/{len(expected)} date={target_date}")
    return {"date": actual_date, "rows": count, "consumed_fields": {"volume_ratio_20d": valid},
            "descriptive_only_fields": ["excess_return_20d"]}


def news_for_tickers(tickers: List[str], limit_per: int = 10, days: int = 5,
                     target_date: Optional[str] = None) -> Dict[str, List[Dict]]:
    """Batch news known by target-session end (publication AND crawl cutoff)."""
    from datetime import datetime, timedelta
    end = datetime.fromisoformat(target_date or query_date() or latest_date()) + timedelta(days=1)
    cutoff = end - timedelta(days=days)
    out: Dict[str, List[Dict]] = {t: [] for t in tickers}
    if not out:
        return out
    with get_cursor() as cur:
        cur.execute("""SELECT id, title, source, url AS link, published_at,
                              sentiment_score, summary, related_tickers
                       FROM stock_news WHERE published_at >= %s AND published_at < %s
                         AND crawled_at < %s
                       ORDER BY published_at DESC, id DESC LIMIT 50001""", (cutoff, end, end))
        rows = cur.fetchall()
    if len(rows) > 50000:
        raise RuntimeError('bounded news query exceeded 50000 rows; incomplete ranking refused')
    for row in rows:
        try:
            related = json.loads(row.get('related_tickers') or '[]')
        except (ValueError, TypeError):
            continue
        if not isinstance(related, list):
            continue
        for t in set(str(t) for t in related):
            if t in out and len(out[t]) < limit_per:
                out[t].append(row)
    return out


# ---------- quick smoke test ----------

if __name__ == "__main__":
    print(f"latest daily_data2_full date: {latest_date('daily_data2_full')}")
    print(f"latest daily_data2 date:     {latest_date('daily_data2')}")
    print(f"latest daily_data date:      {latest_date('daily_data')}")
    print(f"daily_data2_full stale?     {is_stale('daily_data2_full', 3)}")
    print(f"industry for 2330:           {industry_for('2330')}")
    snap = market_snapshot()
    print(f"snapshot rows:               {len(snap)}")
    if snap:
        print(f"sample row 2330:             {next((r for r in snap if r['Ticker'] == '2330'), None)}")
    print(f"2330 history (5d):")
    for r in ticker_history("2330", days=5):
        print(f"  {r['Date']} C={r['Close']} V={r['Volume']} FNet={r['ForeignNet']} Rsi={r['rsi_14']}")
```

### render_full_watchlist.py

來源：`C:\Users\icemo\Projects\tw-invest-suite\scripts\render_full_watchlist.py`

```python
"""
Render the full deep-dive watchlist for groovelab.dev/picks.html.

For each of the 24 picks (4 price buckets × 6 picks):
  - Company info (FinMind stock_info)
  - Price snapshot (TWSE / TPEx)
  - Technicals (MA5/20/60, RSI, trend)
  - Valuation (P/E, P/B, dividend yield)
  - Three-major institutional (近 10 日)
  - Margin / short balance
  - Monthly revenue (FinLab — free tier may be limited)
  - ROE (FinLab)
  - News (5 latest)
  - Dividend history
  - Hedge-fund master tags (from market_screen)
  - Zen (Chanlun) structural read
  - Perplexity deep-dive prompt (Tiger Global / Baupost)

Layout:
  - Top: 14-skill navigation bar
  - Tabs: 4 price buckets (default open: <100)
  - Inside each tab: pick cards in 3-col grid, expandable to deep-dive
  - Each card links out to:
      * ticker-dashboard (single-stock dashboard)
      * wall-street-tw-stock-analysis (華爾街風格分析)
      * ai-telegram-research-check (研究流程)

Output:
  - C:\\Users\\icemo\\.claude\\skills\\tw-invest-suite\\reports\\watchlist-full-YYYY-MM-DD.html
  - C:\\Groove-Lab\\watchlist.html  (live, served by groovelab tunnel)
"""
import html
import re as _re
import os
import sys
import json
import time
from bounded_deep_dive import fetch_tickers
from datetime import datetime, date, timedelta
from pathlib import Path
import pymysql

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_stock as a   # noqa: E402
import market_screen as ms  # noqa: E402
import deep_dive_prompts as ddp  # noqa: E402
import watchlist as wl  # noqa: E402
import db_client as db  # noqa: E402
import zen_analyzer as zen  # noqa: E402

REPORTS_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
GROOVE_WATCHLIST = Path(r"C:\Groove-Lab\watchlist.html")


SKILL_LINKS = [
    ("tw-invest-suite", "主控：個股深挖 + 市場掃描"),
    ("finlab", "台股量化交易（ROE／月營收）"),
    ("finmind", "台股／全球金融資料 API"),
    ("tw-stock-info", "即時報價／財報／技術（Fugle/FinMind）"),
    ("twse-api", "TWSE 官方 OpenAPI"),
    ("yahoo-finance", "Yahoo Finance 全球股票"),
    ("wall-street-tw-stock-analysis", "華爾街風格台股個股分析"),
    ("hedge-fund-expert-team", "18 位投資大師 + 6 位分析師"),
    ("stock-selection-decision", "選股決策工作流"),
    ("minerva", "Minerva 量化研究 workflow"),
    ("zen", "纏論技術分析"),
    ("ticker-dashboard", "AI-Telegram 個股儀表板"),
    ("ai-telegram-research-check", "台股 daily 研究流程"),
    ("ui-development", "AI-Telegram 總控 UI"),
]


CSS = """
:root { --bg:#0a0e1a; --panel:#131b2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --green:#58d68d; --red:#ec7063; --amber:#f5b041; --purple:#bc8cff; --cyan:#39c5cf; --border:#1f2942; }
* { box-sizing: border-box; }
body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; }
.topbar { position: sticky; top: 0; z-index: 100; background: rgba(10, 14, 26, 0.95); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); padding: 12px 20px; }
.brand { font-size: 1.2rem; font-weight: 600; color: var(--acc); }
.brand small { color: var(--muted); font-weight: 400; font-size: 0.7rem; margin-left: 8px; }
.skillbar { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; font-size: 0.72rem; }
.skillbar .sk { background: var(--panel); color: var(--muted); padding: 3px 8px; border-radius: 8px; border: 1px solid var(--border); }
.tabs { display: flex; gap: 4px; background: var(--panel); border-radius: 8px; padding: 4px; margin: 16px 20px 0; overflow-x: auto; }
.tab { background: transparent; color: var(--muted); border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.9rem; font-weight: 500; white-space: nowrap; transition: all 0.15s; }
.tab:hover { color: var(--ink); }
.tab.active { background: var(--acc); color: #000; }
.tab .count { background: rgba(0,0,0,0.2); padding: 1px 6px; border-radius: 8px; font-size: 0.7rem; margin-left: 4px; }
main { padding: 20px; max-width: 1400px; margin: 0 auto; }
.tab-content { display: none; }
.tab-content.active { display: block; }
.bucket-title { font-size: 1.1rem; color: var(--acc); margin: 0 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.bucket-title small { color: var(--muted); font-weight: 400; font-size: 0.85rem; }
.pick-chips { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0 6px; }
.chip { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; font-family: 'Consolas', monospace; border: 1px solid; }
.chip-pos { background: rgba(236,112,99,0.15); color: #ec7063; border-color: rgba(236,112,99,0.3); }
.chip-neu { background: rgba(245,176,65,0.15); color: #f5b041; border-color: rgba(245,176,65,0.3); }
.chip-neg { background: rgba(88,214,141,0.12); color: #58d68d; border-color: rgba(88,214,141,0.3); }
.pick-score { margin-left: auto; }
.summary-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 20px; }
.card { background: var(--panel); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border); }
.card .k { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
.card .v { font-size: 1.3rem; font-weight: 600; margin-top: 4px; }
.picks { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }
.pick { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.pick-head { padding: 14px 16px; background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
.pick-head.long { border-left: 3px solid var(--green); }
.pick-head.short { border-left: 3px solid var(--amber); }
.pick-ticker { font-size: 1.1rem; font-weight: 700; color: var(--acc); }
.pick-name { color: var(--ink); font-weight: 500; }
.pick-price { font-size: 1.3rem; font-weight: 700; }
.pick-price.up { color: var(--red); }
.pick-price.down { color: var(--green); }
.pick-horizon { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: 500; }
.pick-horizon.long { background: rgba(236,112,99,0.18); color: var(--red); }
.pick-horizon.short { background: rgba(245,176,65,0.18); color: var(--amber); }
.pick-body { padding: 12px 16px; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.tag { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 0.72rem; background: var(--border); color: var(--ink); }
.tag-green { background: rgba(63,185,80,0.18); color: var(--green); }
.tag-red { background: rgba(236,112,99,0.18); color: var(--red); }
.tag-yellow { background: rgba(245,176,65,0.18); color: var(--amber); }
.tag-blue { background: rgba(95,177,255,0.18); color: var(--acc); }
.tag-cyan { background: rgba(57,197,207,0.18); color: var(--cyan); }
.tag-purple { background: rgba(188,140,255,0.18); color: var(--purple); }
.tabs2 { display: flex; gap: 2px; background: rgba(0,0,0,0.2); border-radius: 6px; padding: 2px; margin: 8px 0; }
.tabs2 button { background: transparent; color: var(--muted); border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 0.78rem; }
.tabs2 button.active { background: var(--acc); color: #000; }
.section { display: none; padding: 8px 0; font-size: 0.9rem; line-height: 1.6; }
.section.active { display: block; }
.section h5 { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; margin: 10px 0 6px; letter-spacing: 0.6px; font-weight: 600; }
.section table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.85rem; margin: 4px 0 10px; background: rgba(0,0,0,0.15); border-radius: 6px; overflow: hidden; }
.section th, .section td { padding: 8px 10px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.05); }
.section th { color: var(--muted); font-weight: 600; background: rgba(255,255,255,0.03); text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.4px; }
.section td:first-child, .section th:first-child { text-align: left; }
.section tr:last-child td { border-bottom: none; }
.section tr:hover td { background: rgba(95,177,255,0.06); }
.section td.num { font-variant-numeric: tabular-nums; font-weight: 500; }
.section td.pos { color: var(--red); font-weight: 600; }
.section td.neg { color: var(--green); font-weight: 600; }
.section td.muted { color: var(--muted); }
.section .callout { background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border: 1px solid rgba(95,177,255,0.3); border-radius: 8px; padding: 10px 12px; margin: 8px 0; font-size: 0.85rem; line-height: 1.7; }
.section .callout .k { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.4px; margin-right: 4px; }
.section .callout .v { font-weight: 600; color: var(--ink); }
.section .callout .v.pos { color: var(--red); }
.section .callout .v.neg { color: var(--green); }
.section .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 6px 0 10px; }
.section .stat { background: rgba(255,255,255,0.04); border-radius: 6px; padding: 8px 10px; }
.section .stat .k { color: var(--muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.4px; }
.section .stat .v { font-size: 0.95rem; font-weight: 700; margin-top: 2px; }
.section .stat .v.pos { color: var(--red); }
.section .stat .v.neg { color: var(--green); }
.section .summary-line { padding: 6px 0; border-top: 1px solid rgba(255,255,255,0.06); margin-top: 8px; font-size: 0.85rem; }
.zen-box { background: rgba(188,140,255,0.06); border: 1px solid var(--purple); border-radius: 6px; padding: 8px 10px; margin: 6px 0; font-size: 0.82rem; }
.zen-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; margin-top: 4px; }
.zen-cell { background: rgba(0,0,0,0.2); padding: 4px 6px; border-radius: 4px; }
.zen-cell-label { font-size: 0.7rem; color: var(--muted); }
.zen-cell-value { font-size: 0.85rem; font-weight: 600; }
.zen-bullish { color: var(--red); }
.zen-bearish { color: var(--green); }
.zen-neutral { color: var(--muted); }
.news-item { padding: 4px 0; border-bottom: 1px dashed rgba(255,255,255,0.06); font-size: 0.8rem; }
.news-item:last-child { border-bottom: none; }
.news-item a { color: var(--acc); text-decoration: none; }
.dd-prompt { background: rgba(57,197,207,0.06); border: 1px solid var(--cyan); border-radius: 6px; padding: 8px; margin-top: 6px; }
.dd-prompt pre { font-size: 0.72rem; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; max-height: 280px; overflow-y: auto; margin: 0; }
.copy-btn { background: var(--cyan); color: #000; border: none; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 0.72rem; font-weight: 600; margin-bottom: 4px; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.actions a { color: var(--acc); font-size: 0.72rem; padding: 2px 8px; border: 1px solid var(--border); border-radius: 4px; text-decoration: none; }
.obs { color: var(--ink); font-size: 0.82rem; }
.obs li { padding: 2px 0; }
footer { padding: 24px; color: var(--muted); font-size: 0.8rem; text-align: center; }
.ret-up { color: var(--red); }
.ret-down { color: var(--green); }
.muted { color: var(--muted); }
@media (max-width: 700px) {
  .picks { grid-template-columns: 1fr; }
  .zen-grid { grid-template-columns: 1fr; }
  .summary-bar { grid-template-columns: repeat(2, 1fr); }
}
"""


# ---- helpers ----

def _esc(s) -> str:
    return html.escape(str(s)) if s else ""


def render_md_table(md: str) -> str:
    """Convert a markdown pipe table to a styled HTML table.
    Handles: | col1 | col2 |\n|---|---|...\n| v1 | v2 |...
    Cells with **text** become bold; +N/-N get pos/neg classes;
    first column is left-aligned, rest are right-aligned (numeric).
    """
    if not md or "|" not in md:
        return md
    lines = [l for l in md.split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return md
    # Detect separator row (|---|)
    sep_idx = None
    for i, l in enumerate(lines):
        if _re.match(r"^\|[\s\-:|]+\|?\s*$", l):
            sep_idx = i
            break
    if sep_idx is None:
        return md
    header_cells = [c.strip() for c in lines[sep_idx - 1].strip("|").split("|")]
    body_rows = []
    for l in lines[sep_idx + 1:]:
        cells = [c.strip() for c in l.strip("|").split("|")]
        if len(cells) != len(header_cells):
            cells = (cells + [""] * len(header_cells))[:len(header_cells)]
        body_rows.append(cells)

    def cell_html(raw: str, is_first: bool) -> str:
        # parse number
        s = raw
        # strip bold markers
        is_bold = s.startswith("**") and s.endswith("**") and len(s) > 4
        if is_bold: s = s[2:-2]
        # detect numeric for sign + class
        sign_cls = ""
        s_clean = s.strip()
        m = _re.match(r"^([+\-]?)([\d.,]+)(%?)$", s_clean)
        if m and not is_first:
            try:
                sign = m.group(1) or ""
                val = float((sign + m.group(2)).replace(",", ""))
                if val > 0: sign_cls = "pos"
                elif val < 0: sign_cls = "neg"
            except: pass
        # escape
        s_esc = _esc(s)
        # restore bold
        if is_bold: s_esc = f"<strong>{s_esc}</strong>"
        # decimal alignment: tabular-nums via .num class
        cls_parts = []
        if not is_first: cls_parts.append("num")
        if sign_cls: cls_parts.append(sign_cls)
        cls_attr = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
        return f"<td{cls_attr}>{s_esc}</td>"

    out = ['<table>']
    out.append('<thead><tr>' + "".join(f"<th>{_esc(h)}</th>" for h in header_cells) + '</tr></thead>')
    out.append('<tbody>')
    for row in body_rows:
        out.append('<tr>' + "".join(cell_html(c, i == 0) for i, c in enumerate(row)) + '</tr>')
    out.append('</tbody></table>')
    return "\n".join(out)


def beautify_section_html(html_str: str) -> str:
    """Post-process a section's HTML: convert markdown tables to HTML tables,
    and wrap 'summary' lines that start with '- ' after a table into a callout.
    """
    if not html_str: return html_str
    # Find markdown table block: contiguous lines starting with |
    out = []
    lines = html_str.split("\n")
    i = 0
    while i < len(lines):
        l = lines[i]
        # detect start of a markdown table (line starts with | and next line is |---|)
        if l.lstrip().startswith("|") and i + 1 < len(lines) and _re.match(r"^\s*\|[\s\-:|]+\|?\s*$", lines[i + 1]):
            # collect table block
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(render_md_table("\n".join(block)))
        else:
            out.append(l)
            i += 1
    return "\n".join(out)


def _fmt_pct(v):
    if v is None: return "—"
    try:
        return f"{float(v)*100:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_price(v):
    if v is None: return "—"
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(v):
    if v is None: return "—"
    try:
        return f"{int(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _signed(v, dec=0):
    if v is None: return "—"
    try:
        f = float(v)
        s = f"{abs(f):,.{dec}f}"
        return f"+{s}" if f > 0 else (f"-{s}" if f < 0 else s)
    except (TypeError, ValueError):
        return "—"


def _zen_class(bias: str) -> str:
    if not bias: return "zen-neutral"
    if "bull" in bias.lower() or "多" in bias: return "zen-bullish"
    if "bear" in bias.lower() or "空" in bias: return "zen-bearish"
    return "zen-neutral"


# ---- SVG chart helpers ----

def _svg_bar_chart(rows: list, value_keys: list, width: int = 480, height: int = 200,
                    labels: list = None, colors: list = None, title: str = "") -> str:
    """Clustered bar chart for time series. rows = [{date, k1, k2, ...}].
    Each bar group per row, multiple series side by side.
    """
    if not rows: return '<div class="muted">_無資料_</div>'
    if not colors: colors = ["#5fb1ff", "#58d68d", "#f5b041", "#bc8cff"]
    if not labels: labels = value_keys

    n = len(rows)
    n_series = len(value_keys)
    pad_l, pad_r, pad_t, pad_b = 40, 12, 18, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    group_w = plot_w / n
    bar_w = group_w / (n_series + 1)  # +1 for spacing

    # find max abs value for y scale
    max_abs = 1.0
    for r in rows:
        for k in value_keys:
            v = r.get(k) or 0
            max_abs = max(max_abs, abs(v))
    # round up to nice number
    import math
    ymax = math.ceil(max_abs / 1000) * 1000
    ymin = -ymax

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # zero line
    y0 = pad_t + plot_h * (ymax / (ymax - ymin))
    parts.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{width-pad_r}" y2="{y0:.1f}" stroke="#3a4a6a" stroke-width="0.5" stroke-dasharray="2,2"/>')

    # y-axis labels (3 levels: +max, 0, -max)
    for v, lab in [(ymax, f"+{ymax:,.0f}"), (0, "0"), (-ymax, f"-{ymax:,.0f}")]:
        y = pad_t + plot_h * ((ymax - v) / (ymax - ymin))
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="9">{lab}</text>')
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')

    # bars
    for i, r in enumerate(rows):
        gx = pad_l + i * group_w + bar_w / 2
        for s_i, k in enumerate(value_keys):
            v = r.get(k) or 0
            if v == 0: continue
            color = colors[s_i % len(colors)]
            bar_x = gx + s_i * bar_w
            # map value to height
            h = abs(v) / ymax * (plot_h / 2)
            if v >= 0:
                y = y0 - h
                rect_h = h
            else:
                y = y0
                rect_h = h
            parts.append(f'<rect x="{bar_x:.1f}" y="{y:.1f}" width="{bar_w*0.92:.1f}" height="{max(rect_h, 1):.1f}" '
                         f'fill="{color}" opacity="0.85" rx="1">'
                         f'<title>{_esc(labels[s_i])} {_esc(str(r.get("date", "")))}: {v:+,.0f}</title></rect>')
        # x-axis date label
        d = r.get("date", "")
        if hasattr(d, "strftime"):
            d_short = d.strftime("%m-%d")
        else:
            d = str(d)
            if " " in d: d = d.split(" ")[0]
            d_short = d[5:] if len(d) >= 10 else d
        parts.append(f'<text x="{gx + (n_series*bar_w)/2:.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{d_short}</text>')

    # legend
    legend_y = height - 4
    leg_x = pad_l
    for s_i, lab in enumerate(labels):
        color = colors[s_i % len(colors)]
        parts.append(f'<rect x="{leg_x}" y="{legend_y-7}" width="8" height="8" fill="{color}" opacity="0.85" rx="1"/>')
        parts.append(f'<text x="{leg_x+11}" y="{legend_y}" fill="#8aa0c0" font-size="8">{_esc(lab)}</text>')
        leg_x += 12 + len(lab) * 5 + 8

    parts.append('</svg>')
    return "".join(parts)


def _svg_line_chart(series: dict, width: int = 480, height: int = 200,
                     dates: list = None, title: str = "", y_label: str = "價格", n_total: int = None) -> str:
    """Multi-series line chart. series = {name: [(x_idx, value), ...]}.
    n_total: total x-axis points (defaults to max len of series).
    """
    if not series: return '<div class="muted">_無資料_</div>'

    n = n_total or max(len(v) for v in series.values())
    if n == 0: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 12, 18, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # collect all values for y scale (排除 None 與 <=0 的假性缺值)
    all_vals = []
    for vals in series.values():
        for _, v in vals:
            if v is not None and isinstance(v, (int, float)) and v > 0:
                all_vals.append(v)
    if not all_vals: return '<div class="muted">_無資料_</div>'

    ymin = min(all_vals)
    ymax = max(all_vals)
    yrange = ymax - ymin if ymax > ymin else 1
    # add 5% padding
    ymin -= yrange * 0.05
    ymax += yrange * 0.05
    yrange = ymax - ymin

    colors = {"收盤": "#5fb1ff", "MA5": "#f5b041", "MA13": "#58d68d", "MA27": "#bc8cff", "MA54": "#ec7063", "RSI(14)": "#39c5cf"}
    palette = ["#5fb1ff", "#f5b041", "#58d68d", "#bc8cff", "#ec7063", "#39c5cf", "#8b949e"]

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    def x_pos(i):
        return pad_l + (i / max(1, n - 1)) * plot_w

    def y_pos(v):
        return pad_t + (1 - (v - ymin) / yrange) * plot_h

    # y grid + labels (5 ticks)
    for t in range(6):
        v = ymin + yrange * t / 5
        y = y_pos(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.0f}</text>')

    # x labels (dates)
    if dates and len(dates) == n:
        idxs = [0, n // 4, n // 2, 3 * n // 4, n - 1]
        for i in idxs:
            d = dates[i]
            if hasattr(d, "strftime"):
                d_short = d.strftime("%m-%d")
            elif isinstance(d, str) and len(d) >= 10:
                d_short = d[5:]  # MM-DD
            else:
                d_short = str(d)
            parts.append(f'<text x="{x_pos(i):.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{d_short}</text>')

    # plot each series (None 與 <=0 一律跳過，避免假性暴跌到 0)
    for s_i, (name, vals) in enumerate(series.items()):
        color = colors.get(name, palette[s_i % len(palette)])
        pts = []
        for i, (x_i, v) in enumerate(vals):
            if v is None: continue
            if isinstance(v, (int, float)) and v <= 0: continue
            pts.append(f"{x_pos(i):.1f},{y_pos(v):.1f}")
        if not pts: continue
        # path
        path_d = "M " + " L ".join(pts)
        parts.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/>')
        # dots (last valid point only)
        if vals:
            last = [v for v in vals if v[1] is not None and (not isinstance(v[1], (int, float)) or v[1] > 0)]
            if last:
                i, v = last[-1]
                parts.append(f'<circle cx="{x_pos(i):.1f}" cy="{y_pos(v):.1f}" r="2.5" fill="{color}">'
                             f'<title>{name} 最新: {v:.2f}</title></circle>')

    # legend
    legend_y = height - 4
    leg_x = pad_l
    for s_i, name in enumerate(series.keys()):
        color = colors.get(name, palette[s_i % len(palette)])
        parts.append(f'<rect x="{leg_x}" y="{legend_y-7}" width="8" height="8" fill="{color}" rx="1"/>')
        parts.append(f'<text x="{leg_x+11}" y="{legend_y}" fill="#8aa0c0" font-size="8">{_esc(name)}</text>')
        leg_x += 12 + len(name) * 5 + 8

    parts.append('</svg>')
    return "".join(parts)


def _compute_rsi(closes: list, period: int = 14) -> list:
    """Return RSI values list (same length as closes, first period-1 are None)."""
    rsi = [None] * len(closes)
    if len(closes) < period + 1: return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    rs = avg_g / avg_l if avg_l else 100
    rsi[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = max(diff, 0)
        l = max(-diff, 0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        rs = avg_g / avg_l if avg_l else 100
        rsi[i] = 100 - (100 / (1 + rs))
    return rsi


def _svg_candlestick(ohlc: list, width: int = 520, height: int = 220,
                     dates: list = None, title: str = "",
                     zen_overlay: dict = None) -> str:
    """Candlestick chart. ohlc = [{date, open, high, low, close}, ...].
    zen_overlay = {center_low, center_high, center_start_date, center_end_date} optional.
    """
    if not ohlc or len(ohlc) < 5: return '<div class="muted">_K 線資料不足_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 12, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(ohlc)

    highs = [float(r.get("high") or 0) for r in ohlc]
    lows = [float(r.get("low") or 0) for r in ohlc]
    ymax = max(highs)
    ymin = min(lows)
    yrange = ymax - ymin if ymax > ymin else 1
    ymin -= yrange * 0.03
    ymax += yrange * 0.03
    yrange = ymax - ymin

    def x_pos(i): return pad_l + (i / max(1, n - 1)) * plot_w
    def y_pos(v): return pad_t + (1 - (v - ymin) / yrange) * plot_h

    candle_w = max(2, plot_w / n * 0.65)

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # y grid
    for t in range(6):
        v = ymin + yrange * t / 5
        y = y_pos(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.1f}</text>')

    # x labels (5 ticks)
    for i in [0, n // 4, n // 2, 3 * n // 4, n - 1]:
        d = ohlc[i].get("date", "")
        if hasattr(d, "strftime"): d_short = d.strftime("%m-%d")
        elif isinstance(d, str) and len(d) >= 10: d_short = d[5:]
        else: d_short = str(d)
        parts.append(f'<text x="{x_pos(i):.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{d_short}</text>')

    # zen center overlay (rectangle)
    if zen_overlay:
        cl = zen_overlay.get("center_low")
        ch = zen_overlay.get("center_high")
        cs = zen_overlay.get("center_start_idx")
        ce = zen_overlay.get("center_end_idx")
        if cl is not None and ch is not None and cs is not None and ce is not None:
            x1 = x_pos(cs)
            x2 = x_pos(ce)
            y1 = y_pos(ch)
            y2 = y_pos(cl)
            parts.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2-x1:.1f}" height="{y2-y1:.1f}" '
                         f'fill="#bc8cff" fill-opacity="0.18" stroke="#bc8cff" stroke-width="0.6" stroke-dasharray="2,2"/>')
            parts.append(f'<text x="{(x1+x2)/2:.1f}" y="{y1-2:.1f}" text-anchor="middle" fill="#bc8cff" font-size="8">中樞 {cl:.1f} - {ch:.1f}</text>')

    # candles
    for i, r in enumerate(ohlc):
        o = float(r.get("open") or 0)
        h = float(r.get("high") or 0)
        l = float(r.get("low") or 0)
        c = float(r.get("close") or 0)
        if not all([o, h, l, c]): continue
        x = x_pos(i)
        up = c >= o
        color = "#58d68d" if up else "#ec7063"
        # wick
        parts.append(f'<line x1="{x:.1f}" y1="{y_pos(h):.1f}" x2="{x:.1f}" y2="{y_pos(l):.1f}" stroke="{color}" stroke-width="0.8"/>')
        # body
        body_top = y_pos(max(o, c))
        body_bot = y_pos(min(o, c))
        body_h = max(1, body_bot - body_top)
        parts.append(f'<rect x="{x-candle_w/2:.1f}" y="{body_top:.1f}" width="{candle_w:.1f}" height="{body_h:.1f}" fill="{color}" opacity="0.9" rx="0.5">'
                     f'<title>{_esc(str(r.get("date", "")))[:10]} O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}</title></rect>')

    # buy/sell markers (from zen_overlay)
    if zen_overlay:
        for marker in zen_overlay.get("markers", []):
            idx = marker.get("idx")
            kind = marker.get("kind")  # "buy" or "sell"
            price = marker.get("price")
            if idx is None or price is None: continue
            x = x_pos(idx)
            y = y_pos(price)
            if kind == "buy":
                sym = "▲"
                color = "#58d68d"
                y_offset = -8
            else:
                sym = "▼"
                color = "#ec7063"
                y_offset = 12
            parts.append(f'<text x="{x:.1f}" y="{y+y_offset:.1f}" text-anchor="middle" fill="{color}" font-size="11" font-weight="700">{sym}</text>')

    parts.append('</svg>')
    return "".join(parts)


def _svg_horizontal_bars(items: list, width: int = 480, height: int = 180,
                          title: str = "", value_fmt: str = "+.1%") -> str:
    """Horizontal bar chart. items = [{label, value, color?, suffix?}]"""
    if not items: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 70, 60, 18, 16
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(items)
    bar_h = plot_h / n * 0.7
    gap = plot_h / n * 0.3

    abs_vals = [abs(it.get("value") or 0) for it in items]
    max_abs = max(abs_vals) if abs_vals else 1
    if max_abs == 0: max_abs = 1

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # zero line
    zero_x = pad_l + plot_w / 2
    parts.append(f'<line x1="{zero_x:.1f}" y1="{pad_t}" x2="{zero_x:.1f}" y2="{height-pad_b}" stroke="#3a4a6a" stroke-width="0.5" stroke-dasharray="2,2"/>')

    for i, it in enumerate(items):
        v = it.get("value") or 0
        label = it.get("label", "")
        color = it.get("color") or ("#58d68d" if v > 0 else "#ec7063" if v < 0 else "#8aa0c0")
        y = pad_t + i * (bar_h + gap) + gap / 2
        bar_w = abs(v) / max_abs * (plot_w / 2)
        if v >= 0:
            x = zero_x
        else:
            x = zero_x - bar_w
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bar_w, 1):.1f}" height="{bar_h:.1f}" fill="{color}" opacity="0.85" rx="1">'
                     f'<title>{_esc(label)}: {v}</title></rect>')
        # label
        parts.append(f'<text x="{pad_l-6}" y="{y + bar_h/2 + 3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="9">{_esc(label)}</text>')
        # value (after bar)
        val_str = f"{v*100:+.1f}%" if value_fmt == "+.1%" else f"{v:.1f}"
        text_x = zero_x + bar_w + 4 if v >= 0 else zero_x - bar_w - 4
        anchor = "start" if v >= 0 else "end"
        parts.append(f'<text x="{text_x:.1f}" y="{y + bar_h/2 + 3:.1f}" text-anchor="{anchor}" fill="{color}" font-size="9" font-weight="600">{val_str}</text>')

    parts.append('</svg>')
    return "".join(parts)


def _svg_grouped_bars(categories: list, series: dict, width: int = 480, height: int = 200,
                       title: str = "", value_fmt: str = "{:.1f}") -> str:
    """Grouped vertical bar chart. categories = [labels on x-axis].
    series = {name: [values, ...]} with same length as categories.
    """
    if not categories or not series: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 12, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(categories)
    n_series = len(series)
    group_w = plot_w / n
    bar_w = group_w / (n_series + 0.5)

    all_vals = []
    for vals in series.values():
        for v in vals:
            if v is not None: all_vals.append(v)
    if not all_vals: return '<div class="muted">_無資料_</div>'
    vmax = max(all_vals)
    vmin = min(all_vals)
    if vmax == vmin: vmax = vmin + 1
    vmax *= 1.1
    if vmin < 0: vmin *= 1.1
    yrange = vmax - vmin

    def y_pos(v): return pad_t + (1 - (v - vmin) / yrange) * plot_h

    palette = ["#5fb1ff", "#58d68d", "#f5b041", "#bc8cff", "#ec7063", "#39c5cf"]
    colors = {n: palette[i % len(palette)] for i, n in enumerate(series.keys())}

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # zero line if vmin < 0
    if vmin < 0:
        zy = y_pos(0)
        parts.append(f'<line x1="{pad_l}" y1="{zy:.1f}" x2="{width-pad_r}" y2="{zy:.1f}" stroke="#3a4a6a" stroke-width="0.5" stroke-dasharray="2,2"/>')

    # y grid
    for t in range(5):
        v = vmin + yrange * t / 4
        y = y_pos(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.0f}</text>')

    # bars
    for i, cat in enumerate(categories):
        gx = pad_l + i * group_w
        for s_i, (name, vals) in enumerate(series.items()):
            if i >= len(vals) or vals[i] is None: continue
            v = vals[i]
            x = gx + s_i * bar_w + bar_w * 0.1
            color = colors[name]
            if v >= 0:
                y = y_pos(v)
                h = y_pos(0) - y if vmin < 0 else pad_t + plot_h - y
                if vmin >= 0: h = (pad_t + plot_h) - y
                else: h = y_pos(0) - y
                h = max(1, h)
                y_top = y
            else:
                y = y_pos(0)
                h = y_pos(v) - y_pos(0)
                h = max(1, h)
                y_top = y_pos(v)
            parts.append(f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bar_w*0.9:.1f}" height="{h:.1f}" fill="{color}" opacity="0.85" rx="1">'
                         f'<title>{_esc(name)} {_esc(str(cat))}: {v:.1f}</title></rect>')
        # x label
        parts.append(f'<text x="{gx + group_w/2:.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{_esc(str(cat))[:10]}</text>')

    # legend
    legend_y = height - 4
    leg_x = pad_l
    for name, c in colors.items():
        parts.append(f'<rect x="{leg_x}" y="{legend_y-7}" width="8" height="8" fill="{c}" opacity="0.85" rx="1"/>')
        parts.append(f'<text x="{leg_x+11}" y="{legend_y}" fill="#8aa0c0" font-size="8">{_esc(name)}</text>')
        leg_x += 12 + len(name) * 5 + 8

    parts.append('</svg>')
    return "".join(parts)


def _svg_combo_bar_line(categories: list, bars: list, line: list, width: int = 480, height: int = 200,
                          title: str = "", bar_label: str = "", line_label: str = "") -> str:
    """Combo chart: bar values + line overlay (e.g. revenue bars + YoY line).
    bars = [values], line = [values].
    """
    if not categories: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 50, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(categories)

    # y scale: bars (left), line (right) — use 0-100 for YoY % on right
    bar_max = max([b for b in bars if b is not None] + [1])
    line_vals = [l for l in line if l is not None]
    line_min = min(line_vals) if line_vals else 0
    line_max = max(line_vals) if line_vals else 1
    line_pad = max(5, (line_max - line_min) * 0.1)
    line_min -= line_pad; line_max += line_pad
    if line_min > 0: line_min = 0  # anchor at 0 for %

    bar_w = plot_w / n * 0.65

    def y_bar(v): return pad_t + (1 - v / bar_max) * plot_h
    def y_line(v):
        if line_max == line_min: return pad_t + plot_h / 2
        return pad_t + (1 - (v - line_min) / (line_max - line_min)) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # y left axis (bars)
    for t in range(5):
        v = bar_max * t / 4
        y = y_bar(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.0f}</text>')
    # y right axis (line)
    for t in range(5):
        v = line_min + (line_max - line_min) * t / 4
        y = y_line(v)
        parts.append(f'<text x="{width-pad_r+4}" y="{y+3:.1f}" text-anchor="start" fill="#bc8cff" font-size="8">{v:+.0f}%</text>')

    # bars
    for i, cat in enumerate(categories):
        x = pad_l + i * (plot_w / n) + (plot_w / n - bar_w) / 2
        b = bars[i] if i < len(bars) else None
        if b is not None:
            y = y_bar(b)
            h = (pad_t + plot_h) - y
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 1):.1f}" fill="#5fb1ff" opacity="0.75" rx="1">'
                         f'<title>{_esc(str(cat))} {bar_label}: {b:,.0f}</title></rect>')
        # x label
        parts.append(f'<text x="{pad_l + i * (plot_w/n) + plot_w/n/2:.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{_esc(str(cat))[:10]}</text>')

    # line (YoY)
    pts = []
    for i, lv in enumerate(line):
        if lv is None: continue
        x = pad_l + i * (plot_w / n) + plot_w / n / 2
        y = y_line(lv)
        pts.append(f"{x:.1f},{y:.1f}")
    if pts:
        parts.append(f'<path d="M {" L ".join(pts)}" fill="none" stroke="#bc8cff" stroke-width="1.5"/>')
        # dots
        for i, lv in enumerate(line):
            if lv is None: continue
            x = pad_l + i * (plot_w / n) + plot_w / n / 2
            y = y_line(lv)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#bc8cff">'
                         f'<title>{_esc(str(categories[i]))} {line_label}: {lv:+.1f}%</title></circle>')

    # legend
    parts.append(f'<rect x="{pad_l}" y="{height-7}" width="8" height="6" fill="#5fb1ff" opacity="0.75" rx="1"/>')
    parts.append(f'<text x="{pad_l+11}" y="{height-2}" fill="#8aa0c0" font-size="8">{_esc(bar_label)}</text>')
    parts.append(f'<rect x="{pad_l + len(bar_label)*6 + 24}" y="{height-7}" width="8" height="6" fill="#bc8cff" rx="1"/>')
    parts.append(f'<text x="{pad_l + len(bar_label)*6 + 35}" y="{height-2}" fill="#8aa0c0" font-size="8">{_esc(line_label)}</text>')

    parts.append('</svg>')
    return "".join(parts)


# ---- institutional + technical chart sections ----

def render_institutional_section(ticker: str) -> str:
    """Three-major institutional investors, last 8 trading days, with bar chart + table."""
    rows = db.ticker_history(ticker, days=10)  # grab 10 to filter weekends
    if not rows: return '<div class="muted">_查無三大法人_</div>'
    # Take last 8 (most recent first in list, but list is asc so last 8)
    rows = rows[-8:]
    chart_rows = [
        {
            "date": r.get("Date"),
            "ForeignNet": float(r.get("ForeignNet") or 0) / 1000.0,  # 張
            "InvestmentNet": float(r.get("InvestmentNet") or 0) / 1000.0,
            "DealerNet": float(r.get("DealerNet") or 0) / 1000.0,
            "ThreeNet": float(r.get("ThreeNet") or 0) / 1000.0,
        }
        for r in rows
    ]
    # Build chart rows in display order (most recent on top? No, left-to-right asc)
    # we want most recent on the RIGHT
    chart_rows_asc = list(reversed(chart_rows))
    chart = _svg_bar_chart(
        chart_rows_asc,
        value_keys=["ForeignNet", "InvestmentNet", "DealerNet", "ThreeNet"],
        labels=["外資", "投信", "自營", "合計"],
        colors=["#5fb1ff", "#58d68d", "#f5b041", "#bc8cff"],
        width=520, height=180, title="三大法人買賣超 (近 8 日, 單位: 張)",
    )

    # Table - most recent first
    items = ["| 日期 | 外資 | 投信 | 自營 | 合計 |", "|---|---|---|---|---|"]
    cum_f = cum_t = cum_d = 0
    for r in reversed(chart_rows):
        f_v = r["ForeignNet"]; t_v = r["InvestmentNet"]; d_v = r["DealerNet"]; total = r["ThreeNet"]
        cum_f += f_v; cum_t += t_v; cum_d += d_v
        items.append(
            f"| {_esc(r['date'])[:10]} | {_signed(f_v)} | {_signed(t_v)} | {_signed(d_v)} | **{_signed(total)}** |"
        )
    items.append(f"\n**近 8 日累積**：外資 {_signed(cum_f)} 張｜投信 {_signed(cum_t)} 張｜自營 {_signed(cum_d)} 張｜合計 {_signed(cum_f+cum_t+cum_d)} 張")
    return chart + "\n" + "\n".join(items)


def render_technical_section(ticker: str) -> str:
    """Price + MA + RSI chart, last 60 days."""
    rows = db.ticker_history(ticker, days=70)
    if not rows or len(rows) < 30:
        return '<div class="muted">_K 線資料不足_</div>'
    rows = rows[-60:]
    dates = [r.get("Date") for r in rows]
    # 把 None / 0 / 負值 視為缺值 (DB 偶有 NULL), 不會畫成掉到 0 的假性暴跌
    closes = []
    for r in rows:
        v = r.get("Close")
        if v is None or (isinstance(v, (int, float)) and v <= 0):
            closes.append(None)
        else:
            closes.append(float(v))

    # MA5/13/27/54 — 跳過 None 視窗, 視窗內有效值 < 一半才標 None
    def ma(closes, n):
        out = [None] * len(closes)
        for i in range(n - 1, len(closes)):
            window = closes[i - n + 1:i + 1]
            valid = [c for c in window if c is not None]
            if len(valid) >= max(2, n // 2):
                out[i] = sum(valid) / len(valid)
        return out

    ma5 = ma(closes, 5)
    ma13 = ma(closes, 13)
    ma27 = ma(closes, 27)
    ma54 = ma(closes, 54)
    rsi = _compute_rsi(closes, 14)

    def to_xy(arr):
        return [(i, v) for i, v in enumerate(arr) if v is not None]

    main_chart = _svg_line_chart(
        {
            "收盤": to_xy(closes),
            "MA5": to_xy(ma5),
            "MA13": to_xy(ma13),
            "MA27": to_xy(ma27),
            "MA54": to_xy(ma54),
        },
        dates=dates, width=520, height=220,
        title="收盤價 + 均線 (近 60 日)",
    )
    rsi_chart = _svg_line_chart(
        {"RSI(14)": [(i, v) for i, v in enumerate(rsi) if v is not None]},
        dates=dates, width=520, height=120,
        title="RSI(14) 動能指標 (超買 >70 / 超賣 <30)",
        n_total=len(closes),
    )

    # 取最後一個有效收盤價（避免 closes[-1] 是 None）
    valid_closes = [c for c in closes if c is not None]
    if not valid_closes:
        return '<div class="muted">_K 線資料不足_</div>'
    cur = valid_closes[-1]
    last_ma5 = ma5[-1] or 0
    last_ma13 = ma13[-1] or 0
    last_ma27 = ma27[-1] or 0
    last_ma54 = ma54[-1] or 0
    last_rsi = rsi[-1] or 0
    trend = "多頭排列" if (cur > last_ma5 > last_ma13 > last_ma27) else \
            "空頭排列" if (cur < last_ma5 < last_ma13 < last_ma27) else "盤整/糾結"
    if cur > last_ma13 > last_ma27 and last_ma13 > last_ma5:
        trend = "短空長多，留意落底"
    if last_rsi > 70: rsi_label = "超買"
    elif last_rsi < 30: rsi_label = "超賣"
    else: rsi_label = "中性"

    summary = f"""
- 收盤: **{cur:.2f}** | MA5: {last_ma5:.2f} | MA13: {last_ma13:.2f} | MA27: {last_ma27:.2f} | MA54: {last_ma54:.2f}
- RSI(14): **{last_rsi:.1f}** ({rsi_label}) | 趨勢: **{trend}**
- 區間高: {max(valid_closes):.2f} | 區間低: {min(valid_closes):.2f} | 波動: {(max(valid_closes)-min(valid_closes))/cur*100:.1f}%
"""
    return main_chart + rsi_chart + summary



# ---- per-pick section renderers ----

def render_pick_header(c: ms.Candidate) -> str:
    change_pct = c.change_pct or 0
    pcls = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
    horizon = c.horizon or "long"
    horizon_label = "長期" if horizon == "long" else "短中期"
    industry = c.industry or "—"
    cap_label = f"{c.market_cap / 1e8:,.1f} 億" if c.market_cap is not None else "未提供"
    return f"""
    <div class="pick-head {horizon}">
      <div>
        <div><span class="pick-ticker">{_esc(c.ticker)}</span> <span class="pick-name">{_esc(c.name)}</span> <span class="pick-horizon {horizon}">{horizon_label}</span></div>
        <div class="muted" style="font-size:0.78rem;margin-top:3px">{_esc(industry)} · 市值 {cap_label} · 成交量 {c.volume/1000:,.1f} 張</div>
      </div>
      <div class="pick-price {pcls}">{_fmt_price(c.close)} <span class="muted" style="font-size:0.7rem">{_fmt_pct(change_pct/100)}</span></div>
    </div>
    """


def render_tags_bar(c: ms.Candidate) -> str:
    """Reuse tags from market_screen Candidate by reconstructing from a quick call."""
    # We rely on tags already attached to candidate. But Candidate has no tags attr
    # — tags are generated in market_report_html.render_pick. Instead, use chip + horizon summary.
    tags = []
    if c.excess_return_240d is not None:
        cls = "tag-green" if c.excess_return_240d > 0 else "tag-red"
        tags.append(f'<span class="tag {cls}">240 曆日價格報酬 {c.excess_return_240d:+.1%}</span>')
    if c.foreign_net and c.foreign_net > 0:
        tags.append(f'<span class="tag tag-green">外資 +{c.foreign_net/1000:,.0f} 張</span>')
    elif c.foreign_net and c.foreign_net < 0:
        tags.append(f'<span class="tag tag-red">外資 {c.foreign_net/1000:,.0f} 張</span>')
    if c.rsi14:
        if 50 <= c.rsi14 <= 65:
            tags.append(f'<span class="tag tag-green">RSI {c.rsi14:.0f} 甜蜜區</span>')
        elif c.rsi14 > 70:
            tags.append(f'<span class="tag tag-red">RSI {c.rsi14:.0f} 超買</span>')
        elif c.rsi14 < 30:
            tags.append(f'<span class="tag tag-green">RSI {c.rsi14:.0f} 超賣</span>')
    if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
        tags.append('<span class="tag tag-green">多頭排列</span>')
    if c.chip_score and c.chip_score > 50:
        tags.append(f'<span class="tag tag-cyan">ChipScore {c.chip_score:.0f}</span>')
    if c.volume_burst == 1:
        tags.append('<span class="tag tag-yellow">量能爆發</span>')
    if c.kd_golden_cross == 1:
        tags.append('<span class="tag tag-green">KD 黃金交叉</span>')
    if c.inv_first_in == 1:
        tags.append('<span class="tag tag-yellow">法人首次進場</span>')
    return f'<div class="tags">{"".join(tags)}</div>'


def render_zen_section(c: ms.Candidate) -> str:
    """Zen summary from Candidate.zen_summary (already populated by market_screen)."""
    if not c.zen_summary:
        return '<div class="muted">無 Zen 結構資料</div>'
    cells = []
    for line in c.zen_summary.split("\n"):
        line = line.strip()
        if not line: continue
        if line.startswith("**") and "**：" in line:
            label, val = line.split("**：", 1)
            label = label.strip("*").strip()
            val = val.strip()
            vcls = ""
            if "方向" in label and "偏多" in val and "偏空" not in val:
                vcls = "zen-bullish"
            elif "方向" in label and "偏空" in val and "偏多" not in val:
                vcls = "zen-bearish"
            cells.append(f'<div class="zen-cell"><div class="zen-cell-label">{_esc(label)}</div><div class="zen-cell-value {vcls}">{_esc(val)}</div></div>')
    return f'<div class="zen-grid">{"".join(cells)}</div>'


def render_news_section(d: Dict, ticker: Optional[str] = None, limit=5) -> str:
    """Render the news section.

    Always reads from the OpenAlice `stock_news` table. FinMind's
    TaiwanStockNews dataset lags 24-72h for popular tickers, so the
    `d["news"]` set by `analyze_stock.fetch_all → fm.stock_news` is no
    longer trusted. The dedicated news-refresh tasks
    (OpenAlice News Refresh Every 2h / RSS Refresh / AI-Telegram Stock
    News Auto Refresh) keep stock_news same-day.
    """
    rows = []
    db_error = d.get("_canonical_news_error")
    canonical = d.get("_canonical_news")
    target_date = (os.environ.get("TW_NEWS_DATE")
                   or os.environ.get("TW_DATA_DATE")
                   or db.latest_date("daily_data2_full")
                   or datetime.now().strftime("%Y-%m-%d"))
    if canonical is not None:
        rows = canonical
    elif ticker:
        try:
            fresh = db.news_for_tickers([ticker], limit_per=limit, days=5,
                                        target_date=target_date).get(ticker, [])
            rows = fresh
        except Exception as exc:
            db_error = str(exc)
            rows = []
    rows = [
        {
            "title": r.get("title", "—"),
            "source": r.get("source", "—"),
            "date": r.get("published_at") or r.get("date"),
            "link": r.get("link") or r.get("url", ""),
        }
        for r in rows
    ]

    fallback_used = False
    if not rows:
        # FinMind is allowed only when it meets the same five-day freshness
        # contract. Never silently reintroduce the known 30-day stale feed.
        end_date = date.fromisoformat(str(target_date)[:10])
        start_date = end_date - timedelta(days=4)
        for row in d.get("news") or []:
            value = row.get("date") or row.get("published_at")
            try:
                published = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                continue
            if start_date <= published <= end_date:
                rows.append({
                    "title": row.get("title", "—"),
                    "source": f"{row.get('source', 'FinMind')}（FinMind fallback）",
                    "date": value,
                    "link": row.get("link") or row.get("url", ""),
                })
        fallback_used = bool(rows)
    if not rows:
        reason = "stock_news 暫時無法讀取；" if db_error else ""
        return f'<div class="muted">_{reason}近 5 日無可驗證新聞_</div>'
    rows_sorted = sorted(rows, key=lambda x: str(x.get("date", "")).replace("T", " "), reverse=True)[:limit]
    items = []
    for r in rows_sorted:
        title = r.get("title", "—")
        source = r.get("source", "—")
        date_s = r.get("date", "—")
        if hasattr(date_s, "strftime"):
            date_s = date_s.strftime("%Y-%m-%d %H:%M:%S")
        link = r.get("link", "")
        if link:
            items.append(f'<div class="news-item">· <a href="{_esc(link)}" target="_blank">{_esc(title)}</a><div class="muted" style="font-size:0.7rem">{_esc(str(date_s))} · {_esc(source)}</div></div>')
        else:
            items.append(f'<div class="news-item">· {_esc(title)}<div class="muted" style="font-size:0.7rem">{_esc(str(date_s))} · {_esc(source)}</div></div>')
    if fallback_used:
        items.insert(0, '<div class="muted">stock_news 無近期資料；以下為符合 5 日時限的 FinMind fallback。</div>')
    return "\n".join(items)


def render_dividend_section(d: Dict) -> str:
    rows = d.get("dividend") or []
    if not rows:
        return '<div class="muted">_查無配息資料_</div>'
    rows_sorted = sorted(rows, key=lambda x: (x.get("year", 0), x.get("CashExDividendTradingDate", "")), reverse=True)[:5]
    items = ["| 年度 | 現金 | 股票 | 合計 |", "|---|---|---|---|"]
    for r in rows_sorted:
        try: cash = float(r.get("CashEarningsDistribution") or 0)
        except: cash = 0
        try: stock = float(r.get("StockEarningsDistribution") or 0)
        except: stock = 0
        items.append(f"| {r.get('year', '—')} | {cash:.2f} | {stock:.2f} | {cash+stock:.2f} |")
    return "\n".join(items)


def render_financial_section(d: Dict) -> str:
    """Quarterly financial statements — render from raw rows."""
    rows = d.get("financial") or []
    if not rows:
        return '<div class="muted">_查無季度財報_</div>'
    type_map = {
        "Revenue": "revenue", "GrossProfit": "grossProfit", "OperatingIncome": "operatingIncome",
        "PreTaxIncome": "pretaxIncome", "IncomeAfterTaxes": "netIncome", "EPS": "EPS",
        "營業收入": "revenue", "營業毛利": "grossProfit", "營業利益": "operatingIncome",
        "稅前淨利": "pretaxIncome", "本期淨利": "netIncome", "歸屬於母公司業主之淨利": "netIncome",
        "基本每股盈餘": "EPS",
    }
    pivot: Dict[str, Dict[str, float]] = {}
    for r in rows:
        d_str = r.get("date", "")
        t = r.get("type", "")
        col = type_map.get(t)
        if not col: continue
        try:
            v = float(r.get("value")) if r.get("value") is not None else None
        except: continue
        pivot.setdefault(d_str, {})[col] = v
    if not pivot:
        return '<div class="muted">_財報格式無法解析_</div>'
    dates = sorted(pivot.keys(), reverse=True)[:6]
    dates.reverse()
    keep = ["revenue", "grossProfit", "operatingIncome", "netIncome", "EPS"]
    headers = ["季度", "營收(億)", "毛利(億)", "營業利益(億)", "淨利(億)", "EPS"]
    items = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * 6) + "|"]
    for d_str in dates:
        row = pivot[d_str]
        cells = [d_str]
        for k in keep:
            v = row.get(k)
            if v is None: cells.append("—")
            elif k == "EPS": cells.append(f"{v:.2f}")
            else: cells.append(f"{v/1e8:.1f}")
        items.append("| " + " | ".join(cells) + " |")
    return "\n".join(items)


def render_margin_section(d: Dict) -> str:
    rows = d.get("margin") or []
    if not rows:
        return '<div class="muted">_查無融資融券_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)
    r = rows_sorted[0]
    date = r.get("date", "—")
    mb = int(r.get("MarginPurchaseTodayBalance") or 0)
    ms = int(r.get("ShortSaleTodayBalance") or 0)
    mb_prev = int(r.get("MarginPurchaseYesterdayBalance") or 0)
    change = mb - mb_prev
    ratio = (mb / ms) if ms else None
    ratio_str = f"{ratio:.1f}" if ratio else "—"
    return (
        f"_資料日：{date}_\n\n"
        f"| 項目 | 融資 | 融券 |\n|---|---|---|\n"
        f"| 今日餘額 | **{mb:,}** 張 | **{ms:,}** 張 |\n"
        f"| 較昨日 | {_signed(change)} 張 | — |\n"
        f"| 融資融券比 | {ratio_str} | — |\n"
    )


def render_finlab_roe(d: Dict) -> str:
    rows = d.get("finlab_roe") or []
    if not rows:
        return '<div class="muted">_FinLab free tier 不提供 / 額度已滿_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:6]
    rows_sorted.reverse()
    items = ["| 季度 | ROE |", "|---|---|"]
    for r in rows_sorted:
        v = r.get("value")
        items.append(f"| {r.get('date', '—')} | {f'{v:.2f}%' if v is not None else '—'} |")
    items.append("\n_資料來源：FinLab（free tier 限 ~2018）_")
    return "\n".join(items)


def render_finlab_revenue(d: Dict) -> str:
    rows = d.get("finlab_revenue") or []
    if not rows:
        return '<div class="muted">_FinLab free tier 不提供 / 額度已滿_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:8]
    rows_sorted.reverse()
    items = ["| 月份 | 營收 | YoY |", "|---|---|---|"]
    for r in rows_sorted:
        v = r.get("value")
        yoy = r.get("yoy")
        date_s = r.get("date", "—")[:7]
        v_str = f"{v:,.0f}" if v is not None else "—"
        yoy_str = f"{yoy:+.1f}%" if yoy is not None else "—"
        items.append(f"| {date_s} | {v_str} | {yoy_str} |")
    items.append("\n_資料來源：FinLab（free tier 限 ~2018）_")
    return "\n".join(items)


def render_observations(d: Dict) -> str:
    obs = a.section_observations(d)
    return obs.replace("\n", "<br>")


# ---- chart-enhanced sections ----

def render_zen_chart_section(ticker: str, c: ms.Candidate) -> str:
    """K-line candlestick + zen center overlay + buy/sell markers (120 days)."""
    rows = db.ticker_history(ticker, days=130)
    if not rows or len(rows) < 30:
        return '<div class="muted">_K 線資料不足_</div>'
    rows = rows[-120:]
    ohlc = [{"date": r.get("Date"), "open": r.get("Open"), "high": r.get("High"),
             "low": r.get("Low"), "close": r.get("Close")} for r in rows]

    # Try to get zen center from cand.zen_summary or compute
    overlay = {}
    if c.zen_summary:
        for line in c.zen_summary.split("\n"):
            line = line.strip()
            if "中樞" in line and "**" not in line and "失效" not in line and "買點" not in line and "賣點" not in line:
                # parse "中樞: 1725.00 - 1985.00（2026-07-08 ~ 2026-07-29）"
                import re
                m = re.match(r"中樞：?\s*([\d.]+)\s*-\s*([\d.]+)", line)
                if m:
                    overlay["center_low"] = float(m.group(1))
                    overlay["center_high"] = float(m.group(2))
                    # find date range
                    m2 = re.search(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", line)
                    if m2:
                        try:
                            s_date = m2.group(1)
                            e_date = m2.group(2)
                            # find indices
                            for idx, r in enumerate(ohlc):
                                d = r.get("date")
                                d_s = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                                if d_s >= s_date and overlay.get("center_start_idx") is None:
                                    overlay["center_start_idx"] = idx
                                if d_s <= e_date:
                                    overlay["center_end_idx"] = idx
                        except: pass
                    break

    # 買點/賣點 markers
    markers = []
    if c.zen_summary:
        for line in c.zen_summary.split("\n"):
            line = line.strip()
            if "買點" in line and "：**" in line:
                # 二買: 拉回至中樞高 X 且不破 (現價 Y)
                import re
                m = re.search(r"現價\s*([\d.]+)", line)
                if m:
                    cur_price = float(m.group(1))
                    # find the last bar index
                    markers.append({"idx": len(ohlc)-1, "kind": "buy", "price": cur_price})
            elif "賣點" in line and "：**" in line:
                import re
                m = re.search(r"現價\s*([\d.]+)", line)
                if m:
                    cur_price = float(m.group(1))
                    markers.append({"idx": len(ohlc)-1, "kind": "sell", "price": cur_price})
    if markers:
        overlay["markers"] = markers

    chart = _svg_candlestick(ohlc, width=520, height=240, title="K 線 (近 120 日) + 中樞/買賣點",
                            zen_overlay=overlay if overlay else None)

    # 補充資訊表
    cur = float(ohlc[-1].get("close") or 0)
    high_60 = max([float(r.get("high") or 0) for r in ohlc[-60:]])
    low_60 = min([float(r.get("low") or 0) for r in ohlc[-60:]])
    summary = f"""
- 收盤: **{cur:.2f}** | 60日高: {high_60:.2f} | 60日低: {low_60:.2f} | 振幅: {(high_60 - low_60)/cur*100:.1f}%
"""
    return chart + summary


def render_valuation_section(c: ms.Candidate) -> str:
    """20d excess return and calendar-day price returns; missing bars stay absent."""
    items = [
        {"label": "20 曆日相對樣本均值", "value": c.excess_return_20d},
        {"label": "60 曆日", "value": c.excess_return_60d},
        {"label": "120 曆日", "value": c.excess_return_120d},
        {"label": "240 曆日", "value": c.excess_return_240d},
    ]
    missing = [item["label"] for item in items if item["value"] is None]
    chart = _svg_horizontal_bars([item for item in items if item["value"] is not None], width=520, height=130,
                                  title="原始價格報酬（20 曆日減有效樣本等權均值）", value_fmt="+.1%")
    if missing:
        chart += '<div class="muted">未提供：' + _esc('、'.join(missing)) + '</div>'
    cap_label = f"{c.market_cap / 1e8:,.1f} 億" if c.market_cap is not None else "未提供"
    summary = f"""
- 市值: **{cap_label}** | 收盤: {c.close:.2f} | 成交量: {c.volume/1000:,.1f} 張
- 60/120/240 為日曆日回溯原始價格報酬；20 曆日相對報酬扣除當日有效樣本等權均值。未含股息或除權息調整，不代表總報酬或相對加權指數報酬。
"""
    return chart + summary


def render_margin_chart_section(ticker: str, d: Dict) -> str:
    """Margin balance trend (line) + daily change (bars) over last 30 days."""
    rows = db.ticker_history(ticker, days=35)
    if not rows:
        return render_margin_section(d)
    rows = rows[-30:]
    dates = [r.get("Date") for r in rows]
    balances = [float(r.get("MarginBalance") or 0) for r in rows]  # DB already stores lots
    shorts = [float(r.get("ShortBalance") or 0) for r in rows]

    # Daily change
    changes = [None]
    for i in range(1, len(balances)):
        changes.append(balances[i] - balances[i-1])

    # Line chart: 融資 + 融券
    main_chart = _svg_line_chart(
        {
            "融資 (張)": [(i, v) for i, v in enumerate(balances) if v is not None],
            "融券 (張)": [(i, v) for i, v in enumerate(shorts) if v is not None],
        },
        dates=dates, width=520, height=160, title="融資融券餘額走勢 (近 30 日)",
    )

    # Bar chart: daily change
    bar_data = [{"date": d, "ForeignNet": 0, "InvestmentNet": 0, "DealerNet": 0, "ThreeNet": chg or 0}
                for d, chg in zip(dates, changes)]
    bar_data = [b for b in bar_data if b["ThreeNet"] != 0]
    if bar_data:
        change_chart = _svg_bar_chart(
            bar_data[-20:],
            value_keys=["ThreeNet"],
            labels=["日增減"],
            colors=["#f5b041"],
            width=520, height=100, title="融資日增減 (近 20 日, 張)",
        )
    else:
        change_chart = ""

    if rows:
        r = rows[-1]
        mb = int(r.get("MarginBalance") or 0)
        ms = int(r.get("ShortBalance") or 0)
        ratio = (mb / ms) if ms else None
        ratio_str = f"{ratio:.1f}" if ratio else "—"
        return main_chart + change_chart + f"""
- 今日融資: **{mb:,} 張** | 融券: **{ms:,} 張** | 融資融券比: {ratio_str}
"""
    return main_chart + change_chart


def render_financial_chart_section(d: Dict) -> str:
    """Quarterly financial statements: 6-quarter grouped bar chart + table."""
    rows = d.get("financial") or []
    if not rows: return '<div class="muted">_查無季度財報_</div>'
    type_map = {
        "Revenue": "revenue", "GrossProfit": "grossProfit", "OperatingIncome": "operatingIncome",
        "PreTaxIncome": "pretaxIncome", "IncomeAfterTaxes": "netIncome", "EPS": "EPS",
        "營業收入": "revenue", "營業毛利": "grossProfit", "營業利益": "operatingIncome",
        "稅前淨利": "pretaxIncome", "本期淨利": "netIncome", "歸屬於母公司業主之淨利": "netIncome",
        "基本每股盈餘": "EPS",
    }
    pivot = {}
    for r in rows:
        d_str = r.get("date", "")
        t = r.get("type", "")
        col = type_map.get(t)
        if not col: continue
        try:
            v = float(r.get("value")) if r.get("value") is not None else None
        except: continue
        pivot.setdefault(d_str, {})[col] = v
    if not pivot: return '<div class="muted">_財報格式無法解析_</div>'

    dates = sorted(pivot.keys(), reverse=True)[:6]
    dates.reverse()
    categories = [d[2:].replace("-", "Q") if len(d) >= 7 else d for d in dates]  # e.g. "25Q3"

    # Convert to 億
    rev = [pivot[d].get("revenue", 0) / 1e8 if pivot[d].get("revenue") else None for d in dates]
    oi = [pivot[d].get("operatingIncome", 0) / 1e8 if pivot[d].get("operatingIncome") else None for d in dates]
    ni = [pivot[d].get("netIncome", 0) / 1e8 if pivot[d].get("netIncome") else None for d in dates]
    eps = [pivot[d].get("EPS") for d in dates]

    chart = _svg_grouped_bars(categories, {"營收(億)": rev, "營業利益(億)": oi, "淨利(億)": ni},
                              width=520, height=180, title="近 6 季季報 (億)")

    # EPS line below
    eps_chart = _svg_line_chart(
        {"EPS (元)": [(i, v) for i, v in enumerate(eps) if v is not None]},
        dates=dates, width=520, height=80, title="EPS 趨勢 (元)",
    )

    # Compact table
    table = "| 季度 | 營收(億) | 毛利(億) | 營業利益(億) | 淨利(億) | EPS |\n|---|---|---|---|---|---|\n"
    for d in dates:
        row = pivot[d]
        def fmt(k, scale=1e8):
            v = row.get(k)
            if v is None: return "—"
            if k == "EPS": return f"{v:.2f}"
            return f"{v/scale:.1f}"
        table += f"| {d[2:7].replace('-', 'Q')} | {fmt('revenue')} | {fmt('grossProfit')} | {fmt('operatingIncome')} | {fmt('netIncome')} | {fmt('EPS')} |\n"
    return chart + eps_chart + "\n" + table


def render_finlab_roe_chart(d: Dict) -> str:
    """ROE history line chart + table."""
    rows = d.get("finlab_roe") or []
    if not rows:
        return '<div class="muted">_查無 ROE 資料_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""))[-12:]  # 最多 12 季
    if not rows_sorted: return '<div class="muted">_查無 ROE 資料_</div>'
    dates = [r.get("date", "") for r in rows_sorted]
    vals = [float(r.get("value")) if r.get("value") is not None else None for r in rows_sorted]

    chart = _svg_line_chart(
        {"ROE (%)": [(i, v) for i, v in enumerate(vals) if v is not None]},
        dates=dates, width=520, height=140, title="ROE 季度趨勢 (%)",
    )
    latest = vals[-1] if vals[-1] else None
    note = f"\n_最新 ROE: **{latest:.2f}%** | 資料來源：FinMind TaiwanStockFinancialStatements_\n" if latest is not None else "\n_資料來源：FinMind_\n"
    return chart + note


def render_finlab_revenue_chart(d: Dict) -> str:
    """Monthly revenue combo chart: bar + YoY line."""
    rows = d.get("finlab_revenue") or []
    if not rows:
        return '<div class="muted">_查無月營收_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""))[-12:]
    if not rows_sorted: return '<div class="muted">_查無月營收_</div>'
    # Strip timestamp and take year-month; date format is "2025-08-01" or "2018-12-10 00:00:00"
    cats = []
    for r in rows_sorted:
        ds = str(r.get("date", ""))[:7]  # "2025-08"
        cats.append(ds[2:])  # "25-08"
    bars = [float(r.get("value")) if r.get("value") is not None else None for r in rows_sorted]
    line = [float(r.get("yoy")) if r.get("yoy") is not None else None for r in rows_sorted]
    chart = _svg_combo_bar_line(cats, bars, line, width=520, height=180,
                                 title="月營收 + YoY (近 12 月)", bar_label="營收", line_label="YoY%")
    latest_yoy = [y for y in line if y is not None][-1] if any(line) else None
    note = f"\n_最新 YoY: **{latest_yoy:+.1f}%** | 資料來源：FinMind TaiwanStockMonthRevenue_\n" if latest_yoy is not None else "\n_資料來源：FinMind TaiwanStockMonthRevenue_\n"
    return chart + note


def render_dividend_chart_section(d: Dict) -> str:
    """Dividend history stacked bar (cash + stock) + total line."""
    rows = d.get("dividend") or []
    if not rows: return '<div class="muted">_查無配息資料_</div>'
    # Group by year
    by_year: Dict[str, Dict[str, float]] = {}
    for r in rows:
        y = r.get("year", "")
        if not y or y in ("不適用", "0"): continue
        try:
            cash = float(r.get("CashEarningsDistribution") or 0)
        except: cash = 0
        try:
            stock = float(r.get("StockEarningsDistribution") or 0)
        except: stock = 0
        if y not in by_year:
            by_year[y] = {"cash": 0, "stock": 0}
        by_year[y]["cash"] += cash
        by_year[y]["stock"] += stock
    if not by_year: return '<div class="muted">_查無配息資料_</div>'
    years = sorted(by_year.keys())[-5:]  # 最近 5 年
    cash = [by_year[y]["cash"] for y in years]
    stock = [by_year[y]["stock"] for y in years]
    total = [c + s for c, s in zip(cash, stock)]

    # Stacked bar via grouped_bars (will show side by side, but we want stacked — fake with 2 series)
    # Use line for total
    chart = _svg_grouped_bars(years, {"現金股利": cash, "股票股利": stock},
                              width=520, height=140, title="近 5 年股利 (元/股)")
    line_chart = _svg_line_chart(
        {"合計": [(i, v) for i, v in enumerate(total) if v is not None]},
        dates=years, width=520, height=80, title="合計股利 (元/股)",
    )
    # Compact table
    table = "| 年度 | 現金 | 股票 | 合計 |\n|---|---|---|---|\n"
    for y in years:
        c = by_year[y]["cash"]; s = by_year[y]["stock"]
        table += f"| {y} | {c:.2f} | {s:.2f} | {c+s:.2f} |\n"
    return chart + line_chart + "\n" + table


def render_deep_dive_prompt(c: ms.Candidate) -> str:
    """Tiger Global or Baupost prompt based on horizon/return."""
    try:
        prompt = ddp.render_prompt(c)
        # Escape for HTML
        return f'<div class="dd-prompt"><button class="copy-btn" onclick="copyText(this)">📋 複製</button><pre>{_esc(prompt)}</pre></div>'
    except Exception as e:
        return f'<div class="muted">_deep-dive prompt 生成失敗：{e}_</div>'


def fetch_error_sources(errors):
    # Public artifacts expose source labels, never request URLs or credentials.
    labels = []
    for error in errors:
        label = str(error).split(":", 1)[0]
        labels.append(label if _re.fullmatch(r"[a-z_ ]{1,40}", label) else "fetch")
    return sorted(set(labels))


def render_pick_card(c: ms.Candidate, d: Dict, idx: int) -> str:
    ticker = c.ticker
    ticker_url = f"https://walterLiu168.github.io/stock-report/market-screen-2026-08-12.html#{ticker}"
    headline = render_pick_header(c)
    fetch_errors = d.get("fetch_errors", [])
    if fetch_errors:
        headline += '<div role="status" style="padding:8px;color:var(--amber)">部分補充資料取得失敗：' + _esc("；".join(fetch_error_sources(fetch_errors))) + '</div>'
    tags = render_tags_bar(c)
    # Section tabs (chart-enhanced)
    sections = {
        "zen": ("🧘 纏論", render_zen_chart_section(c.ticker, c)),
        "tech": ("📈 技術", render_technical_section(c.ticker)),
        "val": ("💰 估值", render_valuation_section(c)),
        "inst": ("🏛 法人", render_institutional_section(c.ticker)),
        "marg": ("💴 融資", render_margin_chart_section(c.ticker, d)),
        "fin": ("📊 季報", render_financial_chart_section(d)),
        "fl_roe": ("🧬 ROE", render_finlab_roe_chart(d)),
        "fl_rev": ("📈 月營收", render_finlab_revenue_chart(d)),
        "div": ("💵 配息", render_dividend_chart_section(d)),
        "news": ("📰 新聞", render_news_section(d, ticker=c.ticker, limit=5)),
        "obs": ("💡 觀察", render_observations(d)),
        "dd": ("🔬 Deep-dive", render_deep_dive_prompt(c)),
    }
    tab_btns = []
    sec_htmls = []
    for i, (k, (label, raw_content)) in enumerate(sections.items()):
        active = "active" if i == 0 else ""
        tab_btns.append(f'<button class="{active}" data-sec="{k}">{label}</button>')
        # Post-process: convert markdown tables to styled HTML
        content = beautify_section_html(raw_content)
        sec_htmls.append(f'<div class="section {active}" data-sec="{k}"><h5>{label}</h5>{content}</div>')

    actions = f"""
    <div class="actions">
      <a href="https://walterLiu168.github.io/stock-report/market-screen-2026-08-12.html#{ticker}" target="_blank">📊 Market Report</a>
      <a href="https://github.com/your-org/ticker-dashboard/blob/main/{ticker}.md" onclick="return false">🎛 Ticker Dashboard</a>
      <a href="https://walterLiu168.github.io/stock-report/wall-street-{ticker}.html" onclick="return false">🏛 Wall Street</a>
      <a href="https://walterLiu168.github.io/stock-report/research-{ticker}.md" onclick="return false">📋 Research</a>
    </div>
    """

    return f"""
    <div class="pick" id="pick-{ticker}-{c.horizon}" data-ticker="{ticker}" data-horizon="{c.horizon}" data-bucket="{_esc(c.bucket)}">
      {headline}
      <div class="pick-body">
        {tags}
        <div class="tabs2">
          {''.join(tab_btns)}
        </div>
        {''.join(sec_htmls)}
        {actions}
      </div>
    </div>
    """


# ---- per-bucket group ----

def _fetch_margin_distress_candidates(top_n: int = 10) -> List[Dict]:
    """從 outputs/margin_rebound/<date>.json 讀取 scan 結果。

    若 JSON 不存在（scan 還沒跑過），fallback 到 DB query 算簡化版。
    全 7 維度的 scan 結果由 src/margin_rebound/scan.py 產出。
    """
    import json
    # Try reading today's JSON (scripts/outputs/margin_rebound/<date>.json)
    today = date.today().isoformat()
    skill_root = Path(__file__).parent
    json_path = skill_root / "outputs" / "margin_rebound" / f"{today}.json"
    if json_path.exists():
        try:
            d = json.loads(json_path.read_text(encoding="utf-8"))
            candidates = d.get("candidates", [])
            return candidates[:top_n]
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback: simple DB query (old behavior)
    return _fetch_margin_distress_fallback(top_n)


def _fetch_margin_distress_fallback(top_n: int = 10) -> List[Dict]:
    """Fallback: 從 DB 查詢融資反彈候選人（簡化版，不含多維度評分）。"""
    out = []
    with db.get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT
                d.Ticker, d.Date, d.Close, d.MarginBalance,
                d.ShortBalance, d.Volume,
                c.industry, c.company AS name
            FROM daily_data2_full d
            LEFT JOIN industry_type c ON d.Ticker = c.ticker
            WHERE d.Date = (SELECT MAX(Date) FROM daily_data2_full)
              AND d.MarginBalance >= 5000
              AND d.Close >= 5
              AND d.Volume >= 100
        """)
        latest = cur.fetchall()
        if not latest:
            return []
        tickers = [r["Ticker"] for r in latest]
        placeholders = ",".join(["%s"] * len(tickers))
        cur.execute(f"""
            SELECT Ticker, AVG(Close) AS avg_c
            FROM daily_data2_full
            WHERE Ticker IN ({placeholders})
              AND Date >= (SELECT MAX(Date) FROM daily_data2_full) - INTERVAL 120 DAY
            GROUP BY Ticker
        """, tuple(tickers))
        avg_costs = {r["Ticker"]: float(r["avg_c"]) for r in cur.fetchall() if r.get("avg_c")}

    for r in latest:
        t = r["Ticker"]
        avg_c = avg_costs.get(t, 0)
        if avg_c <= 0:
            continue
        close = float(r["Close"])
        margin = int(r["MarginBalance"])
        maint_pct = close / avg_c * 100
        if maint_pct >= 133:
            continue
        out.append({
            "ticker": t,
            "name": r.get("name") or t,
            "industry": r.get("industry") or "—",
            "close": close,
            "margin_張": margin,
            "margin_市值_億": round(margin * close * 1000 / 1e8, 2),
            "avg_cost_120d": round(avg_c, 2),
            "maint_rate": round(maint_pct, 1),
            "composite": round(maint_pct / 1.33, 1),  # simple proxy
            "scores": {"maint_rate": round(max(0, 100 - (maint_pct - 100) * 2), 1)},
        })
    out.sort(key=lambda x: x.get("margin_市值_億", 0), reverse=True)
    return out[:top_n]


def _render_margin_tab(candidates: List[Dict]) -> str:
    """Render the 🎯 潛在反彈 tab content (uses multi-dim scan results).

    D025: 顯示 tier 標籤 + 進場天數 badge（🆕 新進 / 🔥 持續 / ⚠️ 持續 8+ 天）。
    Group by tier (Tier 1 strict < 130% first, then Tier 2 warning 130-150% 連 3 日下降).
    """
    if not candidates:
        return '<div class="tab-content" data-bucket="margin">無候選人</div>'

    # Group by tier
    tier1 = [c for c in candidates if c.get("tier") == 1 or c.get("maint_rate") is not None and c.get("maint_rate") < 130]
    tier2 = [c for c in candidates if c not in tier1]
    sections = []
    for label, group, badge_color, desc in [
        ("🎯 Tier 1: 維持率 < 130%（斷頭區）", tier1, "red", "已觸及追繳線，強制賣壓大"),
        ("⚠️ Tier 2: 130-150% 連 3 日融資下降（警示區）", tier2, "yellow", "接近追繳且融資持續減，可能是早進場訊號"),
    ]:
        if not group:
            continue
        cards = []
        for c in group:
            # Color: 維持率 紅色 (台灣慣例 — 維持率低 = 紅 = 反彈機會)
            maint = c.get("maint_rate")
            maint_s = f"{maint:.1f}%" if maint is not None else "—"
            score = c.get("composite", 0)
            # D025: 進場天數 badge (Taiwan color convention: 紅=新/正, 綠=舊/負)
            days = c.get("days_on_list", 0) or 0
            if days <= 2:
                # 新進 — 紅色 (台灣慣例 = 正/新)
                days_badge = '<span class="chip chip-pos">🆕 新進 ' + ('今' if days == 0 else f'{days} 天') + '</span>'
            elif days <= 7:
                # 持續中 — 黃色 (注意)
                days_badge = f'<span class="chip chip-neu">🔥 持續 {days} 天</span>'
            else:
                # 持續 8+ 天 — 綠色 (台灣慣例 = 負/舊/失去新鮮感)
                days_badge = f'<span class="chip chip-neg">⚠️ 持續 {days} 天</span>'
            # 顯示每個維度的分數
            scores = c.get("scores", {})
            score_chips = ""
            if scores:
                chips = []
                label_map = {
                    "maint_rate": "📏維持率",
                    "margin_change_1d": "📉1d融資",
                    "margin_change_3d": "📉3d融資",
                    "bias": "📐Bias",
                    "rsi": "RSI",
                    "boll": "布林",
                    "volume_shadow": "💥爆量",
                }
                for k, lbl in label_map.items():
                    if k in scores:
                        s = scores[k]
                        cls = "pos" if s >= 70 else ("neu" if s >= 40 else "neg")
                        chips.append(f'<span class="chip chip-{cls}">{lbl} {s:.0f}</span>')
                score_chips = '<div class="pick-chips">' + " ".join(chips) + '</div>'

            # Tier label
            tier_label = '<span class="chip" style="background:rgba(236,112,99,0.18);color:#ec7063">Tier 1</span>' if c.get("tier") == 1 else '<span class="chip" style="background:rgba(245,176,65,0.18);color:#f5b041">Tier 2</span>'

            cards.append(f"""
        <div class="pick">
          <div class="pick-head">
            <span class="pick-ticker">{_esc(c['ticker'])}</span>
            <span class="pick-name">{_esc(c.get('company') or c.get('name', c['ticker']))}</span>
            <span class="pick-industry muted">{_esc(c.get('industry') or '—')}</span>
            {tier_label}
            {days_badge}
            <span class="pick-score" style="background:var(--acc);color:#000;padding:2px 8px;border-radius:10px;font-weight:700;font-size:0.78rem">Score {score:.0f}</span>
            <a class="analyze-link" href="analyze/{_esc(c['ticker'])}.html" target="_blank">🔍 分析 →</a>
          </div>
          <div class="pick-grid">
            <div class="pick-cell">
              <div class="k">收盤</div>
              <div class="v">{c['close']:,.2f}</div>
            </div>
            <div class="pick-cell">
              <div class="k">120d 平均成本</div>
              <div class="v muted">{c.get('avg_cost_120d', 0):,.2f}</div>
            </div>
            <div class="pick-cell">
              <div class="k">📏 估維持率</div>
              <div class="v pos" style="font-weight:700">{maint_s}</div>
            </div>
            <div class="pick-cell">
              <div class="k">📉 1d 融資變化</div>
              <div class="v {'pos' if c.get('margin_chg_1d_pct', 0) > 0 else 'neg' if c.get('margin_chg_1d_pct', 0) < 0 else ''}">{c.get('margin_chg_1d_pct', 0):+.1f}%</div>
            </div>
            <div class="pick-cell">
              <div class="k">📐 Bias</div>
              <div class="v {'pos' if c.get('bias_pct', 0) > 0 else 'neg' if c.get('bias_pct', 0) < 0 else ''}">{c.get('bias_pct', 0):+.1f}%</div>
            </div>
            <div class="pick-cell">
              <div class="k">RSI</div>
              <div class="v">{c.get('rsi', 0):.0f}</div>
            </div>
            <div class="pick-cell">
              <div class="k">融資張數</div>
              <div class="v">{c.get('margin_張', 0):,}</div>
            </div>
          </div>
          {score_chips}
          <div class="pick-meta muted" style="font-size:0.78rem;line-height:1.7;display:flex;flex-wrap:wrap;gap:4px 12px">
            <span>融資 {c.get('margin_張', 0):,} 張</span>
            <span>市值 {c.get('margin_市值_億', 0):,.1f} 億</span>{f'<span>進場 {c.get("first_seen", "")}</span>' if c.get('first_seen') else ''}
          </div>
        </div>""")
        sections.append(f"""
        <h3 style="margin:18px 0 8px;color:var(--{'green' if badge_color=='red' else 'amber'});font-size:0.95rem">{label} <small class="muted" style="font-weight:400">{desc} · {len(group)} 檔</small></h3>
        <div class="picks">{''.join(cards)}</div>""")
    return f"""
    <div class="tab-content" data-bucket="margin">
      <h2 class="bucket-title">🎯 潛在反彈候選 <small>7 維度評分 (維持率 / 融資變化 / Bias / RSI / 布林 / 量價 / 集保*)</small></h2>
      <p class="muted" style="font-size:0.82rem;margin:4px 0 12px">*集保戶數 / 千張大戶需 TDCC 申報資料，目前沒接入。每日 22:25 自動更新。<br>
      <b>Tier 1</b> 維持率 &lt; 130%（斷頭區）；<b>Tier 2</b> 130-150% 連 3 日融資下降（警示區）。進場天數：<span class="chip chip-pos">🆕 新進</span> ≤ 2 天 / <span class="chip chip-neu">🔥 持續</span> 3-7 天 / <span class="chip" style="background:rgba(110,118,130,0.15);color:#8b949e">⚠️ 持續 8+ 天</span>。</p>
      {''.join(sections)}
    </div>"""


def render_bucket(bucket_label: str, picks: List[ms.Candidate], data_map: Dict[str, Dict], idx_offset: int) -> str:
    BUCKET_META = {
        "<100": ("💰 銅板股", "高波動、題材驅動，短中期操作為主"),
        "100-300": ("💵 中價股", "主流操作區間，流動性佳"),
        "300-1000": ("💎 中高價", "基本面與成長性兼具，適合中期持有"),
        ">1000": ("🏆 高價股", "龍頭企業、法人重倉、波動相對小"),
    }
    title, desc = BUCKET_META.get(bucket_label, (bucket_label, ""))
    cards = []
    for i, c in enumerate(picks):
        d = data_map.get(c.ticker, {})
        cards.append(render_pick_card(c, d, idx_offset + i))
    return f"""
    <div class="tab-content" data-bucket="{bucket_label}">
      <h2 class="bucket-title">{title} <small>{desc}</small></h2>
      <div class="picks">{''.join(cards)}</div>
    </div>
    """


# ---- main ----

def main(groove_only: bool = False):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    import os
    import pipeline_state as ps
    snapshot = ps.db_snapshot()
    # Use the actual data date (last trading day in DB) instead of today's date.
    # DB may not have today's data if rendered before market close or on holidays.
    data_date = os.environ.get("TW_DATA_DATE") or snapshot["data_date"]
    if data_date != snapshot["data_date"]:
        raise RuntimeError("watchlist source changed during nightly")
    today = data_date
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[1/4] Loading active picks from DB + screen…")
    perf = wl.get_performance_report()
    rows = [r for r in perf["picks"] if str(r["run_date"]) == today]
    if not rows:
        raise RuntimeError("No active picks for data date")
    print(f"  {len(rows)} active picks")

    # Render the committed picks, never silently replace/drop them by re-screening.
    snaps = {r["Ticker"]: r for r in db.market_snapshot(today)}
    industries = db.all_industries()
    shares = db.all_shares_outstanding()
    chips = db.all_latest_chipscore(today)
    features = db.all_latest_features(today)
    bucket_picks = {b: [] for b in ("<100", "100-300", "300-1000", ">1000")}
    for pick in snapshot["picks"]:
        ticker = pick["ticker"]
        if ticker not in snaps:
            raise RuntimeError(f"pick {ticker} has no OHLCV for {today}")
        c = ms.build_candidate(snaps[ticker], industries, shares)
        c.horizon, c.bucket = pick["horizon"], pick["bucket"]
        ms.enrich_from_chip_map(c, chips)
        ms.enrich_from_features_map(c, features)
        bucket_picks[c.bucket].append(c)
    committed_candidates = [c for group in bucket_picks.values() for c in group]
    ms.enrich_long_term_returns(committed_candidates, today)
    news_target_date = os.environ.get("TW_NEWS_DATE") or today
    ms.enrich_news_for_picks(committed_candidates, news_target_date)
    for c in committed_candidates:
        try:
            result = ms.zen.analyze(c.ticker, days=120)
            c.zen_position, c.zen_bias = result.position, result.bias
            if result.center:
                c.zen_center = f"{result.center.low:.2f}–{result.center.high:.2f}"
            c.zen_summary = ms.zen.format_read(result)
        except Exception as e:
            c.zen_summary = f"zen 分析失敗: {e}"
    # Sort each bucket: long first, then short
    for k in bucket_picks:
        bucket_picks[k].sort(key=lambda x: (0 if x.horizon == "long" else 1, x.ticker))

    # Group DB picks by ticker for performance summary
    perf_map = {r["ticker"]: r for r in rows}

    # ---- Step 3: parallel deep-dive fetch ----
    print(f"[3/4] Fetching supplemental data for {sum(len(v) for v in bucket_picks.values())} picks (bounded)…", flush=True)
    all_picks = [c for v in bucket_picks.values() for c in v]
    t0 = time.time()
    data_map = fetch_tickers(c.ticker for c in all_picks)
    # One bounded canonical-news query for all 24 picks. Calling
    # news_for_tickers once per card would repeat the same 50k-row scan.
    try:
        canonical_news = db.news_for_tickers(
            [c.ticker for c in all_picks], limit_per=5, days=5,
            target_date=news_target_date,
        )
        canonical_news_error = None
    except Exception as exc:
        canonical_news = {}
        canonical_news_error = str(exc)
    for candidate in all_picks:
        details = data_map.setdefault(candidate.ticker, {})
        details["_canonical_news"] = canonical_news.get(candidate.ticker, [])
        if canonical_news_error:
            details["_canonical_news_error"] = canonical_news_error

    # ---- Step 4: render + write ----
    print(f"[4/4] Rendering HTML…")
    tabs_html = []
    contents_html = []
    # First tab: 潛在反彈 (margin distress candidates) — highest priority
    # D025: margin tab 顯示更多 (Tier 1 strict + Tier 2 warning, 總共 ~60 張)
    margin_candidates = _fetch_margin_distress_candidates(top_n=60)
    if margin_candidates:
        active = "active"  # first tab = default open
        tabs_html.append(f'<button class="tab {active}" data-bucket="margin">🎯 潛在反彈 <span class="count">{len(margin_candidates)}</span></button>')
        contents_html.append(_render_margin_tab(margin_candidates))
    for i, bucket_label in enumerate(["<100", "100-300", "300-1000", ">1000"]):
        items = bucket_picks.get(bucket_label, [])
        if not items: continue
        active = "active" if i == 0 and not margin_candidates else ""
        tabs_html.append(f'<button class="tab {active}" data-bucket="{bucket_label}">{bucket_label} 元 <span class="count">{len(items)}</span></button>')
        contents_html.append(render_bucket(bucket_label, items, data_map, i * 10))

    # Summary stats
    rets = [perf_map.get(c.ticker, {}).get("ret_since_pick") for c in all_picks if perf_map.get(c.ticker, {}).get("ret_since_pick") is not None]
    avg = sum(rets) / len(rets) if rets else 0
    wins = sum(1 for r in rets if r > 0)
    winrate = wins / len(rets) * 100 if rets else 0

    summary_cards = f"""
    <div class="summary-bar">
      <div class="card"><div class="k">活躍 picks</div><div class="v">{len(all_picks)}</div></div>
      <div class="card"><div class="k">長期 / 短中期</div><div class="v">{sum(1 for c in all_picks if c.horizon=='long')} / {sum(1 for c in all_picks if c.horizon=='short')}</div></div>
      <div class="card"><div class="k">平均報酬</div><div class="v" style="color:{'var(--green)' if avg>0 else 'var(--red)'}">{avg*100:+.2f}%</div></div>
      <div class="card"><div class="k">勝率</div><div class="v">{winrate:.0f}%</div></div>
      <div class="card"><div class="k">資料日</div><div class="v">{today}</div></div>
      <div class="card"><div class="k">最後更新</div><div class="v" style="font-size:0.95rem">{now[11:]}</div></div>
    </div>
    """

    skillbar = "".join(f'<span class="sk" title="{_esc(desc)}">{_esc(name)}</span>' for name, desc in SKILL_LINKS)

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>台股深度選股 · {today} · 24 檔</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
    <div class="brand">📊 台股深度選股 <small>tw-invest-suite · market screen + single-stock deep-dive · {today}</small></div>
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <a href="readme.html" style="background:rgba(95,177,255,0.15);color:var(--acc);border:1px solid var(--border);border-radius:6px;padding:6px 12px;font-size:0.85rem;font-weight:600;text-decoration:none;white-space:nowrap">📖 關於本站</a>
      <a href="https://groovelab.dev/analyze/patterns.html" target="_blank" style="background:rgba(57,197,207,0.18);color:var(--cyan);border:1px solid var(--cyan);border-radius:6px;padding:6px 12px;font-size:0.85rem;font-weight:600;text-decoration:none;white-space:nowrap">📊 型態搜尋 →</a>
      <form class="search-form" action="https://groovelab.dev/analyze.html" method="get" target="_blank" style="display:flex;gap:6px">
        <input name="ticker" placeholder="個股代號 e.g. 2324" maxlength="6" required style="background:var(--panel);color:var(--ink);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:0.85rem;width:160px;font-family:inherit">
        <button type="submit" style="background:var(--acc);color:#000;border:none;border-radius:6px;padding:6px 12px;font-size:0.85rem;font-weight:600;cursor:pointer">🔍 分析個股 →</button>
      </form>
    </div>
  </div>
  <div class="skillbar">{skillbar}</div>
</div>
<div class="tabs">{''.join(tabs_html)}</div>
<main>
  {summary_cards}
  {''.join(contents_html)}
  <footer>tw-invest-suite · {now} · Generated by Mavis · 24 檔深度報告 + 14 skill 視角</footer>
</main>
<script>
document.querySelectorAll('.tab').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const b = btn.dataset.bucket;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('.tab-content[data-bucket="' + b + '"]').classList.add('active');
  }});
}});
document.querySelectorAll('.tabs2').forEach(group => {{
  group.querySelectorAll('button').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const sec = btn.dataset.sec;
      const card = btn.closest('.pick');
      group.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      card.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      card.querySelector('.section[data-sec="' + sec + '"]').classList.add('active');
    }});
  }});
}});
function copyText(btn) {{
  const pre = btn.nextElementSibling;
  const text = pre.textContent;
  navigator.clipboard.writeText(text).then(() => {{
    const orig = btn.textContent;
    btn.textContent = '✓ 已複製';
    setTimeout(() => btn.textContent = orig, 1500);
  }}).catch(err => alert('複製失敗：' + err));
}}
</script>
</body>
</html>"""

    # Write outputs
    groove = GROOVE_WATCHLIST
    groove.write_text(html_doc, encoding="utf-8")
    print(f"  → {groove} ({len(html_doc):,} bytes)")

    if not groove_only:
        reports_dir = REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)
        out1 = reports_dir / f"watchlist-full-{today}.html"
        out1.write_text(html_doc, encoding="utf-8")
        print(f"  → {out1} ({len(html_doc):,} bytes)")

        public = ps.PUBLIC
        (public / "watchlist.html").write_text(html_doc, encoding="utf-8")
        ps.atomic_json(public / "data" / "watchlist-full.json", {
            "nightly_id": os.environ.get("TW_NIGHTLY_ID", "manual"),
            "data_date": today, "run_id": snapshot["run_id"], "picks": snapshot["picks"],
            "html_sha256": ps.sha256(public / "watchlist.html"),
            "fetch_errors": {t: fetch_error_sources(d["fetch_errors"]) for t, d in data_map.items() if d.get("fetch_errors")},
        })

    # Stats
    total_errs = sum(len(d.get("fetch_errors", [])) for d in data_map.values())
    print(f"\n✅ Done. {len(all_picks)} picks, fetch_errors={total_errs}, total time {time.time()-t0:.0f}s")
    print(f"📱 Phone: https://groovelab.dev/watchlist.html")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--groove-only", action="store_true",
        help="update only C:\\Groove-Lab\\watchlist.html; preserve certified public artifacts",
    )
    main(groove_only=parser.parse_args().groove_only)
```

### news_refresh_watchlist.py

來源：`C:\Users\icemo\Projects\tw-invest-suite\scripts\news_refresh_watchlist.py`

```python
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
```

### register_news_refresh.ps1

來源：`C:\Users\icemo\Projects\tw-invest-suite\scripts\register_news_refresh.ps1`

```powershell
#requires -Version 5.1
[CmdletBinding()]
param([switch]$Unregister, [switch]$SelfCheck)
$ErrorActionPreference = 'Stop'
$TaskName = 'tw-invest-suite-news-refresh'
$ScriptDir = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
$Cmd = Join-Path $ScriptDir 'news_refresh_watchlist.py'
if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Unregistered $TaskName"
  exit 0
}
if ($SelfCheck) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Select-Object TaskName,State,@{N='UserId';E={$_.Principal.UserId}},@{N='LogonType';E={$_.Principal.LogonType}},@{N='RunLevel';E={$_.Principal.RunLevel}},@{N='Triggers';E={$_.Triggers.Count}} | ConvertTo-Json -Compress
    } else {
        Write-Output "MISSING: $TaskName"
    }
    exit 0
}
if (-not (Test-Path -LiteralPath $Cmd)) { throw "Missing launcher: $Cmd" }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run this from an elevated PowerShell (right-click / Run as administrator).' }
$action = New-ScheduledTaskAction -Execute 'C:\Python314\python.exe' -Argument "-X utf8 `"$Cmd`"" -WorkingDirectory $ScriptDir
# Eight independent daily triggers: 08, 10, 12, 14, 16, 18, 20 and 22.
$triggers = @()
foreach ($hour in 8, 10, 12, 14, 16, 18, 20, 22) {
    $triggers += New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour $hour -Minute 0 -Second 0)
}
if ($triggers.Count -ne 8) { throw "Expected 8 triggers, got $($triggers.Count)" }
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'News-only refresh for the live C:\Groove-Lab\watchlist.html. Preserves certified public artifacts and does not push GitHub Pages.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State,@{N='UserId';E={$_.Principal.UserId}},@{N='LogonType';E={$_.Principal.LogonType}},@{N='Triggers';E={$_.Triggers.Count}} | ConvertTo-Json -Compress
```

### publish_ghpages_daily.ps1

來源：`C:\Users\icemo\Projects\tw-invest-suite\scripts\publish_ghpages_daily.ps1`

```powershell
# The only scheduled publisher. Wait for the actual nightly, then certify and publish.
# WaitMinutes budget covers the typical 21:30 → about 23:02 nightly duration
# plus a safety margin. The 22:50 publisher normally waits about 12 minutes;
# a 130-minute budget gives it an absolute 01:00 deadline. Set to 10 only for manual one-off debugging
# when you know the chain is already finished.
[CmdletBinding()]
param([switch]$PrepareOnly, [int]$WaitMinutes = 130)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
Set-Location 'C:\Users\icemo\Projects\tw-invest-suite\scripts'
$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ((Get-ScheduledTask -TaskName 'tw-invest-suite-daily-report').State -eq 'Running') {
    if ((Get-Date) -ge $deadline) { Write-Error 'Nightly still running at publish deadline'; exit 1 }
    Start-Sleep -Seconds 15
}
& C:\Python314\python.exe pipeline_state.py verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = Join-Path $PSScriptRoot "_debug\publish_ghpages_$ts.log"
$flag = if ($PrepareOnly) { '--prepare-only' } else { '--publish' }
& C:\Python314\python.exe publish_ghpages.py $flag 2>&1 | Tee-Object -FilePath $log
$rc = $LASTEXITCODE
Add-Content -LiteralPath $log -Value "publish_ghpages_daily.ps1 done (exit $rc)" -Encoding UTF8
exit $rc
```

### pipeline_state.py

來源：`C:\Users\icemo\Projects\tw-invest-suite\scripts\pipeline_state.py`

```python
"""Daily run identity and verified artifacts. No DB writes or publication here."""
import argparse
from contextlib import contextmanager
from functools import wraps
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from market_calendar import expected_session, is_session

REPO = Path(r"C:\Users\icemo\Projects\tw-invest-suite")
RUNTIME = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
PUBLIC = REPO / "public"
REPORTS = RUNTIME.parent / "reports"
ANALYZE = Path(r"C:\Groove-Lab\analyze")
STATE = RUNTIME / "_debug" / "pipeline_run.json"
MARKER = RUNTIME / "_debug" / "last_completed.json"
BUCKETS = {"<100", "100-300", "300-1000", ">1000"}
REQUIRED = {"render", "patterns", "patterns_html", "watchlist", "all_reports"}
REPO_SOURCE_FILES = (
    'src/margin_rebound/finmind_maint.py', 'src/margin_rebound/scan.py',
    'src/all_reports.py', 'src/report_inputs.py', 'src/chip_rank.py',
    'src/chip_advanced.py', 'src/sector_aggregate.py', 'src/build_ticker_meta.py',
    'src/concept_stocks.py', 'src/render_concepts.py', 'src/render_chips_advanced.py',
    'src/industry_zh.py', 'src/generate_og.py', 'src/chip_push.py',
)
REPORT_FRONTEND_FILES = ('analyze.html','readme.html','chips-history.html','monitor.html',
                         'manifest.json','sw.js','assets/textsize.css','assets/textsize.js')
SOURCE_FILES = (
    "run_daily.ps1", "run_stage.py", "pipeline_state.py", "render_only.py",
    "render_full_watchlist.py", "pattern_classifier.py", "build_patterns_html.py",
    "publish_ghpages_daily.ps1", "publish_ghpages.py", "publish_manifest.py",
    "postflight_daily.py", "daily_summary.py", "build_dashboard.py",
    "marker_watchdog_daily.ps1", "cross_source_runner.py", "market_calendar.py",
    "market_screen_runner.py",
    "render_ticker_full.py", "daily_full_tickers.py",
    "market_report.py", "market_report_html.py",
    "bounded_deep_dive.py",
    "nightly_health.py", "nightly_health_daily.ps1",
    "check_openalice_health.py", "db_client.py", "deep_dive_prompts.py", "market_screen.py",
    "process_lifecycle.ps1", "publish_verified_sites.ps1", "sync_groove_release.py",
    "metadata_backfill_daily.ps1", "metadata_backfill.py", "market_screen_daily.ps1",
    "company_refresh_daily.ps1", "company_refresh.py", "daily_certification_catchup.py", "postflight_daily.ps1",
    "sync_legacy_tables_runner.ps1", "sync_legacy_tables.py",
    "yfinance_daily.py", "yfinance_batch.py", "cache_manager.py",
    "finmind_batch.py", "finmind_client.py",
    "groove_service_watch.ps1", "news_refresh_watchlist.py",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def owner_running(run):
    """Use a live process handle, not just a stale 'running' JSON field."""
    if run.get("status") != "running" or not run.get("owner_pid"):
        return False
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(run["owner_pid"]))
    if not handle:
        if ctypes.get_last_error() == 5:
            return owner_creation_matches(run, cim_process_creation_time(run['owner_pid']))
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)) or code.value != 259:
            return False
        created = process_creation_time(run["owner_pid"])
        return owner_creation_matches(run, created)
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def owner_creation_matches(run, created):
    if not created:
        return False
    actual = datetime.fromisoformat(created)
    if run.get('owner_created_at'):
        # FILETIME float conversion and CIM truncation differ by at most 1us.
        return abs(actual - datetime.fromisoformat(run['owner_created_at'])) <= timedelta(microseconds=2)
    if run.get('started_at'):
        return timedelta(seconds=-2) <= datetime.fromisoformat(run['started_at']) - actual <= timedelta(minutes=2)
    return True


def cim_process_creation_time(pid):
    """Read public process identity when another logon denies OpenProcess."""
    import subprocess
    command = (f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' -ErrorAction Stop;"
               "if($p){$p.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss.ffffff')}")
    result = subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                             '-NoProfile', '-Command', command], capture_output=True, text=True,
                            timeout=10, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError('Cannot verify process identity through CIM')
    created = result.stdout.strip()
    if created:
        datetime.fromisoformat(created)
    return created or None


def process_creation_time(pid):
    import ctypes
    from ctypes.wintypes import FILETIME
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        if ctypes.get_last_error() == 5:
            return cim_process_creation_time(pid)
        return None
    try:
        times = [FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(ctypes.c_void_p(handle), *(ctypes.byref(t) for t in times)):
            return None
        ticks = (times[0].dwHighDateTime << 32) + times[0].dwLowDateTime
        return datetime.fromtimestamp((ticks - 116444736000000000) / 10000000).isoformat()
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(f.read()).hexdigest()


def source_hashes():
    result = {}
    for name in SOURCE_FILES:
        source, runtime = REPO / "scripts" / name, RUNTIME / name
        digest = sha256(source)
        if not runtime.is_file() or sha256(runtime) != digest:
            raise ValueError(f"runtime/repo SHA mismatch: {name}")
        result[name] = digest
    for name in REPO_SOURCE_FILES:
        result[name] = sha256(REPO / name)
    for name in REPORT_FRONTEND_FILES:
        result['public/' + name] = sha256(PUBLIC / name)
    result['AI-Telegram/strategy_lab/finmind_batch_update.py'] = sha256(Path(r'D:\CODEX\AI-Telegram\strategy_lab\finmind_batch_update.py'))
    return result


class PickParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.picks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        # Margin candidates also use class=pick, but are not committed screen picks.
        # Count identified screen cards even if an identity attribute is missing,
        # so malformed committed cards still fail the multiset validation.
        if tag == "div" and "pick" in attrs.get("class", "").split() and attrs.get("id", "").startswith("pick-"):
            self.picks.append(tuple(attrs.get(k) for k in ("data-ticker", "data-horizon", "data-bucket")))


def validate_watchlist(body, picks):
    parser = PickParser()
    parser.feed(body)
    expected = Counter((p["ticker"], p["horizon"], p["bucket"]) for p in picks)
    if len(parser.picks) != 24 or Counter(parser.picks) != expected:
        raise ValueError("watchlist HTML does not contain the 24 committed picks")


def db_snapshot():
    import db_client as db
    with db.get_cursor() as c:
        c.execute("SELECT MAX(Date) AS d FROM daily_data2_full")
        data_date = str(c.fetchone()["d"])
        c.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT Ticker) AS tickers FROM daily_data2_full WHERE Date=%s", (data_date,))
        coverage = c.fetchone()
        c.execute("SELECT id,run_date,picks_count FROM market_screen_runs WHERE run_date=%s ORDER BY id DESC LIMIT 1", (data_date,))
        run = c.fetchone()
        if not run:
            raise ValueError(f"no screen run for {data_date}")
        c.execute("SELECT ticker,horizon,bucket,status FROM market_screen_picks WHERE run_id=%s ORDER BY bucket,horizon,ticker", (run["id"],))
        picks = c.fetchall()
        c.execute("SELECT ticker FROM industry_type WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$' ORDER BY ticker")
        render_tickers = [row['ticker'] for row in c.fetchall()]
    groups = Counter((p["bucket"], p["horizon"]) for p in picks)
    expected = {(b, h): 3 for b in BUCKETS for h in ("long", "short")}
    if run["picks_count"] != 24 or len(picks) != 24 or groups != expected:
        raise ValueError(f"invalid picks for run {run['id']}: {dict(groups)}")
    if any(p["status"] != "active" for p in picks):
        raise ValueError("inactive picks in current run")
    if coverage["tickers"] < 1900:
        raise ValueError(f"OHLCV coverage insufficient: {coverage}")
    return {"data_date": data_date, "run_id": run["id"], "picks_count": 24,
            "bucket_counts": {b: 6 for b in sorted(BUCKETS)}, "picks": picks,
            "ohlcv_rows": coverage["n"], "ohlcv_tickers": coverage["tickers"], "render_tickers": render_tickers}


@contextmanager
def state_lock():
    """Serialize begin/complete/fail with watchdog recovery across processes."""
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, "Local\\TwInvestSuiteDailyState")
    if not handle:
        raise OSError("cannot open daily state mutex")
    acquired = False
    try:
        result = kernel.WaitForSingleObject(ctypes.c_void_p(handle), 10000)
        if result not in (0, 0x80):
            raise TimeoutError("daily state mutex unavailable")
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(ctypes.c_void_p(handle))
        kernel.CloseHandle(ctypes.c_void_p(handle))


def state_guarded(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with state_lock():
            return function(*args, **kwargs)
    return guarded


@state_guarded
def begin(mode="full"):
    now = datetime.now()
    execution_day = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    run = {"nightly_id": uuid.uuid4().hex, "started_at": now.isoformat(),
           "execution_date": execution_day.isoformat(), "status": "running", "mode": mode,
           "owner_pid": int(os.environ.get("TW_OWNER_PID", "0")), "trading_session": is_session(execution_day)}
    run["owner_created_at"] = process_creation_time(run["owner_pid"]) if run["owner_pid"] else None
    # Invalidate publish eligibility before preflight, including preflight failures.
    atomic_json(STATE, run)
    try:
        run.update(db_snapshot())
        if run["data_date"] != expected_session(execution_day):
            raise ValueError(f"upstream stale: expected {expected_session(execution_day)}, got {run['data_date']}")
        run["source_hashes"] = source_hashes()
        atomic_json(STATE, run)
        return run
    except Exception as e:
        run.update(status="failed", error=str(e))
        atomic_json(STATE, run)
        raise


def artifact(path, gh_path):
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"missing/empty artifact: {path}")
    return {"gh_path": gh_path, "abs_path": str(path), "exists": True,
            "sha256": sha256(path), "size": path.stat().st_size}


def canonical_inputs_hash(data_date):
    """Detect canonical value changes while reports are being generated."""
    import db_client as db
    fields = ('Ticker,Date,Open,High,Low,Close,Volume,ForeignBuy,ForeignSell,ForeignNet,'
              'InvestmentBuy,InvestmentSell,InvestmentNet,DealerBuy,DealerSell,DealerNet,ThreeNet,'
              'MarginBalance,ShortBalance,DayTradeVol,DayTradeBuyAmt,DayTradeSellAmt,'
              'ForeignRatio,ForeignShare,SharesOutstanding_shares')
    with db.get_cursor() as cursor:
        cursor.execute('SELECT DISTINCT Date FROM daily_data2_full WHERE Date<=%s ORDER BY Date DESC LIMIT 240', (data_date,))
        dates = [str(row['Date']) for row in cursor.fetchall()]
        if len(dates) < 30 or dates[0] != data_date:
            raise ValueError('Canonical input history/date incomplete')
        marks = ','.join(['%s'] * len(dates))
        cursor.execute(f'SELECT {fields} FROM daily_data2_full WHERE Date IN ({marks}) ORDER BY Date,Ticker', tuple(dates))
        digest = hashlib.sha256()
        for row in cursor.fetchall():
            digest.update(json.dumps(row, sort_keys=True, default=str, separators=(',', ':')).encode('utf-8'))
        cursor.execute('SELECT ticker,company,industry FROM industry_type ORDER BY ticker')
        digest.update(json.dumps(cursor.fetchall(), sort_keys=True, default=str, separators=(',', ':')).encode('utf-8'))
    return digest.hexdigest()


@state_guarded
def finalize_inputs():
    run = read_json(STATE)
    if run.get('status') != 'running' or os.environ.get('TW_NIGHTLY_ID') != run.get('nightly_id'):
        raise ValueError('Cannot finalize another or completed run')
    if run.get('inputs_finalized_at'):
        raise ValueError('Canonical inputs already finalized')
    if (ANALYZE / 'render_receipt.json').is_file() and read_json(ANALYZE / 'render_receipt.json').get('nightly_id') == run['nightly_id']:
        raise ValueError('Cannot finalize inputs after rendering')
    if source_hashes() != run['source_hashes']:
        raise ValueError('Source changed before input finalization')
    validate_maintenance_fetch(read_json(RUNTIME / '_debug' / 'maintenance_fetch.json'), run)
    validate_finance_fetch(read_json(RUNTIME / '_debug' / 'finance_fetch.json'), run)
    snapshot = db_snapshot()
    if snapshot['data_date'] != run['data_date'] or snapshot['render_tickers'] != run['render_tickers']:
        raise ValueError('Data date or metadata universe changed before finalization')
    run.update(snapshot)
    run['canonical_inputs_sha256'] = canonical_inputs_hash(run['data_date'])
    run['inputs_finalized_at'] = datetime.now().isoformat()
    atomic_json(STATE, run)
    return run


def validate_all_reports(receipt, run):
    if (receipt.get('status') != 'ok' or receipt.get('nightly_id') != run['nightly_id']
            or receipt.get('data_date') != run['data_date']):
        raise ValueError('All-report receipt identity/status mismatch')
    dates = receipt.get('history_dates', [])
    if len(dates) != 30 or len(set(dates)) != 30 or dates != sorted(dates, reverse=True) or dates[0] != run['data_date']:
        raise ValueError('All-report history coverage mismatch')
    if receipt.get('current_rows', 0) < 1900 or receipt.get('metadata_tickers') != len(run['render_tickers']):
        raise ValueError('All-report market coverage mismatch')
    if receipt.get('rank_tickers',0) < 1900 or receipt.get('advanced_tickers',0) <= 0:
        raise ValueError('All-report ranking/advanced coverage mismatch')
    expected = {'sectors.html','chips.html','chips-advanced.html','concepts.html',
        'data/sectors.json','data/chips.json','data/chips-advanced.json','data/concept-stocks.json',
        'data/tw-industry.json','data/tickers.json','data/chips-history-index.json','data/og.png'}
    expected.update(f'data/chips-history/{day}.json' for day in dates)
    expected.update(REPORT_FRONTEND_FILES)
    artifacts = receipt.get('artifacts', [])
    if len(artifacts) != len(expected) or {a['gh_path'] for a in artifacts} != expected:
        raise ValueError('All-report artifact set mismatch')
    for item in artifacts:
        path = (PUBLIC / item['gh_path']).resolve()
        if path != Path(item['abs_path']).resolve() or not path.is_relative_to(PUBLIC.resolve()) or sha256(path) != item['sha256']:
            raise ValueError('All-report artifact changed/unsafe')
        if path.suffix == '.json' and path.name != 'manifest.json':
            value = read_json(path)
            if isinstance(value,dict):
                expected_date = path.stem if path.parent.name == 'chips-history' else run['data_date']
                if value.get('date') != expected_date or value.get('nightly_id') != run['nightly_id']:
                    raise ValueError('All-report JSON identity mismatch')
            elif path.name == 'tickers.json':
                if sorted(v['ticker'] for v in value) != run['render_tickers'] or any(v.get('date') != run['data_date'] for v in value):
                    raise ValueError('Ticker metadata universe/date mismatch')
    return artifacts


def validate_maintenance_fetch(fetch, run):
    dd = run['data_date']
    if fetch.get('nightly_id') != run['nightly_id'] or fetch.get('requested_date') != dd or fetch.get('status') != 'ok' or not fetch.get('provider_rows') or fetch.get('api_errors') != 0:
        raise ValueError('maintenance fetch does not certify this run')
    if fetch.get('price_refresh_date') != dd or not isinstance(fetch.get('price_refresh_rows'), int) or fetch['price_refresh_rows'] < 1900:
        raise ValueError('maintenance price refresh does not certify this run')
    if (fetch.get('canonical_refresh_date') != dd or fetch.get('canonical_refresh_rows') != fetch['price_refresh_rows']
            or set(fetch.get('canonical_datasets', [])) != {'price','inst','margin','daytrade','shareholding','shares'}
            or fetch.get('source_value_mismatches') != 0):
        raise ValueError('maintenance canonical source values do not certify this run')
    if fetch.get('price_history_sessions') != 30 or fetch.get('price_history_mismatches') != 0:
        raise ValueError('maintenance price history does not certify this run')
    if (fetch.get('chips_history_sessions') != 30 or fetch.get('chips_history_mismatches') != 0
            or set(fetch.get('chips_history_datasets', [])) != {'inst','margin','daytrade','shareholding','shares'}):
        raise ValueError('maintenance chips history does not certify this run')
    synced = fetch.get('legacy_sync', {})
    if (synced.get('date') != dd or synced.get('rows') != fetch['canonical_refresh_rows']
            or synced.get('tables') != 4 or synced.get('mismatches') != 0):
        raise ValueError('maintenance derived table sync does not certify this run')
    valuation = fetch.get('valuation_refresh', {})
    if valuation.get('date') != dd or valuation.get('provider_tickers', 0) < 1500 or valuation.get('mismatches') != 0:
        raise ValueError('maintenance valuation source does not certify this run')
    source_date = date.fromisoformat(fetch['latest_source_date'])
    previous_session = date.fromisoformat(expected_session(date.fromisoformat(dd) - timedelta(days=1)))
    if not previous_session <= source_date <= date.fromisoformat(dd):
        raise ValueError('maintenance provider data is stale or future-dated')
    return source_date.isoformat()


def validate_finance_fetch(fetch, run):
    if (fetch.get('nightly_id') != run['nightly_id'] or fetch.get('data_date') != run['data_date']
            or fetch.get('status') != 'ok' or fetch.get('expected_tickers') != len(run['render_tickers'])
            or fetch.get('fresh_tickers',0) < 1900):
        raise ValueError('Valuation cache receipt does not certify this run')
    return fetch


@state_guarded
def complete(stages_path):
    run = read_json(STATE)
    try:
        stages = read_json(stages_path)
        if run["status"] != "running" or os.environ.get("TW_NIGHTLY_ID") != run["nightly_id"]:
            raise ValueError("run identity mismatch")
        required = [s for s in stages if not s.get("Optional")]
        if not REQUIRED.issubset({s["Name"] for s in required}) or any(not s["Ok"] for s in required):
            raise ValueError("required stage failed/missing")
        if run.get('mode') == 'full' and run.get('trading_session') and 'finmind_maint' not in {s['Name'] for s in required}:
            raise ValueError('Full trading-day certification requires canonical source refresh')
        snapshot = db_snapshot()
        if any(snapshot[k] != run[k] for k in ("data_date", "run_id", "picks", "render_tickers")):
            raise ValueError("DB changed during nightly")
        if source_hashes() != run["source_hashes"]:
            raise ValueError("source changed during nightly")
        receipt = read_json(ANALYZE / "render_receipt.json")
        if receipt["nightly_id"] != run["nightly_id"] or receipt["data_date"] != run["data_date"] or receipt["failures"]:
            raise ValueError("render receipt does not certify this run")
        if len(receipt["artifacts"]) != receipt["expected_count"] or receipt["expected_count"] < 1900:
            raise ValueError("incomplete render coverage")
        rendered = [Path(artifact['gh_path']).stem for artifact in receipt['artifacts']]
        if sorted(rendered) != run['render_tickers']:
            raise ValueError("render universe differs from the frozen metadata universe")
        if receipt.get("fresh_count", 0) < 1900:
            raise ValueError("fresh render coverage insufficient")
        artifacts = list(receipt["artifacts"])
        all_reports = read_json(RUNTIME / '_debug' / 'all_reports_receipt.json')
        artifacts += validate_all_reports(all_reports, run)
        for a in artifacts:
            if sha256(a["abs_path"]) != a["sha256"]:
                raise ValueError(f"render artifact changed: {a['gh_path']}")
        dd = run["data_date"]
        patterns = read_json(ANALYZE / "patterns.json")
        if patterns["as_of_date"] != dd or patterns.get("total_tickers", 0) < 1900:
            raise ValueError("patterns date/coverage mismatch")
        if patterns.get("nightly_id") != run["nightly_id"]:
            raise ValueError("patterns belongs to another nightly")
        watch = read_json(PUBLIC / "data" / "watchlist-full.json")
        if watch["nightly_id"] != run["nightly_id"] or watch["run_id"] != run["run_id"] or watch["picks"] != run["picks"]:
            raise ValueError("watchlist identity/picks mismatch")
        if watch["html_sha256"] != sha256(PUBLIC / "watchlist.html"):
            raise ValueError("watchlist HTML/receipt mismatch")
        validate_watchlist((PUBLIC / "watchlist.html").read_text(encoding="utf-8"), run["picks"])
        # Publish exactly the files the generators produced, not an older public mirror.
        pairs = [(ANALYZE / "patterns.json", "data/patterns.json"),
                 (ANALYZE / "patterns.html", "patterns.html"),
                 (ANALYZE / "patterns.html", "analyze/patterns.html"),
                 (ANALYZE / "patterns.json", "analyze/patterns.json"),
                 (ANALYZE / "index.html", "analyze/index.html"),
                 (PUBLIC / "watchlist.html", "watchlist.html"),
                 (PUBLIC / "data" / "watchlist-full.json", "data/watchlist-full.json")]
        for name in (f"market-screen-{dd}.html", f"market-screen-{dd}.md",
                     f"deep-dive-prompts-{dd}.md", f"watchlist-full-{dd}.html"):
            pairs.append((REPORTS / name, name))
        for src, dest in pairs:
            target = PUBLIC / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
            artifacts.append(artifact(target, dest))
        maintenance = {}
        if any(stage['Name'] == 'finmind_maint' for stage in required):
            if not {'valuation','market_screen','finalize_inputs'} <= {stage['Name'] for stage in required} or not run.get('inputs_finalized_at'):
                raise ValueError('Canonical refresh/picks were not finalized before rendering')
            if run.get('canonical_inputs_sha256') != canonical_inputs_hash(dd):
                raise ValueError('Canonical DB values changed during nightly')
            fetch = read_json(RUNTIME / '_debug' / 'maintenance_fetch.json')
            maintenance['maintenance_data_date'] = validate_maintenance_fetch(fetch, run)
            maintenance['finance_refresh'] = validate_finance_fetch(read_json(RUNTIME / '_debug' / 'finance_fetch.json'), run)
        run.update(status="ok", marker_version="D056-3", completed_at=datetime.now().isoformat(),
                   all_reports=all_reports,
                   stages=stages, degraded_stages=sum(not s["Ok"] for s in stages if s.get("Optional")),
                   render_data_issues=receipt.get("data_issues", []), render_count=receipt["expected_count"],
                   fresh_render_count=receipt["fresh_count"], render_numeric_issues=receipt.get("numeric_data_issues", {}),
                   watchlist_fetch_errors=watch.get("fetch_errors", {}), artifacts=artifacts, **maintenance)
        atomic_json(MARKER, run)
        atomic_json(STATE, run)
        return run
    except Exception as e:
        run.update(status="failed", error=str(e))
        atomic_json(STATE, run)
        raise


def verify_marker(marker=None, now=None, check_files=True):
    marker = marker if marker is not None else read_json(MARKER)
    run = read_json(STATE)
    now = now or datetime.now()
    execution_day = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    if marker.get("marker_version") != "D056-3" or marker.get("regenerated_by"):
        raise ValueError("uncertified/legacy marker")
    if marker.get("status") != "ok" or run.get("status") != "ok" or marker.get("nightly_id") != run.get("nightly_id"):
        raise ValueError("nightly is incomplete/failed or marker belongs to another run")
    if marker.get("execution_date") != execution_day.isoformat():
        raise ValueError("marker is from a previous nightly")
    started, completed = (datetime.fromisoformat(marker[k]) for k in ("started_at", "completed_at"))
    if not started <= completed <= now or completed - started > timedelta(hours=4):
        raise ValueError("invalid execution timestamps")
    if check_files:
        snapshot = db_snapshot()
        if any(snapshot[k] != marker[k] for k in ("data_date", "run_id", "picks", "render_tickers")):
            raise ValueError("marker/DB mismatch")
        if source_hashes() != marker["source_hashes"]:
            raise ValueError("marker/source SHA mismatch")
        if not marker.get("artifacts"):
            raise ValueError("marker has no artifacts")
        for a in marker["artifacts"]:
            if sha256(a["abs_path"]) != a["sha256"]:
                raise ValueError(f"artifact changed: {a['gh_path']}")
        validate_all_reports(marker.get('all_reports', {}), marker)
    return marker


@state_guarded
def fail_run(nightly_id, reason="orchestrator failed; see daily log"):
    value = read_json(STATE)
    if value.get("nightly_id") != nightly_id:
        raise ValueError("cannot fail another run")
    # Certification is terminal. Never resurrect a failed attempt from an old
    # marker, nor invalidate a committed success because reporting later failed.
    if value.get("status") == "ok":
        marker = read_json(MARKER)
        if (marker.get("nightly_id") == nightly_id and marker.get("status") == "ok"
                and marker.get("marker_version") == "D056-3"):
            return value
        raise ValueError("inconsistent completed state; refusing overwrite")
    value.update(status="failed", error=reason)
    atomic_json(STATE, value)
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["begin", "finalize-inputs", "complete", "verify", "watchdog", "fail"])
    ap.add_argument("--stages")
    ap.add_argument("--mode", default="full")
    args = ap.parse_args()
    try:
        if args.action == "begin":
            value = begin(args.mode)
        elif args.action == "finalize-inputs":
            value = finalize_inputs()
        elif args.action == "complete":
            value = complete(args.stages)
        elif args.action == "fail":
            value = fail_run(os.environ.get("TW_NIGHTLY_ID"))
        elif args.action == "watchdog" and STATE.exists() and owner_running(read_json(STATE)):
            print("PENDING: nightly process is still running; no completion marker fabricated")
            return 0
        else:
            value = verify_marker()
        print(json.dumps({k: value[k] for k in ("nightly_id", "data_date", "run_id", "status")}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

### TwPipelineMonitor.ps1

來源：`C:\Users\icemo\.mavis\agents\mavis\workspace\tools\tw-pipeline-gui\TwPipelineMonitor.ps1`

```powershell
#requires -Version 5.1
<#
.SYNOPSIS
  tw-invest-suite + AI-Telegram Pipeline Monitor (GUI)
  排程監控 + 整鏈/單階段手動觸發

.DESCRIPTION
  - 監控所有 Windows Task Scheduler 相關任務 (18 個)
  - 顯示整體 health (HEALTHY/DEGRADED/BLOCKED/FAILED) 從 audit latest.json
  - 手動觸發單一 stage（Start-ScheduledTask，包確認對話框）
  - 一鍵觸發 22:25 全鏈 nightly (tw-invest-suite-daily-report)
  - 唯讀審查 (audit --no-notify，不寫 DB、不發送 Telegram)
  - 安全：永遠不重啟 AI-Telegram Scheduled Pipeline (forever owner，5+ 天 Running)
  - Auto-refresh 預設 30 秒
  - Thread-safe：所有 UI 更新走 Invoke
#>

param(
    [switch]$SelfTest,
    [switch]$Snapshot,
    [string]$ExecutionSummary,
    [string]$PreviewTask
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ============== 設定 ==============
$AuditScript     = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\daily_chain_audit.py'
$AuditPython     = 'C:\Python314\python.exe'
$AuditLatest     = 'C:\Groove-Lab\automation\audit\latest.json'
$TwRuntime       = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
$AuditRunner     = Join-Path $PSScriptRoot 'audit_runner.ps1'
$NewsCachePath   = 'D:\CODEX\AI-Telegram\ui_control_panel\cache\news_refresh_latest.json'
$RefreshInterval = 30
$ForbiddenTask   = 'AI-Telegram Scheduled Pipeline'  # 永遠不重啟
$CrashLog        = Join-Path $env:LOCALAPPDATA 'Temp\tw-pipeline-gui-crash.log'
$AuditStdout     = Join-Path $env:LOCALAPPDATA 'Temp\tw-pipeline-gui-audit.out.log'
$AuditStderr     = Join-Path $env:LOCALAPPDATA 'Temp\tw-pipeline-gui-audit.err.log'
$AuditExitCode   = Join-Path $env:LOCALAPPDATA 'Temp\tw-pipeline-gui-audit.exit.txt'
$script:RefreshJob = $null
$script:RefreshStarted = $null
$script:AuditProcess = $null
$script:AuditStarted = $null

# CJK 友善字型（依序嘗試）
$UIFont  = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$MonoFont = New-Object System.Drawing.Font('Consolas', 9)

# 監控的排程清單
$WatchedTasks = @(
    'tw-invest-suite-market-screen',
    'AI-Telegram Enrichment Update 18-25',
    'AI-Telegram Pattern Scan 18-30',
    'tw-invest-suite-daily-report',
    'AI-Telegram Daily Report 22-47',
    'tw-invest-suite-marker-watchdog',
    'tw-invest-suite-postflight',
    'tw-invest-suite-publish',
    'tw-invest-suite-daily-chain-audit',
    'tw-invest-suite-certification-catchup',
    'tw-invest-suite-health-check',
    'tw-invest-suite-nightly-health',
    'tw-invest-suite-company-refresh',
    'tw-invest-suite-metadata-backfill',
    'tw-invest-suite-yfinance',
    'tw-invest-suite-finmind-download',
    'tw-invest-suite-news-refresh',
    'tw-invest-suite-sync-legacy',
    'AI-Telegram Scheduled Pipeline',
    'AI-Telegram Stock News Auto Refresh'
)

# 可觸發的 stage
$TriggableStages = @(
    [pscustomobject]@{ Name = 'tw-invest-suite-market-screen';       Time = '18:20'; Desc = '市場 24 檔 + features + ledger' }
    [pscustomobject]@{ Name = 'AI-Telegram Enrichment Update 18-25';  Time = '18:25'; Desc = 'US anchor + news 刷新' }
    [pscustomobject]@{ Name = 'AI-Telegram Pattern Scan 18-30';       Time = '18:30'; Desc = '型態掃描' }
    [pscustomobject]@{ Name = 'tw-invest-suite-daily-report';         Time = '21:30'; Desc = '【全鏈】nightly 完整跑一次' }
    [pscustomobject]@{ Name = 'AI-Telegram Daily Report 22-47';       Time = '22:47'; Desc = '4 份 daily report + Telegram' }
    [pscustomobject]@{ Name = 'tw-invest-suite-marker-watchdog';      Time = '23:55'; Desc = 'marker watchdog' }
    [pscustomobject]@{ Name = 'tw-invest-suite-postflight';           Time = '00:05'; Desc = 'postflight 驗收' }
    [pscustomobject]@{ Name = 'tw-invest-suite-publish';              Time = '00:30'; Desc = 'GitHub Pages + groovelab.dev 發布' }
    [pscustomobject]@{ Name = 'tw-invest-suite-daily-chain-audit';    Time = '06:30'; Desc = 'audit 驗收' }
    [pscustomobject]@{ Name = 'tw-invest-suite-certification-catchup'; Time = '每小時'; Desc = '認證 catch-up（idempotent）' }
    [pscustomobject]@{ Name = 'tw-invest-suite-health-check';         Time = '健康';  Desc = '健康檢查' }
    [pscustomobject]@{ Name = 'tw-invest-suite-nightly-health';       Time = '健康';  Desc = 'nightly 健康' }
    [pscustomobject]@{ Name = 'tw-invest-suite-company-refresh';      Time = '23:25'; Desc = '公司資料刷新' }
    [pscustomobject]@{ Name = 'tw-invest-suite-finmind-download';     Time = '19:00 / 23:00'; Desc = '【FinMind 主路徑】19:00 更新 OHLCV；23:00 更新完整 canonical（含融資融券）；日期依官方交易日曆' }
    [pscustomobject]@{ Name = 'tw-invest-suite-yfinance';             Time = '22:30'; Desc = '【Yahoo fallback】收盤報價；FinMind 主路徑失敗時用' }
    [pscustomobject]@{ Name = 'tw-invest-suite-news-refresh';         Time = '每 2 小時 08-22'; Desc = '【新聞專用】更新 groovelab 即時 watchlist；保留認證 artifacts，不推 GitHub Pages' }
)

$ExternalEffectTasks = @(
    'tw-invest-suite-daily-report',
    'AI-Telegram Daily Report 22-47',
    'tw-invest-suite-publish',
    'tw-invest-suite-certification-catchup',
    'tw-invest-suite-news-refresh'
)

# Runs both synchronously for -Snapshot/-SelfTest and inside Start-Job for the GUI.
$SnapshotScript = {
    param([string]$AuditPath, [string[]]$TaskNames, [string]$OwnerTask)

    $health = [pscustomobject]@{
        status = 'NO_AUDIT'; fingerprint = ''; checked_at = ''
        target_date = ''; current_session = ''; findings_count = 0
    }
    try {
        if (Test-Path -LiteralPath $AuditPath) {
            $j = Get-Content -LiteralPath $AuditPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $health = [pscustomobject]@{
                status = if ($j.status) { [string]$j.status } else { 'UNKNOWN' }
                fingerprint = if ($j.fingerprint) { [string]$j.fingerprint } else { '' }
                checked_at = if ($j.checked_at) { [string]$j.checked_at } else { '' }
                target_date = if ($j.target_date) { [string]$j.target_date } else { '' }
                current_session = if ($j.current_session) { [string]$j.current_session } else { '' }
                findings_count = @($j.findings).Count
            }
        }
    } catch {
        $health = [pscustomobject]@{
            status = 'AUDIT_READ_ERROR'; fingerprint = ''; checked_at = ''
            target_date = ''; current_session = ''; findings_count = 0
            error = $_.Exception.Message
        }
    }

    $ownerProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match '[\\/]run_pipeline_scheduled\.py(?:"|\s|$)' -and
            $_.CommandLine -notmatch '(?:^|\s)--once(?:\s|$)'
        } |
        Select-Object ProcessId, ParentProcessId, CreationDate, CommandLine)

    $tasks = foreach ($name in $TaskNames) {
        try {
            $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
            $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
            if ($null -eq $task) {
                [pscustomobject]@{
                    Name = $name; Found = $false; State = 'MISSING'; Logon = '?'
                    Wake = $false; StartWhenAvailable = $false
                    LastRun = '—'; LastResult = $null; LastResultStr = '—'; LastResultHex = '—'
                    NextRun = '—'; OwnerProcessAlive = $false; OwnerPids = @()
                }
                continue
            }
            $isOwner = $name -eq $OwnerTask
            $ownerAlive = $isOwner -and $ownerProcesses.Count -gt 0
            $code = if ($info) { [uint32]$info.LastTaskResult } else { [uint32]0 }
            [pscustomobject]@{
                Name = $name; Found = $true
                State = if ($ownerAlive) { 'Running (process)' } else { [string]$task.State }
                Logon = [string]$task.Principal.LogonType
                Wake = [bool]$task.Settings.WakeToRun
                StartWhenAvailable = [bool]$task.Settings.StartWhenAvailable
                LastRun = if ($info -and $info.LastRunTime) { $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') } else { '—' }
                LastResult = $code; LastResultStr = [string]$code
                LastResultHex = ('0x{0:X8}' -f $code)
                NextRun = if ($info -and $info.NextRunTime) { $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') } else { '—' }
                OwnerProcessAlive = $ownerAlive
                OwnerPids = if ($isOwner) { @($ownerProcesses.ProcessId) } else { @() }
            }
        } catch {
            [pscustomobject]@{
                Name = $name; Found = $false; State = 'ERROR'; Logon = '?'
                Wake = $false; StartWhenAvailable = $false
                LastRun = '—'; LastResult = $null; LastResultStr = '—'; LastResultHex = '—'
                NextRun = '—'; OwnerProcessAlive = $false; OwnerPids = @(); Error = $_.Exception.Message
            }
        }
    }

    [pscustomobject]@{
        ok = $true
        captured_at = (Get-Date).ToString('o')
        health = $health
        tasks = @($tasks)
        owner_processes = $ownerProcesses
    }
}

# ============== 工具函式 ==============
function Write-Log {
    param([string]$Msg, [System.Drawing.Color]$Color = [System.Drawing.Color]::LightGreen)
    if (-not $script:LogBox) { return }
    $ts = Get-Date -Format 'HH:mm:ss'
    $line = "[$ts] $Msg"
    if ($script:LogBox.InvokeRequired) {
        $script:LogBox.Invoke([Action]{ Write-LogInternal $line $Color })
    } else {
        Write-LogInternal $line $Color
    }
}

function Write-LogInternal {
    param([string]$Line, [System.Drawing.Color]$Color)
    $script:LogBox.SuspendLayout()
    $script:LogBox.SelectionStart = $script:LogBox.TextLength
    $script:LogBox.SelectionLength = 0
    $script:LogBox.SelectionColor = $Color
    $script:LogBox.AppendText($Line + [Environment]::NewLine)
    $script:LogBox.ScrollToCaret()
    $script:LogBox.ResumeLayout()
}

function Get-AuditHealth {
    try {
        if (-not (Test-Path $AuditLatest)) {
            return @{ status = 'NO_AUDIT'; fingerprint = ''; checked_at = ''; target_date = ''; current_session = '' }
        }
        $j = Get-Content $AuditLatest -Raw -Encoding UTF8 | ConvertFrom-Json
        return @{
            status = if ($j.status) { [string]$j.status } else { 'UNKNOWN' }
            fingerprint = if ($j.fingerprint) { [string]$j.fingerprint } else { '' }
            checked_at = if ($j.checked_at) { [string]$j.checked_at } else { '' }
            target_date = if ($j.target_date) { [string]$j.target_date } else { '' }
            current_session = if ($j.current_session) { [string]$j.current_session } else { '' }
        }
    } catch {
        return @{ status = 'ERROR'; fingerprint = ''; checked_at = ''; target_date = ''; current_session = ''; error = $_.Exception.Message }
    }
}

function Get-NewsSnapshot {
    try {
        if (-not (Test-Path $NewsCachePath)) {
            return @{
                light = 'red'; refreshed_at = ''; latest_date = $null; today = (Get-Date -Format 'yyyy-MM-dd')
                items = @(); top_headlines = @(); is_empty = $true
                note = 'cache missing - first refresh pending'
            }
        }
        $j = Get-Content $NewsCachePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $items = if ($j.items) { @($j.items) } else { @() }
        $top = $items | Select-Object -First 3 | ForEach-Object {
            [pscustomobject]@{
                title = [string]$_.title
                source = [string]$_.source
                published_at = [string]$_.published_at
                hotness = [double]$_.hotness
            }
        }
        return @{
            light = [string]$j.light
            refreshed_at = [string]$j.refreshed_at
            latest_date = $j.latest_date
            today = [string]$j.today
            items = $items
            top_headlines = @($top)
            is_empty = ($items.Count -eq 0)
            note = if ($items.Count -eq 0) { 'no news today (refreshed but Google News returned 0 items)' } else { "$($items.Count) headlines" }
        }
    } catch {
        return @{
            light = 'red'; refreshed_at = ''; latest_date = $null; today = (Get-Date -Format 'yyyy-MM-dd')
            items = @(); top_headlines = @(); is_empty = $true; note = "read failed: $($_.Exception.Message)"
        }
    }
}

function Get-SchedulerTaskRow {
    param([string]$Name)
    try {
        $t = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        if ($null -eq $t) { return $null }
        $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
        $logon = '?'
        try { $logon = $t.Principal.LogonType.ToString() } catch {}
        return [pscustomobject]@{
            Name = $Name
            State = $t.State.ToString()
            Logon = $logon
            Wake = $t.Settings.WakeToRun
            StartWhenAvailable = $t.Settings.StartWhenAvailable
            LastRun = if ($info -and $info.LastRunTime) { $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') } else { '—' }
            LastResult = if ($info) { $info.LastTaskResult } else { 0 }
            LastResultStr = if ($info) { ('{0}' -f $info.LastTaskResult) } else { '0' }
            LastResultHex = if ($info) { '0x{0:X}' -f $info.LastTaskResult } else { '0x0' }
            NextRun = if ($info -and $info.NextRunTime) { $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') } else { '—' }
        }
    } catch {
        return $null
    }
}

function Get-HumanTaskState {
    param([string]$State, [bool]$OwnerProcessAlive = $false)
    if ($OwnerProcessAlive -or $State -like 'Running*') { return '正在執行' }
    switch ($State) {
        'Ready'    { return '待命' }
        'Disabled' { return '已停用' }
        'Queued'   { return '等待執行' }
        'MISSING'  { return '找不到' }
        'ERROR'    { return '讀取失敗' }
        default    { return '狀態未知' }
    }
}

function Get-HumanLogon {
    param([string]$Logon)
    switch ($Logon) {
        'S4U'             { return '背景執行' }
        'ServiceAccount'  { return '系統服務' }
        'Interactive'     { return '登入使用者' }
        'InteractiveToken' { return '登入使用者' }
        'Password'        { return '帳戶密碼' }
        'Group'           { return '使用者群組' }
        '?'               { return '未知' }
        default           { return '其他方式' }
    }
}

function Get-HumanTaskResult {
    param($Code, [bool]$OwnerProcessAlive = $false)
    if ($OwnerProcessAlive) { return '服務正常運行' }
    if ($null -eq $Code) { return '尚無結果' }
    $value = [uint32]$Code
    switch ($value) {
        0          { return '成功' }
        1          { return '失敗' }
        10         { return '完成，但有提醒' }
        267009     { return '正在執行' }
        267010     { return '已停用' }
        267011     { return '尚未執行' }
        267014     { return '已中止' }
        4294967295 { return '尚無結果' }
        2147946720 { return '前次未正常結束' }
        default    { return '需要檢查' }
    }
}

function Get-TaskExecutionSummary {
    param([string]$TaskName)

    $launchers = New-Object System.Collections.Generic.List[string]
    $pythonFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $launcherFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $pendingFiles = New-Object 'System.Collections.Generic.Queue[string]'
    $addPythonFile = {
        param([string]$Candidate, [string]$BaseDir = '')
        $clean = $Candidate.Trim().Trim('"').Trim("'")
        if ($clean -match '(?i)python(?:[0-9.]*)?\.exe\s+(?<script>.+\.py)$') {
            $clean = $Matches['script'].Trim()
        }
        if ($clean -and -not [System.IO.Path]::IsPathRooted($clean) -and $BaseDir) {
            $searchRoots = @($BaseDir, (Split-Path -Parent $BaseDir))
            foreach ($searchRoot in $searchRoots) {
                if (-not $searchRoot) { continue }
                $resolved = [System.IO.Path]::GetFullPath((Join-Path $searchRoot $clean))
                if (Test-Path -LiteralPath $resolved) {
                    $clean = $resolved
                    break
                }
            }
        }
        if ($clean) { [void]$pythonFiles.Add($clean) }
    }
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        foreach ($action in @($task.Actions)) {
            $command = (([string]$action.Execute) + ' ' + ([string]$action.Arguments)).Trim()
            if ($command) { $launchers.Add($command) }
            foreach ($match in [regex]::Matches([string]$action.Arguments, '(?i)(?<path>[A-Z]:\\[^"''\r\n|;&]+?\.py|[A-Za-z0-9_.\\/-]+\.py)')) {
                & $addPythonFile $match.Groups['path'].Value
            }
            foreach ($match in [regex]::Matches([string]$action.Arguments, '(?i)(?<path>[A-Z]:\\[^"''\r\n]+?\.(?:ps1|cmd|bat))')) {
                $scriptPath = $match.Groups['path'].Value.Trim()
                if ($launcherFiles.Add($scriptPath)) { $pendingFiles.Enqueue($scriptPath) }
            }
        }

        $scanned = 0
        while ($pendingFiles.Count -gt 0 -and $scanned -lt 25) {
            $scriptPath = $pendingFiles.Dequeue()
            if (-not (Test-Path -LiteralPath $scriptPath)) { continue }
            $scanned++
            $source = Get-Content -LiteralPath $scriptPath -Raw -Encoding UTF8
            foreach ($match in [regex]::Matches($source, '(?i)(?<path>[A-Z]:\\[^"''\r\n|;&]+?\.py|[A-Za-z0-9_.\\/-]+\.py)')) {
                & $addPythonFile $match.Groups['path'].Value (Split-Path -Parent $scriptPath)
            }
            foreach ($match in [regex]::Matches($source, '(?i)(?<path>[A-Z]:\\[^"''\r\n]+?\.(?:ps1|cmd|bat))')) {
                $childPath = $match.Groups['path'].Value.Trim()
                if ($launcherFiles.Add($childPath)) { $pendingFiles.Enqueue($childPath) }
            }
        }

        $absoluteLeafNames = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
        foreach ($pythonFile in @($pythonFiles)) {
            if ([System.IO.Path]::IsPathRooted($pythonFile)) {
                [void]$absoluteLeafNames.Add([System.IO.Path]::GetFileName($pythonFile))
            }
        }
        foreach ($pythonFile in @($pythonFiles)) {
            if (-not [System.IO.Path]::IsPathRooted($pythonFile) -and $pythonFile -notmatch '[\\/]' -and $absoluteLeafNames.Contains($pythonFile)) {
                [void]$pythonFiles.Remove($pythonFile)
            }
        }
    } catch {
        return "執行檔案資訊讀取失敗：$($_.Exception.Message)"
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('排程入口：')
    if ($launchers.Count) {
        foreach ($launcher in $launchers) { $lines.Add("  $launcher") }
    } else {
        $lines.Add('  未提供')
    }
    $lines.Add('')
    $lines.Add('Python 檔案：')
    if ($pythonFiles.Count) {
        foreach ($pythonFile in @($pythonFiles | Sort-Object)) { $lines.Add("  $pythonFile") }
    } else {
        $lines.Add('  此排程沒有直接指定 Python 檔案')
    }
    return ($lines -join [Environment]::NewLine)
}

function Color-ForResult {
    param($Code, [bool]$OwnerProcessAlive = $false)
    if ($OwnerProcessAlive) { return [System.Drawing.Color]::SeaGreen }
    if ($null -eq $Code) { return [System.Drawing.Color]::DarkRed }
    $Code = [uint32]$Code
    if ($Code -eq 0) { return [System.Drawing.Color]::SeaGreen }
    if ($Code -eq 10) { return [System.Drawing.Color]::DarkOrange }
    if ($Code -eq 2147946720) { return [System.Drawing.Color]::DarkOrange }
    if ($Code -gt 1000) { return [System.Drawing.Color]::DarkRed }
    return [System.Drawing.Color]::DarkGoldenrod
}

function UI-SetText {
    param($Control, [string]$Text, [System.Drawing.Color]$Color)
    if ($null -eq $Control) { return }
    if ($Control.InvokeRequired) {
        $Control.Invoke([Action]{ $Control.Text = $Text; if ($Color) { $Control.ForeColor = $Color } })
    } else {
        $Control.Text = $Text
        if ($Color) { $Control.ForeColor = $Color }
    }
}

function Apply-RefreshResult {
    param($Result, [double]$ElapsedSeconds)
    if (-not $Result -or -not $Result.ok) {
        $message = if ($Result.error) { $Result.error } else { 'snapshot worker did not return data' }
        Write-Log ("Refresh 失敗 ({0:n1}s)：{1}" -f $ElapsedSeconds, $message) ([System.Drawing.Color]::DarkRed)
        return
    }

    # 更新 health
    $h = $Result.health
    $color = switch ($h.status) {
        'HEALTHY'   { [System.Drawing.Color]::SeaGreen }
        'DEGRADED'  { [System.Drawing.Color]::DarkOrange }
        'BLOCKED'   { [System.Drawing.Color]::Goldenrod }
        'FAILED'    { [System.Drawing.Color]::DarkRed }
        'AUDIT_READ_ERROR' { [System.Drawing.Color]::DarkRed }
        default     { [System.Drawing.Color]::Gray }
    }
    UI-SetText $script:HealthLabel $h.status $color
    $fingerprint = [string]$h.fingerprint
    $shortFingerprint = if ($fingerprint) { $fingerprint.Substring(0, [Math]::Min(12, $fingerprint.Length)) } else { '—' }
    UI-SetText $script:HealthDetail "target_date=$($h.target_date) | current_session=$($h.current_session) | checked_at=$($h.checked_at) | findings=$($h.findings_count) | fp=$shortFingerprint"

    # 更新 news panel (main thread 讀 cache 即可，輕量)
    $n = Get-NewsSnapshot
    $newsColor = switch ($n.light) {
        'green'  { [System.Drawing.Color]::SeaGreen }
        'yellow' { [System.Drawing.Color]::DarkOrange }
        'red'    { [System.Drawing.Color]::DarkRed }
        default  { [System.Drawing.Color]::Gray }
    }
    UI-SetText $script:NewsLight $n.light $newsColor
    UI-SetText $script:NewsDetail ("last_refresh={0} | latest={1} | today={2} | items={3} | {4}" -f `
        ($n.refreshed_at -replace 'T', ' ' -replace '\+.*$', ''), `
        ($n.latest_date -as [string] -replace '^$', '—'), `
        $n.today, `
        $n.items.Count, `
        $n.note)

    $script:NewsTopList.BeginUpdate()
    try {
        $script:NewsTopList.Items.Clear()
        if ($n.top_headlines.Count -gt 0) {
            foreach ($h in $n.top_headlines) {
                $item = New-Object System.Windows.Forms.ListViewItem(([string]$h.source))
                $item.SubItems.AddRange([string[]]@(
                    [string]$h.title,
                    ([string]$h.published_at -replace 'T', ' ' -replace '\+.*$', '' -replace '\.\d+Z?$', ''),
                    ('{0:n1}' -f [double]$h.hotness)
                ))
                $item.ForeColor = [System.Drawing.Color]::Black
                # store url in Tag for double-click handler
                $url = ($n.items | Where-Object { $_.title -eq $h.title } | Select-Object -First 1).url
                if ($url) { $item.Tag = [string]$url }
                $script:NewsTopList.Items.Add($item) | Out-Null
            }
        } else {
            # 沒 news 時也要讓 panel 顯示「no news」訊息
            $item = New-Object System.Windows.Forms.ListViewItem(('—'))
            $item.SubItems.AddRange([string[]]@(
                ('no news today  (last refresh: ' + ($n.refreshed_at -replace 'T', ' ' -replace '\+.*$', '') + ')'),
                $n.today, '0'
            ))
            $item.ForeColor = [System.Drawing.Color]::DarkOrange
            $item.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Italic)
            $script:NewsTopList.Items.Add($item) | Out-Null
        }
    } finally {
        $script:NewsTopList.EndUpdate()
    }

    # 更新 task list（用 BeginUpdate/EndUpdate 避免 flicker）
    $script:TaskList.BeginUpdate()
    try {
        $script:TaskList.Items.Clear()
        foreach ($row in $Result.tasks) {
            # PowerShell 5.1 overload 解析陷阱：不要傳 array 給 New-Object ListViewItem，
            # 會誤匹配 (string[], Color, Color, Font) 建構子把字串當 Color 轉。
            # 解法：用 Text-only 建構子 + SubItems.AddRange([string[]]@(...))
            $displayState = Get-HumanTaskState $row.State $row.OwnerProcessAlive
            $displayLogon = Get-HumanLogon $row.Logon
            $displayResult = Get-HumanTaskResult $row.LastResult $row.OwnerProcessAlive
            $item = New-Object System.Windows.Forms.ListViewItem($row.Name)
            $item.SubItems.AddRange([string[]]@($displayState, $displayLogon, $row.LastRun, $displayResult, $row.NextRun))
            $item.SubItems[1].ForeColor = if ($row.State -like 'Running*') { [System.Drawing.Color]::SeaGreen } elseif (-not $row.Found) { [System.Drawing.Color]::DarkRed } else { [System.Drawing.Color]::Black }
            $item.SubItems[2].ForeColor = if ($row.Logon -eq 'S4U' -or $row.Logon -eq 'ServiceAccount') { [System.Drawing.Color]::SeaGreen } elseif ($row.Logon -eq '?') { [System.Drawing.Color]::DarkRed } else { [System.Drawing.Color]::Black }
            $item.SubItems[4].ForeColor = Color-ForResult $row.LastResult $row.OwnerProcessAlive
            $item.Tag = $row
            $script:TaskList.Items.Add($item) | Out-Null
        }
    } finally {
        $script:TaskList.EndUpdate()
    }

    $script:LeftTitle.Text = "排程狀態 ($($Result.tasks.Count)/$($WatchedTasks.Count))"
    UI-SetText $script:RefreshedLabel "最後更新：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Log ("Refresh 完成：Health={0}，任務數={1}，耗時 {2:n1}s" -f $h.status, $Result.tasks.Count, $ElapsedSeconds) ([System.Drawing.Color]::LightGreen)
}

function Refresh-All {
    if ($script:RefreshJob -and $script:RefreshJob.State -in @('Running', 'NotStarted')) {
        return
    }
    if ($script:RefreshJob) {
        Remove-Job -Job $script:RefreshJob -Force -ErrorAction SilentlyContinue
        $script:RefreshJob = $null
    }
    $script:RefreshStarted = Get-Date
    UI-SetText $script:RefreshedLabel '更新中…'
    try {
        $script:RefreshJob = Start-Job -ScriptBlock $SnapshotScript -ArgumentList $AuditLatest, @($WatchedTasks), $ForbiddenTask
    } catch {
        Write-Log "無法啟動 refresh worker：$($_.Exception.Message)" ([System.Drawing.Color]::DarkRed)
    }
}

function Complete-RefreshIfReady {
    if (-not $script:RefreshJob -or $script:RefreshJob.State -in @('Running', 'NotStarted')) { return }
    $elapsed = if ($script:RefreshStarted) { ((Get-Date) - $script:RefreshStarted).TotalSeconds } else { 0 }
    try {
        if ($script:RefreshJob.State -eq 'Completed') {
            $items = @(Receive-Job -Job $script:RefreshJob -ErrorAction Stop)
            $result = if ($items.Count) { $items[-1] } else { $null }
            Apply-RefreshResult $result $elapsed
        } else {
            $reason = ($script:RefreshJob.ChildJobs[0].JobStateInfo.Reason | Out-String).Trim()
            Write-Log "Refresh worker $($script:RefreshJob.State)：$reason" ([System.Drawing.Color]::DarkRed)
        }
    } catch {
        Write-Log "Refresh worker 讀取失敗：$($_.Exception.Message)" ([System.Drawing.Color]::DarkRed)
    } finally {
        Remove-Job -Job $script:RefreshJob -Force -ErrorAction SilentlyContinue
        $script:RefreshJob = $null
        $script:RefreshStarted = $null
    }
}

function Run-AuditReadOnly {
    if ($script:AuditProcess -and -not $script:AuditProcess.HasExited) {
        Write-Log 'audit 已在執行，忽略重複請求' ([System.Drawing.Color]::DarkGoldenrod)
        return
    }
    foreach ($path in @($AuditStdout, $AuditStderr, $AuditExitCode)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    }
    Write-Log '啟動 audit (--no-notify, no Telegram)...' ([System.Drawing.Color]::Cyan)
    try {
        $script:AuditStarted = Get-Date
        $script:AuditProcess = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $AuditRunner), '-PythonPath', ('"{0}"' -f $AuditPython), '-AuditScript', ('"{0}"' -f $AuditScript), '-ExitCodePath', ('"{0}"' -f $AuditExitCode)) `
            -RedirectStandardOutput $AuditStdout -RedirectStandardError $AuditStderr `
            -WindowStyle Hidden -PassThru
        $script:BtnAudit.Enabled = $false
    } catch {
        $script:AuditProcess = $null
        Write-Log "audit 啟動失敗：$($_.Exception.Message)" ([System.Drawing.Color]::DarkRed)
    }
}

function Complete-AuditIfReady {
    if (-not $script:AuditProcess) { return }
    $process = $script:AuditProcess
    try {
        $process.Refresh()
        $hasExited = $process.HasExited
    } catch {
        Write-Log ("audit process 狀態讀取失敗：{0}" -f $_.Exception.Message) ([System.Drawing.Color]::DarkRed)
        $hasExited = $true
    }
    if (-not $hasExited) { return }
    try {
        # Wait until inherited stdout/stderr handles have flushed, then consume
        # the runner's explicit exit receipt. PowerShell 5.1 Process.ExitCode is
        # not reliable in this WinForms timer context.
        $process.WaitForExit()
        $elapsed = if ($script:AuditStarted) { ((Get-Date) - $script:AuditStarted).TotalSeconds } else { 0 }
        $exitCode = $null
        if (Test-Path -LiteralPath $AuditExitCode) {
            $rawExitCode = [string](Get-Content -LiteralPath $AuditExitCode -Raw -Encoding UTF8)
            $parsedExitCode = 0
            if ([int]::TryParse($rawExitCode.Trim(), [ref]$parsedExitCode)) { $exitCode = $parsedExitCode }
        }
        $health = Get-AuditHealth
        $stderr = ''
        if (Test-Path -LiteralPath $AuditStderr) {
            $rawStderr = Get-Content -LiteralPath $AuditStderr -Raw -Encoding UTF8
            if ($null -ne $rawStderr) { $stderr = [string]$rawStderr }
        }
        if ($null -eq $exitCode) {
            Write-Log ("audit exit receipt 遺失，耗時 {0:n1}s" -f $elapsed) ([System.Drawing.Color]::DarkRed)
        } elseif ($exitCode -eq 0) {
            Write-Log ("audit exit=0，status={0}，耗時 {1:n1}s" -f $health.status, $elapsed) ([System.Drawing.Color]::SeaGreen)
        } elseif ($exitCode -eq 10) {
            Write-Log ("audit exit=10，status={0}（有 findings，不是 crash），耗時 {1:n1}s" -f $health.status, $elapsed) ([System.Drawing.Color]::DarkOrange)
        } else {
            $detail = if (-not [string]::IsNullOrWhiteSpace($stderr)) { @($stderr -split '\r?\n')[-1] } else { 'no stderr' }
            Write-Log ("audit exit={0}，耗時 {1:n1}s：{2}" -f $exitCode, $elapsed, $detail) ([System.Drawing.Color]::DarkRed)
        }
    } catch {
        $failure = "audit completion 失敗：{0} @ {1}" -f $_.Exception.Message, $_.ScriptStackTrace
        Write-Log $failure ([System.Drawing.Color]::DarkRed)
        Add-Content -LiteralPath $CrashLog -Value ("[{0:o}] {1}" -f (Get-Date), $failure) -Encoding UTF8
    } finally {
        try { $process.Dispose() } catch {}
        $script:AuditProcess = $null
        $script:AuditStarted = $null
        $script:BtnAudit.Enabled = $true
        Refresh-All
    }
}

function Confirm-AutoTrigger {
    param(
        [string]$Title,
        [string]$Message,
        [int]$CountdownSeconds = 10
    )

    $dialog = New-Object System.Windows.Forms.Form
    $dialog.Text = $Title
    $dialog.Size = New-Object System.Drawing.Size(660, 330)
    $dialog.StartPosition = 'CenterParent'
    $dialog.FormBorderStyle = 'FixedDialog'
    $dialog.MaximizeBox = $false
    $dialog.MinimizeBox = $false
    $dialog.ControlBox = $false
    $dialog.Font = $UIFont
    $dialog.Tag = 'cancel'

    $body = New-Object System.Windows.Forms.TextBox
    $body.Location = New-Object System.Drawing.Point(20, 18)
    $body.Size = New-Object System.Drawing.Size(610, 180)
    $body.Text = $Message
    $body.Multiline = $true
    $body.ReadOnly = $true
    $body.ScrollBars = 'Vertical'
    $body.BackColor = [System.Drawing.Color]::White

    $countdown = New-Object System.Windows.Forms.Label
    $countdown.Location = New-Object System.Drawing.Point(20, 205)
    $countdown.Size = New-Object System.Drawing.Size(610, 28)
    $countdown.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 11, [System.Drawing.FontStyle]::Bold)
    $countdown.ForeColor = [System.Drawing.Color]::DarkOrange

    $runNow = New-Object System.Windows.Forms.Button
    $runNow.Text = '立即執行'
    $runNow.Location = New-Object System.Drawing.Point(365, 245)
    $runNow.Size = New-Object System.Drawing.Size(125, 34)
    $runNow.BackColor = [System.Drawing.Color]::LightSalmon

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = '取消'
    $cancel.Location = New-Object System.Drawing.Point(505, 245)
    $cancel.Size = New-Object System.Drawing.Size(125, 34)

    $countdownState = [pscustomobject]@{ Remaining = $CountdownSeconds }
    $countdown.Text = "$($countdownState.Remaining) 秒後自動執行；按取消可停止。"
    $dialog.Controls.AddRange(@($body, $countdown, $runNow, $cancel))

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 1000
    $timer.Add_Tick({
        $countdownState.Remaining--
        if ($countdownState.Remaining -le 0) {
            $timer.Stop()
            $dialog.Tag = 'run'
            $dialog.Close()
        } else {
            $countdown.Text = "$($countdownState.Remaining) 秒後自動執行；按取消可停止。"
        }
    })
    $runNow.Add_Click({ $timer.Stop(); $dialog.Tag = 'run'; $dialog.Close() })
    $cancel.Add_Click({ $timer.Stop(); $dialog.Tag = 'cancel'; $dialog.Close() })
    $dialog.Add_Shown({
        $body.SelectionStart = 0
        $body.SelectionLength = 0
        [void]$runNow.Focus()
        $timer.Start()
    })

    [void]$dialog.ShowDialog($form)
    $shouldRun = $dialog.Tag -eq 'run'
    $timer.Dispose()
    $dialog.Dispose()
    return $shouldRun
}

function Trigger-ScheduledTask {
    param([string]$TaskName, [switch]$SkipConfirmation)

    if ($TaskName -eq $ForbiddenTask) {
        Write-Log "拒絕觸發 $ForbiddenTask（forever owner，不得手動重啟）" ([System.Drawing.Color]::DarkRed)
        [System.Windows.Forms.MessageBox]::Show(
            "拒絕觸發 $ForbiddenTask`n`n這是 AI-Telegram 的 forever owner，已健康運行 5+ 天。`n規範：不要重啟 healthy owner。",
            '安全拒絕', 'OK', 'Warning') | Out-Null
        return
    }

    $allowed = @($TriggableStages | ForEach-Object { $_.Name })
    if ($TaskName -notin $allowed) {
        Write-Log "拒絕未知或未核准任務：$TaskName" ([System.Drawing.Color]::DarkRed)
        return
    }

    $row = Get-SchedulerTaskRow $TaskName
    if ($null -eq $row) {
        Write-Log "找不到任務：$TaskName" ([System.Drawing.Color]::DarkRed)
        return
    }

    if ($row.State -eq 'Running') {
        Write-Log "拒絕重複觸發：$TaskName 正在執行" ([System.Drawing.Color]::DarkOrange)
        [System.Windows.Forms.MessageBox]::Show("$TaskName 已在執行。`n請等待目前 run 完成。", '已在執行', 'OK', 'Warning') | Out-Null
        return
    }

    if (-not $SkipConfirmation) {
        $effect = if ($TaskName -in $ExternalEffectTasks) { "`n`n⚠ 此任務可能發布網站或傳送 Telegram。" } else { '' }
        $stateText = Get-HumanTaskState $row.State
        $resultText = Get-HumanTaskResult $row.LastResult
        $executionSummary = Get-TaskExecutionSummary $TaskName
        $msg = "即將執行：`r`n`r`n  $TaskName`r`n`r`n目前狀態：$stateText`r`n上次結果：$resultText$effect`r`n`r`n$executionSummary"
        if (-not (Confirm-AutoTrigger '排程即將自動執行' $msg)) {
            Write-Log "使用者取消觸發 $TaskName" ([System.Drawing.Color]::DarkGoldenrod)
            return
        }
    }

    Write-Log "Start-ScheduledTask $TaskName ..." ([System.Drawing.Color]::Cyan)
    try {
        Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
        Write-Log "觸發指令已送出；Started 不等於成功，請看 task state 與 receipt" ([System.Drawing.Color]::SeaGreen)
        Refresh-All
    } catch {
        Write-Log "觸發失敗：$($_.Exception.Message)" ([System.Drawing.Color]::DarkRed)
        [System.Windows.Forms.MessageBox]::Show("觸發失敗：`n$($_.Exception.Message)", '錯誤', 'OK', 'Error') | Out-Null
    }
}

function Trigger-CertCatchup {
    Trigger-ScheduledTask 'tw-invest-suite-certification-catchup'
}

function Trigger-NewsRefresh {
    <#
    Re-render C:\Groove-Lab\watchlist.html with the freshest available news.
    Prefers Start-ScheduledTask on `tw-invest-suite-news-refresh`; falls back
    to running the .py directly when the task is not registered (the user
    has not yet run the elevated installer). Does NOT push to groovelab.dev
    and does not modify certified public artifacts or push GitHub Pages.
    #>
    $taskName = 'tw-invest-suite-news-refresh'
    $scriptPath = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\news_refresh_watchlist.py'

    $row = Get-SchedulerTaskRow $taskName
    if ($row) {
        Trigger-ScheduledTask $taskName
        return
    }
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        Write-Log "找不到 news_refresh_watchlist.py：$scriptPath" ([System.Drawing.Color]::DarkRed)
        return
    }
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*news_refresh_watchlist.py*' })
    if ($existing) {
        Write-Log "新聞刷新已在執行，PID=$($existing[0].ProcessId)" ([System.Drawing.Color]::DarkGoldenrod)
        return
    }
    $msg = "找不到排程任務 $taskName，改用直接執行 news_refresh_watchlist.py。`n`n通常執行約 3-8 分鐘，會更新 groovelab 即時 watchlist，但保留認證 artifacts 且不推 GitHub Pages。`n`n提示：用桌面「註冊新聞刷新任務.lnk」安裝排程後可改用 Start-ScheduledTask 觸發。"
    if (-not (Confirm-AutoTrigger '新聞刷新即將執行' $msg)) {
        Write-Log '使用者取消新聞刷新' ([System.Drawing.Color]::DarkGoldenrod)
        return
    }
    Write-Log "Start-Process news_refresh_watchlist.py ..." ([System.Drawing.Color]::Cyan)
    $proc = Start-Process -FilePath 'C:\Python314\python.exe' -ArgumentList '-X','utf8',"`"$scriptPath`"" -WorkingDirectory (Split-Path -Parent $scriptPath) -WindowStyle Hidden -PassThru
    Write-Log "已啟動 PID=$($proc.Id)，完成時 log 寫到 reports\news_refresh_watchlist_*.log" ([System.Drawing.Color]::SeaGreen)
}

function Trigger-FullNightly {
    $executionSummary = Get-TaskExecutionSummary 'tw-invest-suite-daily-report'
    $msg = "將執行完整 nightly：資料更新、features、選股、模型、50+ 報告、網站發布、postflight 與 Telegram daily report。`r`n`r`n通常需要 10–30 分鐘，並會寫入資料庫及發布網站。`r`n`r`n$executionSummary"
    if (-not (Confirm-AutoTrigger '完整 nightly 即將自動執行' $msg)) {
        Write-Log '使用者取消整鏈 nightly' ([System.Drawing.Color]::DarkGoldenrod)
        return
    }
    Trigger-ScheduledTask 'tw-invest-suite-daily-report' -SkipConfirmation
}

function Open-AuditFile {
    if (Test-Path $AuditLatest) {
        Start-Process notepad.exe -ArgumentList $AuditLatest
        Write-Log "已開啟 $AuditLatest" ([System.Drawing.Color]::Cyan)
    } else {
        Write-Log "找不到 $AuditLatest" ([System.Drawing.Color]::DarkRed)
    }
}

function Open-TwRuntimeDir {
    Start-Process explorer.exe -ArgumentList $TwRuntime
}

function Invoke-SelfTest {
    $errors = New-Object System.Collections.Generic.List[string]
    $required = @($AuditScript, $AuditPython, $TwRuntime, $AuditRunner)
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path)) { $errors.Add("missing path: $path") }
    }
    if (@($WatchedTasks | Select-Object -Unique).Count -ne $WatchedTasks.Count) {
        $errors.Add('WatchedTasks contains duplicates')
    }
    $stageNames = @($TriggableStages | ForEach-Object { $_.Name })
    if (@($stageNames | Select-Object -Unique).Count -ne $stageNames.Count) {
        $errors.Add('TriggableStages contains duplicates')
    }
    if ($ForbiddenTask -in $stageNames) { $errors.Add('forever owner is triggable') }
    if ((Get-HumanTaskState 'Ready') -ne '待命') { $errors.Add('human state mapping failed') }
    if ((Get-HumanLogon 'S4U') -ne '背景執行') { $errors.Add('human logon mapping failed') }
    if ((Get-HumanTaskResult 0) -ne '成功' -or (Get-HumanTaskResult 4294967295) -ne '尚無結果') {
        $errors.Add('human result mapping failed')
    }
    $executionSummary = Get-TaskExecutionSummary 'tw-invest-suite-market-screen'
    if ($executionSummary -notmatch 'stock_features_daily\.py' -or $executionSummary -notmatch 'market_screen_runner\.py') {
        $errors.Add('python file discovery failed for market-screen')
    }
    $finmindSummary = Get-TaskExecutionSummary 'tw-invest-suite-finmind-download'
    if ($finmindSummary -notmatch [regex]::Escape('D:\CODEX\AI-Telegram\scripts\run_finmind_daily.py')) {
        $errors.Add('python file discovery failed for finmind-download')
    }
    foreach ($stage in $stageNames) {
        if ($stage -notin $WatchedTasks) { $errors.Add("triggable task is not watched: $stage") }
    }

    $snapshotResult = & $SnapshotScript $AuditLatest ([string[]]$WatchedTasks) $ForbiddenTask
    if (-not $snapshotResult.ok) { $errors.Add('snapshot failed') }
    $missing = @($snapshotResult.tasks | Where-Object { -not $_.Found })
    foreach ($row in $missing) { $errors.Add("scheduled task missing: $($row.Name)") }
    $owner = @($snapshotResult.tasks | Where-Object { $_.Name -eq $ForbiddenTask })
    if ($owner.Count -ne 1) { $errors.Add('owner row missing or duplicated') }
    elseif (-not $owner[0].OwnerProcessAlive) { $errors.Add('canonical owner process is not running') }
    if ($snapshotResult.health.status -in @('NO_AUDIT', 'AUDIT_READ_ERROR')) {
        $errors.Add("audit snapshot unavailable: $($snapshotResult.health.status)")
    }

    [pscustomobject]@{
        status = if ($errors.Count -eq 0) { 'ok' } else { 'failed' }
        checked_at = (Get-Date).ToString('o')
        watched_tasks = $WatchedTasks.Count
        triggable_tasks = $stageNames.Count
        audit_status = $snapshotResult.health.status
        owner_pids = @($snapshotResult.owner_processes.ProcessId)
        errors = @($errors.ToArray())
    }
}

if ($ExecutionSummary) {
    Get-TaskExecutionSummary $ExecutionSummary
    exit 0
}

if ($Snapshot) {
    & $SnapshotScript $AuditLatest ([string[]]$WatchedTasks) $ForbiddenTask | ConvertTo-Json -Depth 8
    exit 0
}

if ($SelfTest) {
    $testResult = Invoke-SelfTest
    $testResult | ConvertTo-Json -Depth 6
    if ($testResult.status -ne 'ok') { exit 1 }
    exit 0
}

# ============== GUI 建構 ==============
$form = New-Object System.Windows.Forms.Form
$form.Text = 'tw-invest-suite + AI-Telegram Pipeline Monitor'
$form.Size = New-Object System.Drawing.Size(1400, 880)
$form.StartPosition = 'CenterScreen'
$form.MinimumSize = New-Object System.Drawing.Size(1000, 640)
$form.Font = $UIFont
$form.BackColor = [System.Drawing.Color]::WhiteSmoke

# --- 上方狀態列 ---
$topPanel = New-Object System.Windows.Forms.Panel
$topPanel.Dock = 'Top'
$topPanel.Height = 100
$topPanel.BackColor = [System.Drawing.Color]::White

$healthTitle = New-Object System.Windows.Forms.Label
$healthTitle.Text = '整體 Health：'
$healthTitle.Location = New-Object System.Drawing.Point(20, 14)
$healthTitle.AutoSize = $true
$healthTitle.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10, [System.Drawing.FontStyle]::Bold)

$script:HealthLabel = New-Object System.Windows.Forms.Label
$script:HealthLabel.Text = '—'
$script:HealthLabel.Location = New-Object System.Drawing.Point(140, 10)
$script:HealthLabel.AutoSize = $true
$script:HealthLabel.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 14, [System.Drawing.FontStyle]::Bold)

$script:HealthDetail = New-Object System.Windows.Forms.Label
$script:HealthDetail.Text = '讀取中...'
$script:HealthDetail.Location = New-Object System.Drawing.Point(20, 50)
$script:HealthDetail.AutoSize = $true
$script:HealthDetail.Font = $MonoFont
$script:HealthDetail.ForeColor = [System.Drawing.Color]::DimGray

$btnRefresh = New-Object System.Windows.Forms.Button
$btnRefresh.Text = '🔄 立即 Refresh'
$btnRefresh.Location = New-Object System.Drawing.Point(1050, 14)
$btnRefresh.Size = New-Object System.Drawing.Size(140, 32)
$btnRefresh.Add_Click({ Refresh-All })

$script:BtnAudit = New-Object System.Windows.Forms.Button
$script:BtnAudit.Text = '🔍 跑 Audit (--no-notify)'
$script:BtnAudit.Location = New-Object System.Drawing.Point(1200, 14)
$script:BtnAudit.Size = New-Object System.Drawing.Size(180, 32)
$script:BtnAudit.Add_Click({ Run-AuditReadOnly })

$topPanel.Controls.AddRange(@($healthTitle, $script:HealthLabel, $script:HealthDetail, $btnRefresh, $script:BtnAudit))

# --- News panel (Google News RSS, 永遠 auto update by AI-Telegram Stock News Auto Refresh task) ---
$newsPanel = New-Object System.Windows.Forms.Panel
$newsPanel.Location = New-Object System.Drawing.Point(8, 108)
$newsPanel.Size = New-Object System.Drawing.Size(1376, 150)
$newsPanel.BorderStyle = 'FixedSingle'
$newsPanel.BackColor = [System.Drawing.Color]::White

$newsTitle = New-Object System.Windows.Forms.Label
$newsTitle.Text = '新聞狀態 (Google News RSS, auto every 2h):'
$newsTitle.Location = New-Object System.Drawing.Point(8, 6)
$newsTitle.AutoSize = $true
$newsTitle.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10, [System.Drawing.FontStyle]::Bold)

$script:NewsLight = New-Object System.Windows.Forms.Label
$script:NewsLight.Text = '—'
$script:NewsLight.Location = New-Object System.Drawing.Point(330, 4)
$script:NewsLight.AutoSize = $true
$script:NewsLight.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 12, [System.Drawing.FontStyle]::Bold)

$script:NewsDetail = New-Object System.Windows.Forms.Label
$script:NewsDetail.Text = '讀取中...'
$script:NewsDetail.Location = New-Object System.Drawing.Point(8, 30)
$script:NewsDetail.AutoSize = $true
$script:NewsDetail.Font = $MonoFont
$script:NewsDetail.ForeColor = [System.Drawing.Color]::DimGray

$script:NewsTopList = New-Object System.Windows.Forms.ListView
$script:NewsTopList.Location = New-Object System.Drawing.Point(8, 52)
$script:NewsTopList.Size = New-Object System.Drawing.Size(1360, 90)
$script:NewsTopList.View = 'Details'
$script:NewsTopList.FullRowSelect = $true
$script:NewsTopList.GridLines = $false
$script:NewsTopList.Font = $MonoFont
$script:NewsTopList.BackColor = [System.Drawing.Color]::WhiteSmoke
[void]$script:NewsTopList.Columns.Add('Source', 100)
[void]$script:NewsTopList.Columns.Add('Title', 900)
[void]$script:NewsTopList.Columns.Add('Published', 200)
[void]$script:NewsTopList.Columns.Add('Hotness', 70)

$script:NewsTopList.Add_DoubleClick({
    if ($script:NewsTopList.SelectedItems.Count -gt 0) {
        $sel = $script:NewsTopList.SelectedItems[0]
        $url = $sel.Tag
        if ($url) { Start-Process $url | Out-Null }
    }
})

$newsPanel.Controls.AddRange(@($newsTitle, $script:NewsLight, $script:NewsDetail, $script:NewsTopList))

# --- 左半：Scheduler List ---
$leftPanel = New-Object System.Windows.Forms.Panel
$leftPanel.Location = New-Object System.Drawing.Point(8, 266)
$leftPanel.Size = New-Object System.Drawing.Size(820, 322)
$leftPanel.BorderStyle = 'FixedSingle'
$leftPanel.BackColor = [System.Drawing.Color]::White

$script:LeftTitle = New-Object System.Windows.Forms.Label
$script:LeftTitle.Text = '排程狀態 (讀取中)'
$script:LeftTitle.Location = New-Object System.Drawing.Point(8, 6)
$script:LeftTitle.AutoSize = $true
$script:LeftTitle.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10, [System.Drawing.FontStyle]::Bold)

$script:TaskList = New-Object System.Windows.Forms.ListView
$script:TaskList.Location = New-Object System.Drawing.Point(8, 30)
$script:TaskList.Size = New-Object System.Drawing.Size(804, 245)
$script:TaskList.View = 'Details'
$script:TaskList.FullRowSelect = $true
$script:TaskList.GridLines = $true
$script:TaskList.MultiSelect = $false
$script:TaskList.Font = $MonoFont

[void]$script:TaskList.Columns.Add('排程名稱', 290)
[void]$script:TaskList.Columns.Add('狀態', 80)
[void]$script:TaskList.Columns.Add('執行方式', 90)
[void]$script:TaskList.Columns.Add('上次執行', 105)
[void]$script:TaskList.Columns.Add('上次結果', 105)
[void]$script:TaskList.Columns.Add('下次執行', 105)

$script:TaskList.Add_DoubleClick({
    if ($script:TaskList.SelectedItems.Count -gt 0) {
        $row = $script:TaskList.SelectedItems[0].Tag
        $stateText = Get-HumanTaskState $row.State $row.OwnerProcessAlive
        $logonText = Get-HumanLogon $row.Logon
        $resultText = Get-HumanTaskResult $row.LastResult $row.OwnerProcessAlive
        $wakeText = if ($row.Wake) { '會喚醒電腦' } else { '不會喚醒電腦' }
        $catchupText = if ($row.StartWhenAvailable) { '錯過後會補跑' } else { '錯過後不補跑' }
        $ownerDetail = if ($row.OwnerProcessAlive) { "`n背景服務：正常運行" } else { '' }
        $errorDetail = if ($row.Error) { "`nError: $($row.Error)" } else { '' }
        [System.Windows.Forms.MessageBox]::Show(
            "排程：$($row.Name)`n狀態：$stateText`n執行方式：$logonText`n電源：$wakeText`n補跑：$catchupText`n上次執行：$($row.LastRun)`n上次結果：$resultText`n下次執行：$($row.NextRun)$ownerDetail$errorDetail",
            '排程詳細資料', 'OK', 'Information') | Out-Null
    }
})

$leftHelp = New-Object System.Windows.Forms.Label
$leftHelp.Text = '雙擊任務可查看詳細資料；狀態與結果均使用一般文字顯示'
$leftHelp.Location = New-Object System.Drawing.Point(8, 280)
$leftHelp.AutoSize = $true
$leftHelp.ForeColor = [System.Drawing.Color]::DimGray
$leftHelp.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 8)

$leftPanel.Controls.AddRange(@($script:LeftTitle, $script:TaskList, $leftHelp))

# --- 右半：手動觸發 ---
$rightPanel = New-Object System.Windows.Forms.Panel
$rightPanel.Location = New-Object System.Drawing.Point(836, 266)
$rightPanel.Size = New-Object System.Drawing.Size(548, 322)
$rightPanel.BorderStyle = 'FixedSingle'
$rightPanel.BackColor = [System.Drawing.Color]::White

$rightTitle = New-Object System.Windows.Forms.Label
$rightTitle.Text = '手動觸發'
$rightTitle.Location = New-Object System.Drawing.Point(8, 6)
$rightTitle.AutoSize = $true
$rightTitle.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10, [System.Drawing.FontStyle]::Bold)

$stageLabel = New-Object System.Windows.Forms.Label
$stageLabel.Text = '單一 Stage：'
$stageLabel.Location = New-Object System.Drawing.Point(12, 38)
$stageLabel.AutoSize = $true

$script:StageCombo = New-Object System.Windows.Forms.ComboBox
$script:StageCombo.Location = New-Object System.Drawing.Point(12, 58)
$script:StageCombo.Size = New-Object System.Drawing.Size(520, 28)
$script:StageCombo.DropDownStyle = 'DropDownList'
foreach ($s in $TriggableStages) {
    $display = "[$($s.Time)] $($s.Name) — $($s.Desc)"
    $script:StageCombo.Items.Add([pscustomobject]@{ Name = $s.Name; Display = $display }) | Out-Null
}
$script:StageCombo.DisplayMember = 'Display'
$script:StageCombo.SelectedIndex = 0

$btnTrigger = New-Object System.Windows.Forms.Button
$btnTrigger.Text = '▶ 觸發選定 Stage'
$btnTrigger.Location = New-Object System.Drawing.Point(12, 96)
$btnTrigger.Size = New-Object System.Drawing.Size(160, 36)
$btnTrigger.BackColor = [System.Drawing.Color]::LightSkyBlue
$btnTrigger.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)
$btnTrigger.Add_Click({
    $sel = $script:StageCombo.SelectedItem
    if ($sel) { Trigger-ScheduledTask $sel.Name }
})

$btnFullNightly = New-Object System.Windows.Forms.Button
$btnFullNightly.Text = '▶▶ 觸發 21:30 整鏈 nightly'
$btnFullNightly.Location = New-Object System.Drawing.Point(180, 96)
$btnFullNightly.Size = New-Object System.Drawing.Size(220, 36)
$btnFullNightly.BackColor = [System.Drawing.Color]::LightSalmon
$btnFullNightly.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)
$btnFullNightly.Add_Click({ Trigger-FullNightly })

$btnCertCatchup = New-Object System.Windows.Forms.Button
$btnCertCatchup.Text = '🔁 Cert Catch-up'
$btnCertCatchup.Location = New-Object System.Drawing.Point(12, 138)
$btnCertCatchup.Size = New-Object System.Drawing.Size(160, 32)
$btnCertCatchup.Add_Click({ Trigger-CertCatchup })

$btnNewsRefresh = New-Object System.Windows.Forms.Button
$btnNewsRefresh.Text = '🗞 新聞刷新（groovelab 即時頁）'
$btnNewsRefresh.Location = New-Object System.Drawing.Point(180, 138)
$btnNewsRefresh.Size = New-Object System.Drawing.Size(220, 32)
$btnNewsRefresh.BackColor = [System.Drawing.Color]::LightGreen
$btnNewsRefresh.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)
$btnNewsRefresh.Add_Click({ Trigger-NewsRefresh })

$sep1 = New-Object System.Windows.Forms.Label
$sep1.Text = '--- 其他工具 ---'
$sep1.Location = New-Object System.Drawing.Point(12, 178)
$sep1.AutoSize = $true
$sep1.ForeColor = [System.Drawing.Color]::DimGray

$btnOpenAudit = New-Object System.Windows.Forms.Button
$btnOpenAudit.Text = '📄 開 audit/latest.json'
$btnOpenAudit.Location = New-Object System.Drawing.Point(12, 202)
$btnOpenAudit.Size = New-Object System.Drawing.Size(180, 30)
$btnOpenAudit.Add_Click({ Open-AuditFile })

$btnOpenRuntime = New-Object System.Windows.Forms.Button
$btnOpenRuntime.Text = '📁 開 runtime 目錄'
$btnOpenRuntime.Location = New-Object System.Drawing.Point(200, 202)
$btnOpenRuntime.Size = New-Object System.Drawing.Size(160, 30)
$btnOpenRuntime.Add_Click({ Open-TwRuntimeDir })

$warningLabel = New-Object System.Windows.Forms.Label
$warningLabel.Text = "⚠ 永遠不會觸發 AI-Telegram Scheduled Pipeline (forever owner)`n  規範：不要重啟 healthy owner。"
$warningLabel.Location = New-Object System.Drawing.Point(12, 244)
$warningLabel.Size = New-Object System.Drawing.Size(520, 50)
$warningLabel.ForeColor = [System.Drawing.Color]::DarkRed
$warningLabel.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 8, [System.Drawing.FontStyle]::Bold)

$rightPanel.Controls.AddRange(@($rightTitle, $stageLabel, $script:StageCombo, $btnTrigger, $btnFullNightly, $btnCertCatchup, $btnNewsRefresh, $sep1, $btnOpenAudit, $btnOpenRuntime, $warningLabel))

# --- 下方 Log 框 ---
$logPanel = New-Object System.Windows.Forms.Panel
$logPanel.Dock = 'Bottom'
$logPanel.Height = 250
$logPanel.BorderStyle = 'FixedSingle'
$logPanel.BackColor = [System.Drawing.Color]::White

$logTitle = New-Object System.Windows.Forms.Label
$logTitle.Text = '執行記錄 (Log)'
$logTitle.Location = New-Object System.Drawing.Point(8, 6)
$logTitle.AutoSize = $true
$logTitle.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10, [System.Drawing.FontStyle]::Bold)

$btnClearLog = New-Object System.Windows.Forms.Button
$btnClearLog.Text = '清除'
$btnClearLog.Location = New-Object System.Drawing.Point(1320, 4)
$btnClearLog.Size = New-Object System.Drawing.Size(60, 24)
$btnClearLog.Add_Click({ $script:LogBox.Clear() })

$script:LogBox = New-Object System.Windows.Forms.RichTextBox
$script:LogBox.Location = New-Object System.Drawing.Point(8, 30)
$script:LogBox.Size = New-Object System.Drawing.Size(1376, 200)
$script:LogBox.ReadOnly = $true
$script:LogBox.Font = $MonoFont
$script:LogBox.BackColor = [System.Drawing.Color]::Black
$script:LogBox.ForeColor = [System.Drawing.Color]::LightGreen
$script:LogBox.WordWrap = $false

$logPanel.Controls.AddRange(@($logTitle, $btnClearLog, $script:LogBox))

# --- 最底 status bar ---
$script:RefreshedLabel = New-Object System.Windows.Forms.Label
$script:RefreshedLabel.Text = '最後更新：—'
$script:RefreshedLabel.Dock = 'Bottom'
$script:RefreshedLabel.Height = 22
$script:RefreshedLabel.TextAlign = 'MiddleLeft'
$script:RefreshedLabel.BackColor = [System.Drawing.Color]::LightGray
$script:RefreshedLabel.Padding = New-Object System.Windows.Forms.Padding(8, 0, 0, 0)

# --- Auto-refresh timer ---
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = $RefreshInterval * 1000
$timer.Add_Tick({
    try {
        Refresh-All
    } catch {
        $__msg = "[$([DateTime]::Now.ToString('HH:mm:ss.fff'))] [Timer] " + $_.Exception.GetType().FullName + ': ' + $_.Exception.Message + "`n" + $_.ScriptStackTrace
        try { [System.IO.File]::AppendAllText($__crashLog, "`n" + $__msg) } catch {}
        try { Write-Log ("Auto-refresh 失敗：{0}" -f $_.Exception.Message) ([System.Drawing.Color]::DarkRed) } catch {}
    }
})

# Poll background refresh and audit processes without blocking the WinForms UI.
$workerTimer = New-Object System.Windows.Forms.Timer
$workerTimer.Interval = 500
$workerTimer.Add_Tick({
    try {
        Complete-RefreshIfReady
        Complete-AuditIfReady
    } catch {
        $__workerError = "背景 worker 檢查失敗：$($_.Exception.Message) @ $($_.ScriptStackTrace)"
        try { Write-Log $__workerError ([System.Drawing.Color]::DarkRed) } catch {}
        try { [System.IO.File]::AppendAllText($CrashLog, "`n$__workerError") } catch {}
    }
})

# --- 組裝 + 啟動 ---
$form.Controls.AddRange(@($topPanel, $newsPanel, $leftPanel, $rightPanel, $logPanel, $script:RefreshedLabel))

$__crashLog = $CrashLog
if (Test-Path $__crashLog) { Remove-Item $__crashLog -Force }

$form.Add_Shown({
    try {
        Write-Log 'tw-pipeline-gui 啟動' ([System.Drawing.Color]::SeaGreen)
        Write-Log ("Auto-refresh 每 {0}s；永遠不觸發 {1}" -f $RefreshInterval, $ForbiddenTask) ([System.Drawing.Color]::Cyan)
        Refresh-All
        $timer.Start()
        $workerTimer.Start()
    } catch {
        $__msg = "[$([DateTime]::Now.ToString('HH:mm:ss.fff'))] " + $_.Exception.GetType().FullName + ': ' + $_.Exception.Message + "`n" + $_.ScriptStackTrace
        [System.IO.File]::WriteAllText($__crashLog, $__msg)
        try {
            [System.Windows.Forms.MessageBox]::Show("Refresh-All crashed:`n`n$($_.Exception.Message)`n`nStack trace written to:`n$__crashLog", 'TW Pipeline GUI Crash', 'OK', 'Error') | Out-Null
        } catch {}
    }
})

$form.Add_FormClosing({
    $timer.Stop()
    $workerTimer.Stop()
    if ($script:RefreshJob) {
        Stop-Job -Job $script:RefreshJob -ErrorAction SilentlyContinue
        Remove-Job -Job $script:RefreshJob -Force -ErrorAction SilentlyContinue
        $script:RefreshJob = $null
    }
})

if ($PreviewTask) {
    $previewSummary = Get-TaskExecutionSummary $PreviewTask
    $previewResult = Confirm-AutoTrigger '倒數視窗預覽（不會觸發排程）' "預覽任務：$PreviewTask`r`n`r`n$previewSummary"
    [pscustomobject]@{ PreviewTask = $PreviewTask; CountdownCompleted = $previewResult; ScheduledTaskTriggered = $false } | ConvertTo-Json
    exit 0
}

[void]$form.ShowDialog()
```

### trigger-2130-elevated.ps1

來源：`C:\Users\icemo\.mavis\agents\mavis\workspace\tools\tw-pipeline-gui\trigger-2130-elevated.ps1`

```powershell
#requires -Version 5.1
# Preserve the registered S4U task byte-for-byte at the XML field level and
# change only the daily CalendarTrigger StartBoundary.
[CmdletBinding()]
param([switch]$SelfCheck)
$ErrorActionPreference = 'Stop'

$taskName = 'tw-invest-suite-daily-report'
$beforeTask = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
$beforeXmlText = Export-ScheduledTask -TaskName $taskName -ErrorAction Stop
[xml]$taskXml = $beforeXmlText

$calendarTriggers = @($taskXml.SelectNodes("//*[local-name()='CalendarTrigger']"))
if ($calendarTriggers.Count -ne 1) {
    throw "Expected exactly one CalendarTrigger; found $($calendarTriggers.Count)"
}
$startNode = $calendarTriggers[0].SelectSingleNode("./*[local-name()='StartBoundary']")
if ($null -eq $startNode) { throw 'CalendarTrigger has no StartBoundary' }

$next = Get-Date -Hour 21 -Minute 30 -Second 0 -Millisecond 0
if ($next -le (Get-Date)) { $next = $next.AddDays(1) }
$startNode.InnerText = $next.ToString('yyyy-MM-ddTHH:mm:ss')

if ($SelfCheck) {
    [pscustomobject]@{
        TaskName = $taskName
        CurrentStartBoundary = $beforeTask.Triggers[0].StartBoundary
        ProposedStartBoundary = $startNode.InnerText
        LogonType = $beforeTask.Principal.LogonType.ToString()
        RunLevel = $beforeTask.Principal.RunLevel.ToString()
        Action = $beforeTask.Actions[0].Execute
    } | ConvertTo-Json
    exit 0
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Administrator elevation is required to re-register this S4U task.' }

# COM constants: TASK_CREATE_OR_UPDATE=6, TASK_LOGON_S4U=2.
# Supplying the existing principal is required; using logon type 3 would
# silently change this into an interactive-token task.
$service = New-Object -ComObject Schedule.Service
$service.Connect()
$folder = $service.GetFolder('\')
$registered = $folder.RegisterTask(
    $taskName,
    $taskXml.OuterXml,
    6,
    $beforeTask.Principal.UserId,
    $null,
    2,
    $null
)

$afterTask = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
$afterXmlText = Export-ScheduledTask -TaskName $taskName -ErrorAction Stop
[xml]$afterXml = $afterXmlText
$afterStart = $afterXml.SelectSingleNode("//*[local-name()='CalendarTrigger']/*[local-name()='StartBoundary']").InnerText

if (-not $afterStart.EndsWith('T21:30:00')) { throw "Unexpected StartBoundary: $afterStart" }
if ($afterTask.Principal.LogonType.ToString() -ne 'S4U') { throw 'LogonType changed; expected S4U' }
if ($afterTask.Principal.RunLevel.ToString() -ne $beforeTask.Principal.RunLevel.ToString()) { throw 'RunLevel changed' }
if ($afterTask.Actions[0].Execute -ne $beforeTask.Actions[0].Execute -or
    $afterTask.Actions[0].Arguments -ne $beforeTask.Actions[0].Arguments -or
    $afterTask.Actions[0].WorkingDirectory -ne $beforeTask.Actions[0].WorkingDirectory) {
    throw 'Task action changed unexpectedly'
}

[pscustomobject]@{
    TaskName = $taskName
    StartBoundary = $afterStart
    NextRunTime = (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime
    State = $afterTask.State.ToString()
    LogonType = $afterTask.Principal.LogonType.ToString()
    RunLevel = $afterTask.Principal.RunLevel.ToString()
    WakeToRun = $afterTask.Settings.WakeToRun
    StartWhenAvailable = $afterTask.Settings.StartWhenAvailable
    Action = $afterTask.Actions[0].Execute
} | ConvertTo-Json
```

### tw-pipeline-trigger-2130.bat

來源：`C:\TankAkali\tw-pipeline-trigger-2130.bat`

```bat
@echo off
REM Change tw-invest-suite-daily-report trigger from 22:25 to 21:30.
REM ASCII-only launcher. The child PowerShell process requests elevation.
setlocal
set "UPDATE_PS=C:\Users\icemo\.mavis\agents\mavis\workspace\tools\tw-pipeline-gui\trigger-2130-elevated.ps1"

if not exist "%UPDATE_PS%" (
  echo [ERROR] Missing updater: %UPDATE_PS%
  pause
  exit /b 1
)

echo ============================================
echo  Change tw-invest-suite daily trigger to 21:30
echo ============================================
echo UAC will ask for permission. Click YES.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$script='%UPDATE_PS%'; try { $p=Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File ' + $script) -Wait -PassThru; exit $p.ExitCode } catch { Write-Error $_.Exception.Message; exit 1 }"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo [ERROR] Trigger update failed or UAC was cancelled. Exit=%RC%
  pause
  exit /b %RC%
)

echo.
echo [OK] Trigger update completed and was verified.
pause
endlocal & exit /b 0
```

### register_news_refresh.bat

來源：`C:\TankAkali\register_news_refresh.bat`

```bat
@echo off
REM Register tw-invest-suite-news-refresh. ASCII-only UAC launcher.
setlocal
set "REGISTER_PS=C:\Users\icemo\Projects\tw-invest-suite\scripts\register_news_refresh.ps1"

if not exist "%REGISTER_PS%" (
  echo [ERROR] Missing installer: %REGISTER_PS%
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$script='%REGISTER_PS%'; try { $p=Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File ' + $script) -Wait -PassThru; exit $p.ExitCode } catch { Write-Error $_.Exception.Message; exit 1 }"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [ERROR] Registration failed or UAC was cancelled. Exit=%RC%
if "%RC%"=="0" echo [OK] News refresh task registered and verified.
pause
endlocal & exit /b %RC%
```
