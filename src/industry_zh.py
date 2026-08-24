"""industry_zh.py — 繁體中文產業對照
優先順序：
  1. FinMind TaiwanStockInfo.industry_category (TWSE/TPEx 官方 48 分類)  ← 權威
  2. yfinance industry 對照表 (85 個細分類)
  3. yfinance sector 大類
  4. 原英文
"""
import json
import os
from pathlib import Path

# yfinance sector (大類) 備援
SECTOR_ZH = {
    "Basic Materials": "原物料",
    "Communication Services": "通訊服務",
    "Consumer Cyclical": "非必需消費",
    "Consumer Defensive": "必需消費",
    "Energy": "能源",
    "Financial Services": "金融",
    "Healthcare": "醫療保健",
    "Industrials": "工業",
    "Real Estate": "不動產",
    "Technology": "科技",
    "Utilities": "公用事業",
}

# yfinance industry (細類) 備援（如果沒在 tw-industry.json 裡）
INDUSTRY_ZH = {
    "Semiconductors": "半導體",
    "Semiconductor Equipment & Materials": "半導體設備",
    "Electronic Components": "電子零組件",
    "Computer Hardware": "電腦硬體",
    "Consumer Electronics": "消費電子",
    "Electronics & Computer Distribution": "電子通路",
    "Communication Equipment": "通訊設備",
    "Information Technology Services": "資訊服務",
    "Software - Application": "軟體應用",
    "Software - Infrastructure": "軟體基礎建設",
    "Solar": "太陽能",
    "Electronic Gaming & Multimedia": "遊戲多媒體",
    "Scientific & Technical Instruments": "科學儀器",

    "Specialty Industrial Machinery": "工業機械",
    "Engineering & Construction": "營建工程",
    "Building Products & Equipment": "建材設備",
    "Metal Fabrication": "金屬加工",
    "Aerospace & Defense": "航太國防",
    "Marine Shipping": "航運",
    "Integrated Freight & Logistics": "物流倉儲",
    "Airlines": "航空",
    "Trucking": "貨運",
    "Railroads": "鐵路",
    "Specialty Business Services": "商業服務",
    "Consulting Services": "顧問服務",
    "Advertising Agencies": "廣告",
    "Staffing & Employment Services": "人力資源",
    "Education & Training Services": "教育訓練",
    "Waste Management": "廢棄物處理",
    "Pollution & Treatment Controls": "環保",
    "Security & Protection Services": "安全監控",
    "Tools & Accessories": "工具機",
    "Business Equipment & Supplies": "辦公設備",

    "Auto Manufacturers": "汽車工業",
    "Auto Parts": "汽車零組件",
    "Auto & Truck Dealerships": "汽車經銷",
    "Apparel Manufacturing": "成衣",
    "Apparel Retail": "成衣零售",
    "Footwear & Accessories": "鞋類配件",
    "Leisure": "休閒娛樂",
    "Resorts & Casinos": "博弈度假",
    "Lodging": "飯店",
    "Restaurants": "餐飲",
    "Travel Services": "旅遊",
    "Specialty Retail": "專賣零售",
    "Home Improvement Retail": "居家修繕",
    "Department Stores": "百貨",
    "Grocery Stores": "超市",
    "Internet Retail": "網購零售",
    "Luxury Goods": "精品",
    "Furnishings, Fixtures & Appliances": "家具家電",
    "Recreational Vehicles": "休閒車",
    "Entertainment": "娛樂",
    "Broadcasting": "廣播電視",

    "Packaged Foods": "食品",
    "Beverages - Non-Alcoholic": "飲料",
    "Confectioners": "糖果",
    "Farm Products": "農產",
    "Agricultural Inputs": "農藥化肥",
    "Household & Personal Products": "日用品",
    "Tobacco": "菸草",

    "Steel": "鋼鐵",
    "Copper": "銅",
    "Aluminum": "鋁",
    "Other Industrial Metals & Mining": "其他金屬礦業",
    "Specialty Chemicals": "特用化學",
    "Chemicals": "化學",
    "Paper & Paper Products": "造紙",
    "Lumber & Wood Production": "木材",
    "Packaging & Containers": "包裝容器",
    "Building Materials": "建材",
    "Cement": "水泥",
    "Gold": "黃金",
    "Silver": "白銀",

    "Oil & Gas Refining & Marketing": "石油煉製",
    "Oil & Gas Equipment & Services": "石油設備",
    "Thermal Coal": "燃煤",
    "Uranium": "鈾",

    "Banks - Regional": "銀行",
    "Banks - Diversified": "綜合銀行",
    "Financial Conglomerates": "金控",
    "Insurance - Life": "壽險",
    "Insurance - Property & Casualty": "產險",
    "Insurance - Diversified": "綜合保險",
    "Insurance - Reinsurance": "再保險",
    "Capital Markets": "證券",
    "Asset Management": "資產管理",
    "Credit Services": "信貸",
    "Financial Data & Stock Exchanges": "金融交易所",

    "Biotechnology": "生技",
    "Drug Manufacturers - Specialty & Generic": "學名藥",
    "Drug Manufacturers - General": "製藥",
    "Medical Devices": "醫材",
    "Medical Instruments & Supplies": "醫療儀器",
    "Medical Distribution": "醫療通路",
    "Medical Care Facilities": "醫療機構",
    "Diagnostics & Research": "檢驗",
    "Healthcare Plans": "健保",

    "Real Estate - Development": "建設",
    "Real Estate - Diversified": "多元不動產",
    "Real Estate Services": "不動產服務",
    "REIT - Residential": "住宅 REIT",
    "REIT - Office": "辦公 REIT",
    "REIT - Retail": "零售 REIT",
    "REIT - Industrial": "工業 REIT",
    "REIT - Diversified": "多元 REIT",
    "REIT - Specialty": "特殊 REIT",
    "REIT - Healthcare Facilities": "醫療 REIT",

    "Utilities - Regulated Electric": "電力公用",
    "Utilities - Regulated Gas": "天然氣公用",
    "Utilities - Regulated Water": "自來水",
    "Utilities - Renewable": "再生能源",
    "Utilities - Independent Power Producers": "獨立發電",

    "Telecom Services": "電信",
    "Pay TV": "有線電視",
    "Entertainment - Distributors": "影視發行",
    "Internet Content & Information": "網路內容",

    "Conglomerates": "集團股",
    "Industrial Distribution": "工業經銷",
    "Electrical Equipment & Parts": "電機機械",
}

