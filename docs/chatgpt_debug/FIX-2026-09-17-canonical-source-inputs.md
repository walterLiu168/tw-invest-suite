# Canonical source readiness and final input freeze

## Problem

Sep16 nonnull/count checks certified empty margin responses and zero daytrade placeholders. Later provider data differed for171 institutional,1746 margin,1580 daytrade and1948 foreign-ownership rows. A14-day periodic range query returned its first day; independent audit caught1901 ownership discrepancies after the first attempted correction. Existing OHLCV presence checks also skipped354 volume revisions over30 report sessions.

## Changes

- Normal FinMind downloader supports forced six-phase canonical refresh, validates dated source fields/uniqueness/market readiness, rejects empty/all-zero market placeholders, and reads back exact committed values. No schema migration or manual manufactured SQL values.
- Periodic snapshots query target day first, then only missing symbols through a bounded14-day lookback. Actual source dates are logged.
- Nightly audits30 price sessions DB-first and repairs real provider revisions through the existing source transform/upsert; changed prices trigger derived recomputation.
- Nightly recomputes picks after final inputs without bypassing metadata/date gates, then freezes the sameUUID/date and refreshed picks. A240-session canonical-value digest rejects mid-generation data changes. Input preparation failures stop before rendering.
- Yfinance daily explicitly refreshes the preceding evening's still-within24h cache; fallback is classified correctly and cannot report a clean refresh. Market capitalization uses dated canonical close times issued shares when available.
- Live refresh exposed wrong Yahoo venue mapping: four-digit OTC symbols were sent as.TW and preferred symbols lost their final letter. Fresh FinMind listing metadata now resolves.TW/.TWO while preserving the entire security code; quote response security identity is checked. Yahoo workers use already maintained FinMind caches instead of starting parallel FinMind requests.
- Full nightly/manual path now prepares actual verified valuation caches before canonical refresh, coordinates with the standalone task through a shared Global mutex, and requires a sameUUID/date>=1900-symbol readback receipt. Dated market PER refresh uses one bulk snapshot; missing source tickers remain explicit. TTM ROE has its own30-day periodic cache and stays available on nontrading days without refreshing daily quotes.
- Provenance now68 hashes including finmind_batch/client; full stage deadlines230min, under4h task cap.

## Verification

- Downloader22 focused Python310 tests plus existing self-check pass.
- Main177-test full suite passes, including market identity, cache/receipt, periodic ROE, and screener tests. Native PowerShell5 parse passes.
- Live Sep16 normal writer1949 symbols/six lanes; independent institutional,margin,daytrade andshareholding comparisons now mismatch0.
- Historical354 volume discrepancies recovered through normal CLI over24 dates; independent30-session/58743-row OHLCV comparison is complete with0 differences,0 missing,0 duplicate source rows.
- Real Yahoo smoke verified1584.TWO/3293.TWO/2330.TW/2881A.TW. Real dated PER cache readback1945/1949; provider omits four TDR symbols9103/9105/9110/9136, which remain missing.

## Remaining acceptance

Full default S4U certification after deployment, actual valuation cache refresh, both remote rawSHA receipts/postflight and authorized Telegram chips message. Two Windows UAC reload attempts were canceled; do not retry or bypass without answering the pending authorization request. Old certified runs are historical evidence and cannot certify these repaired inputs. Physical sleep wake remains unproven. No claim that every240 warehouse table or every historical financial fact is verified.
