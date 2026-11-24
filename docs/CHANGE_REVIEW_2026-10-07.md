# tw-pipeline-gui + tw-invest-suite change review (2026-10-07)

## Outcome

Code review and local implementation are complete. The live news refresh passed an end-to-end smoke test without changing the two certified public artifacts. Two Windows Scheduler changes still require an administrator UAC approval on the desktop.

## Findings and fixes

### CRITICAL

1. `news_refresh_watchlist.py` called the full renderer, which rewrote `public/watchlist.html` and `public/data/watchlist-full.json` after certification. That invalidated the D056-3 artifact hashes. Fixed with an explicit `render_full_watchlist.py --groove-only` mode. The refresh now changes only `C:\Groove-Lab\watchlist.html`.
2. `tw-pipeline-trigger-2130.bat` passed `-Verb RunAs` directly to `powershell.exe`; that parameter belongs to `Start-Process`, so elevation did not work. Fixed with a child `Start-Process -Verb RunAs -Wait -PassThru` call and exit-code propagation.
3. `trigger-2130-elevated.ps1` rebuilt the task XML by hand and used COM logon type `3` (interactive token), which could drop restart, idle and scheduling settings and change the S4U principal. Fixed by exporting the existing XML, changing only `CalendarTrigger/StartBoundary`, and re-registering with `TASK_LOGON_S4U=2`.

### MAJOR

1. `db_client.news_for_tickers()` did not select the `stock_news.url` column, so rendered canonical headlines had no links. Fixed with `url AS link`.
2. The fallback silently displayed the known stale 30-day FinMind feed. Fixed: only FinMind rows inside the same five-day date contract are allowed, and they are visibly labelled as fallback. Missing or unavailable canonical news is shown as a note.
3. The renderer queried the same bounded news set once per card. Fixed with one batch query for all 24 picks.
4. The refresh wrapper had no internal timeout and could leave an orphan renderer when Task Scheduler terminated it. Fixed with a 12-minute internal timeout and `taskkill /T /F`; the scheduled 15-minute limit remains the outer guard.
5. `register_news_refresh.ps1 -SelfCheck` required administrator rights before running its read-only check. Fixed by moving SelfCheck before the elevation gate.
6. The publish timing comment was wrong: a publisher starting at 22:50 with `WaitMinutes=130` has a 01:00 deadline, not 00:00. The implementation remains 130 minutes and the documentation now states the correct math.

### MINOR

1. News refresh status writes were non-atomic. Fixed with a temporary file and `os.replace`.
2. `$env:USERNAME` was ambiguous for an elevated S4U registration. The installer now uses `WindowsIdentity.Name`.
3. The GUI still displayed 22:25 and described the live Groovelab file as local-only. Labels, confirmation text, external-effect warning and direct-run duplicate guard were corrected.
4. The original 2.5-3 minute estimate was optimistic. The measured run took 6 minutes 17 seconds, so the GUI now says 3-8 minutes.

## Validation evidence

- Python compile: passed for `db_client.py`, `render_full_watchlist.py`, `news_refresh_watchlist.py`, and `pipeline_state.py` in source and runtime.
- PowerShell parser: zero errors for publisher, news registration, GUI, and 21:30 updater.
- Encoding: edited `.ps1` files are UTF-8 BOM; both launcher `.bat` files are ASCII without BOM.
- Source/runtime hashes match for the five managed files changed in the pipeline.
- `pipeline_state.source_hashes()`: passed and now includes `news_refresh_watchlist.py`.
- Live DB query for ticker 2330 returned canonical rows with clickable `link` values.
- Trigger construction produced eight independent starts: 08, 10, 12, 14, 16, 18, 20 and 22 local time.
- Groove-only smoke test: exit 0, receipt `last_status=ok`, data date `2026-10-06`, timeout 720 seconds.
- Certified `public/watchlist.html` SHA stayed `978D58367F15238082EDB8EC2B9C207A375682F65ED12C58224A6927124CBA90`.
- Certified `public/data/watchlist-full.json` SHA stayed `122A8FE92AB9B205D88B18B4E70E837E7958FDCD48352632C51B872C1105B0FE`.
- Live `C:\Groove-Lab\watchlist.html` changed to SHA `F2D92E2B4B24E07C6CE87CD57F56B89C5F586C1815E5DC0C404398F8EF9D937F`.
- Generated page: 109 dated canonical news links, newest `2026-10-06`, oldest `2026-10-02`, zero FinMind fallback notes, one explicit no-data note.
- GUI restarted successfully and is responsive. Its remaining SelfTest finding is only the not-yet-registered `tw-invest-suite-news-refresh` task.

## Files ready to use

- `scripts/db_client.py`
- `scripts/render_full_watchlist.py`
- `scripts/news_refresh_watchlist.py`
- `scripts/register_news_refresh.ps1`
- `scripts/publish_ghpages_daily.ps1`
- `scripts/pipeline_state.py`
- `C:\Users\icemo\.mavis\agents\mavis\workspace\tools\tw-pipeline-gui\TwPipelineMonitor.ps1`
- `C:\Users\icemo\.mavis\agents\mavis\workspace\tools\tw-pipeline-gui\trigger-2130-elevated.ps1`
- `C:\TankAkali\tw-pipeline-trigger-2130.bat`
- `C:\TankAkali\register_news_refresh.bat`

## Administrator steps still pending

1. Double-click `C:\Users\icemo\OneDrive\桌面\tw-pipeline-trigger-2130.lnk` and approve UAC. This changes only the daily trigger to 21:30 and verifies S4U/Limited/action preservation.
2. Double-click `C:\Users\icemo\OneDrive\桌面\註冊新聞刷新任務.lnk` and approve UAC. This registers the eight news refresh triggers with a 15-minute limit.
3. Re-run GUI SelfTest. Expected result: 20 watched tasks, 16 triggable tasks, zero errors.

Until step 1 is approved, tonight's nightly remains at 22:25. The 130-minute publisher wait still permits completion, but the release will not meet the desired before-23:00 target. Until step 2 is approved, the GUI button uses the validated direct-run fallback and the automatic eight-times-per-day schedule is inactive.
