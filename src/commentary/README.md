# Commentary — LLM 每日早報

> 自動對 watchlist 24 檔精選做 LLM 評論，產出 markdown 早報。

## 用法

### 1. 設定 LLM API key

支援任何 OpenAI-compatible endpoint：

```powershell
# OpenAI
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_API_KEY = "sk-..."
$env:LLM_MODEL = "gpt-4o"

# Anthropic (via proxy)
$env:LLM_BASE_URL = "https://api.anthropic.com/v1"
$env:LLM_API_KEY = "sk-ant-..."
$env:LLM_MODEL = "claude-3-5-sonnet-20241022"

# 或本地 Ollama
$env:LLM_BASE_URL = "http://localhost:11434/v1"
$env:LLM_API_KEY = "ollama"
$env:LLM_MODEL = "llama3.1:70b"
```

### 2. 跑

```powershell
# Dry-run（不真的打 LLM，看 prompt 對不對）
python src\commentary\daily_commentary.py --dry-run

# 真的跑
python src\commentary\daily_commentary.py

# 指定 run_id
python src\commentary\daily_commentary.py --run-id 7

# 自訂輸出
python src\commentary\daily_commentary.py --out outputs\my_report.md
```

預設輸出到 `outputs/commentary/<date>.md`。

## 輸出格式

LLM 會被 prompt 強制按以下 4 段格式輸出：

1. **大盤速覽**（2-3 段）— 指數、量能、法人、市場情緒
2. **24 檔精選速評** — 每檔：判斷 / 理由 / 進場停損 / 風險
3. **跨檔觀察**（2 段）— 共同主題、反向訊號
4. **行動建議**（3-5 點）

範例（看 `outputs/commentary/2026-08-16.md`）。

## 整合到 daily batch

`run_daily.ps1` 可以加：
```powershell
# Stage 6: LLM commentary (after publish)
& python "$PSScriptRoot\src\commentary\daily_commentary.py"
```

## 為什麼要這個

- 24 檔的 cross-source 數據用人腦消化要 30+ 分鐘
- LLM 30 秒給出可閱讀的早報
- 強制結構化輸出（4 段、每段明確）
- 直接拿給客戶看

## 已知限制

- 第一次跑可能 LLM 還沒回完就 timeout（180s），可調 `LLM_MAX_TOKENS` 環境變數
- LLM 不知道當天新聞（只給 24h DB 內的）
- 沒有「昨天對今天的預測準不準」feedback loop
- 週末/國定假日跑出來的 prompt 跟平日一樣（沒有日期過濾）

## 改進方向

- [ ] 加入「昨日預測 vs 今日實際」對照章節
- [ ] LLM 多輪（先問大盤，再問個股）
- [ ] 自動推播到 Telegram / Email
- [ ] LLM 評分（每天對自己評分，由 feedback 改 prompt）
