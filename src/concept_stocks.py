"""concept_stocks.py — 台股 10 大熱門概念股分類
手動維護，標籤以台股社群/法人常用為主
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "data" / "concept-stocks.json"

# 每個概念 = 1 個分類，含 ticker 清單 + 說明
CONCEPTS = {
    "半導體": {
        "icon": "💎",
        "desc": "晶圓代工 + IC 設計 + 記憶體 + 封測 + 設備",
        "tickers": [
            "2330", "2303", "6770", "5347",  # 晶圓代工
            "2454", "2379", "3034", "2376", "6669", "3443", "3529", "6531", "8016", "8044",
            "3527", "6415", "8054",  # IC 設計
            "2408", "2344", "2337", "3006", "8299",  # 記憶體
            "2325", "6239", "3711", "2449", "6510",  # 封測
            "3131", "2467", "3583", "6198", "6488",  # 設備
        ],
    },
    "AI 概念股": {
        "icon": "🤖",
        "desc": "AI 伺服器 / GPU / 散熱 / 高速傳輸",
        "tickers": [
            "2330", "2379", "6669", "3443", "3529", "2454",  # AI 晶片
            "3017", "2353", "6415", "3527", "5347", "5274",  # 高速傳輸/IP
            "2382", "6666", "6531",  # AI 伺服器
            "2345", "3293",  # 散熱
            "8299",  # CoWoS 封測
        ],
    },
    "蘋果供應鏈": {
        "icon": "🍎",
        "desc": "Apple iPhone/Mac/iPad 供應鏈",
        "tickers": [
            "2317", "2374", "5269", "2301", "2382", "3706",  # 主要組裝/零組件
            "2474", "5264", "1522", "3167", "5439", "3035",  # 金屬/光學
            "8299", "6752", "2357", "3014", "2352", "5443",  # 載板/封測
            "5371", "2455",  # 光通訊/散熱
        ],
    },
    "5G": {
        "icon": "📡",
        "desc": "基地台 / 射頻 / 光通訊 / 網通",
        "tickers": [
            "2345", "2324", "6285", "2455", "3675", "6138",
            "6666", "3293", "3593", "6282", "3494", "3362",
        ],
    },
    "銅箔基板 CCL": {
        "icon": "🟫",
        "desc": "PCB 上游 CCL 材料 (ABF/BT 載板)",
        "tickers": [
            "2383", "8044", "6213", "8039", "6279", "2368",
            "2405", "8054", "6643", "3715", "8227", "1815",
        ],
    },
    "矽智財 IP": {
        "icon": "🔐",
        "desc": "IC 設計上游 IP 授權 + EDA",
        "tickers": [
            "3529", "6533", "6643", "6213", "8054", "5274",
            "3583", "3035", "3527", "3167",
        ],
    },
    "機器人": {
        "icon": "🦾",
        "desc": "工業機器人 / 自動化 / 協作機器人",
        "tickers": [
            "2351", "2352", "2353", "2354", "2355", "2356",
            "2357", "2358", "2359", "2384", "2397", "2401",
            "1536", "4551", "6191", "3680", "5388", "8341",
        ],
    },
    "記憶體": {
        "icon": "💾",
        "desc": "DRAM / NAND Flash / NOR Flash",
        "tickers": [
            "2408", "2344", "2337", "3006", "8299",  # DRAM
            "2342", "2351", "3550",  # NOR
        ],
    },
    "電動車": {
        "icon": "🚗",
        "desc": "EV / 電池 / 車用電子 / 充電樁",
        "tickers": [
            "2308", "2317", "2301", "2454", "3006",  # 車用電子
            "2474", "2353",  # 車殼/連接器
            "1514", "1519", "1326",  # 車用扣件
            "2401", "1513",  # 充電
        ],
    },
    "重電綠能": {
        "icon": "⚡",
        "desc": "變壓器 / 太陽能 / 風電 / 儲能",
        "tickers": [
            "1513", "1519", "1503", "1504",  # 重電
            "1517", "2371", "1506",  # 變壓器
            "6443", "3576", "6244",  # 太陽能
            "1101", "1102",  # 水泥切入綠能
        ],
    },
}


def main():
    # 反向建立 ticker → concepts map
    ticker_to_concepts = {}
    for concept, info in CONCEPTS.items():
        for t in info["tickers"]:
            ticker_to_concepts.setdefault(t, []).append(concept)

    # 移除重複、排序
    for t in ticker_to_concepts:
        ticker_to_concepts[t] = sorted(set(ticker_to_concepts[t]))

    out = {
        "concepts": CONCEPTS,
        "ticker_to_concepts": ticker_to_concepts,
        "ticker_count": len(ticker_to_concepts),
        "concept_count": len(CONCEPTS),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[concepts] {OUT}")
    print(f"  {len(CONCEPTS)} concepts, {len(ticker_to_concepts)} tickers tagged")
    for name, info in CONCEPTS.items():
        print(f"  {name:12s} {info['icon']} {len(info['tickers']):3d} 檔")


if __name__ == "__main__":
    main()
