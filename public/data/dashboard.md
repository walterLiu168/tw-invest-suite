# tw-invest-suite Daily Dashboard
**Generated**: 2026-09-15T12:00:58
**Today**: 2026-09-15 (Tuesday)

**DB picks**: picks=24 (active=24)
**Marker**: data_date=2026-09-14 run_id=15 status=ok
**OHLCV latest**: 2026-09-14 (1d ago)

## GitHub Pages status
- ✓ `watchlist.html` — Last-Modified: Tue, 15 Sep 2026 02:12:16 GMT
- ✓ `patterns.html` — Last-Modified: Tue, 15 Sep 2026 02:12:16 GMT
- ✓ `chips.html` — Last-Modified: Tue, 15 Sep 2026 02:12:16 GMT
- ✓ `chips-advanced.html` — Last-Modified: Tue, 15 Sep 2026 02:12:16 GMT
- ✓ `sectors.html` — Last-Modified: Tue, 15 Sep 2026 02:12:16 GMT
- ✓ `concepts.html` — Last-Modified: Tue, 15 Sep 2026 02:12:16 GMT

## Cron results (last run)
| Cron | LastRun | RC | Status |
|---|---|---|---|
| `tw-invest-suite-daily-report` | 09/14/2026 22:25:25 | `0` | ✓ |
| `tw-invest-suite-marker-watchdog` | 11/30/1999 00:00:00 | `267011` | ✗ |
| `tw-invest-suite-health-check` | 09/14/2026 23:00:00 | `1` | ✗ |
| `tw-invest-suite-publish` | 09/15/2026 00:30:30 | `0` | ✓ |
| `tw-invest-suite-postflight` | 09/15/2026 00:05:05 | `1` | ✗ |

## DB integrity
- Quarantine open: **11** (1 distinct ticker)

## Known PENDING (out of scope for daily pipeline)
- 7768 quarantine (PENDING J) — accumulating daily
- Weekly Shareholding 1330 (D052h-era exit code 2)
- FinMind `finmind_taiwan_total_margin_daily` (structural weekly cadence)
- cloudflared 1033 (groovelab.dev)

## Quick fix (if needed)
```ps1
# Regenerate marker from DB picks
python _debug\marker_watchdog.py

# Manual push (if 00:30 publish missed)
python scripts\publish_manifest.py --date <YYYY-MM-DD> --write-to public\data\publish_manifest_<YYYY-MM-DD>.json
powershell scripts\publish_ghpages_daily.ps1

# Re-run advanced stages manually (sectors/chips/concepts)
powershell scripts\run_daily.ps1 -Mode render -IncludeAdvancedStages
```

**OVERALL**: 🟢 OK — all green
