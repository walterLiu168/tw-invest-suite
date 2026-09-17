# Canonical source readiness and final input freeze

## Problem

Sep16 nonnull/count checks certified empty margin responses and zero daytrade placeholders. Later provider data differed for171 institutional,1746 margin,1580 daytrade and1948 foreign-ownership rows. A14-day periodic range query returned its first day; independent audit caught1901 ownership discrepancies after the first attempted correction. Existing OHLCV presence checks also skipped354 volume revisions over30 report sessions.

## Changes

- Normal FinMind downloader supports forced six-phase canonical refresh, validates dated source fields/uniqueness/market readiness, rejects empty/all-zero market placeholders, and reads back exact committed values. No schema migration or manual manufactured SQL values.
- Periodic snapshots query target day first, then only missing symbols through a bounded14-day lookback. Actual source dates are logged.
- Nightly audits30 price sessions DB-first and repairs real provider revisions through the existing source transform/upsert; changed prices trigger derived recomputation.
- Nightly recomputes picks after final inputs without bypassing metadata/date gates, then freezes the sameUUID/date and refreshed picks. A240-session canonical-value digest rejects mid-generation data changes. Input preparation failures stop before rendering.
- Yfinance daily explicitly refreshes the preceding evening's still-within24h cache; fallback is classified correctly and cannot report a clean refresh. Market capitalization uses dated canonical close times issued shares when available.

## Verification

- Downloader22 focused Python310 tests plus existing self-check pass.
- Main168-test full suite passes; two additional screener refresh tests pass (170 distinct tests covered). Native PowerShell5 parse passes.
- Live Sep16 normal writer1949 symbols/six lanes; independent institutional,margin,daytrade andshareholding comparisons now mismatch0.
- Historical354 volume discrepancies recovered through normal CLI over24 dates; independent30-session/58743-row OHLCV comparison is complete with0 differences,0 missing,0 duplicate source rows.

## Remaining acceptance

Full default S4U certification after deployment, actual valuation cache refresh, both remote rawSHA receipts/postflight and authorized Telegram chips message. Two Windows UAC reload attempts were canceled; do not retry or bypass without answering the pending authorization request. Old certified runs are historical evidence and cannot certify these repaired inputs. Physical sleep wake remains unproven. No claim that every240 warehouse table or every historical financial fact is verified.