# TWSE/TPEx 官方 48 個分類（從 FinMind TaiwanStockInfo 拿到）
# 不在這裡 hard-code，因為每個 ticker 從 tw-industry.json 直接查
TW_PATH = Path(__file__).resolve().parent.parent / "public" / "data" / "tw-industry.json"

_TW_CACHE = None


def _load_tw():
    global _TW_CACHE
    if _TW_CACHE is None:
        if TW_PATH.exists():
            try:
                j = json.loads(TW_PATH.read_text(encoding="utf-8"))
                _TW_CACHE = j.get("by_ticker", {})
            except Exception:
                _TW_CACHE = {}
        else:
            _TW_CACHE = {}
    return _TW_CACHE


def refresh_tw_cache():
    """讓快取失效（fetch_tw_industry.py 跑完後可呼叫）"""
    global _TW_CACHE
    _TW_CACHE = None


def tw_industry(ticker):
    """從 tw-industry.json 查 ticker 的官方 TWSE/TPEx 分類"""
    return _load_tw().get(ticker, {}).get("industry", "") or ""


def tw_name(ticker):
    """從 tw-industry.json 查 ticker 的中文名"""
    return _load_tw().get(ticker, {}).get("name", "") or ""


def zh_industry(industry_en, sector_en=""):
    """英文 yfinance industry → 中文（fallback chain）"""
    if industry_en and industry_en in INDUSTRY_ZH:
        return INDUSTRY_ZH[industry_en]
    if sector_en and sector_en in SECTOR_ZH:
        return SECTOR_ZH[sector_en]
    return industry_en or sector_en or "未分類"


def zh_sector(sector_en):
    if sector_en and sector_en in SECTOR_ZH:
        return SECTOR_ZH[sector_en]
    return sector_en or "未分類"


def resolve(ticker, yf_industry="", yf_sector=""):
    """Best-effort 中文產業：
    1. TWSE/TPEx 官方 (tw-industry.json)
    2. yfinance industry 對照
    3. yfinance sector 對照
    4. 英文 fallback
    """
    tw = tw_industry(ticker)
    if tw:
        return tw
    return zh_industry(yf_industry, yf_sector)
