# Third-party notices and data-provider boundaries

版本：2026-09-21

## Code dependencies

The public source release uses these optional/runtime components. Their upstream terms remain authoritative:

| Component | Use | Upstream notice |
|---|---|---|
| `yfinance` | Yahoo Finance market and valuation access | [Apache-2.0 metadata](https://github.com/ranaroussi/yfinance/blob/main/pyproject.toml) |
| Chart.js 4.x | Browser charts in generated pages | [MIT license](https://github.com/chartjs/Chart.js/blob/master/LICENSE.md) |
| PyMySQL, requests, pandas, NumPy, certifi | Core Python runtime | See the installed package metadata and each upstream distribution notice |
| scikit-learn, XGBoost, Pillow, python-dotenv, FinLab, Playwright | Optional integrations | Install only when needed and retain their upstream notices |

The repository's `LICENSE` covers this project's own source. It does not relicense provider data, generated market data, trademarks, or third-party libraries.

## Market-data terms

- TWSE/TPEx, FinMind and Yahoo Finance data remain subject to their provider terms, rate limits, attribution rules and plan-specific redistribution rights.
- FinMind explicitly states that data-license scope depends on the selected plan; review the [FinMind terms and data licensing page](https://finmind.github.io/en/PrivacyPolicy/) before redistributing historical raw data or operating a public mirror.
- The default source release contains code and configuration templates. Treat generated historical data and provider responses as a separate release decision.

## Product boundary

This project is for research and education. It does not provide investment advice, execute orders, or guarantee data completeness, timeliness or performance.
