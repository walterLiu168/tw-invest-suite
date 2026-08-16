# Data — 資料說明

> 此目錄存放 schema 文件、範例資料、SQL schema。不放實際的 CSV/Parquet（太大，git 會爆）。

## 結構

```
data/
├── README.md              ← 你正在看
├── schema/
│   ├── mysql.sql          ← MySQL CREATE TABLE 語法
│   └── cache_format.md    ← Cache JSON 格式定義
├── samples/               ← 範例資料（少量）
│   ├── watchlist_sample.csv
│   └── industry_sample.csv
└── migrations/            ← 結構變更紀錄
    ├── 001_initial.sql
    ├── 002_add_sma_27.sql
    └── ...
```

## 實際資料位置

- **MySQL 倉儲**：`localhost:3306` / `tw_elec`
- **Cache**：`~/.cache_manager/`（每個 dataset 一個子資料夾）
- **Generated HTML**：`C:\Groove-Lab\analyze\`
- **部署目標**：
  - GitHub Pages：`walterLiu168.github.io/stock-report/`
  - groovelab.dev
