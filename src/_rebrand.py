"""rebrand to 坦克阿卡利
- Replace visible text "tw-invest-suite" → "坦克阿卡利"
- Keep URLs unchanged (GitHub Pages URL depends on repo name)
"""
import re
from pathlib import Path

ROOT = Path(r"C:\Users\icemo\Projects\tw-invest-suite")
PUBLIC = ROOT / "public"
NEW_BRAND = "坦克阿卡利"
OLD = "tw-invest-suite"

# 副檔名白名單 (要改的)
INCLUDE_EXT = {".html", ".json", ".md", ".txt"}

# 排除規則：包含這些的 match 不改 (URL, 路徑)
EXCLUDE_PATTERNS = [
    r"https?://",
    r"github\.com",
    r"href=[\"'][^\"']*",  # href= 開頭的
    r"src=[\"'][^\"']*",    # src= 開頭的
    r"data:",
    r"\.json[\"'\?]",       # .json 結尾
    r"\.css[\"'\?]",
    r"\.js[\"'\?]",
    r"manifest",
    r"sw\.js",
]

# HTML tags 內容要改
CONTENT_TAGS = ["title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "a", "div"]


def should_skip(context, pos):
    """檢查這個 match 周圍 context 是否在 URL/href 裡"""
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, context):
            return True
    return False


def rebrand_file(path: Path):
    text = path.read_text(encoding="utf-8")
    new_text = text
    changes = 0
    # Pattern 1: 在 content tag 裡 <title>tw-invest-suite</title>
    for tag in CONTENT_TAGS:
        pat = re.compile(rf"(<{tag}[^>]*>)([^<]*?{OLD}[^<]*?)(</{tag}>)", re.IGNORECASE)
        def repl(m):
            nonlocal changes
            inner = m.group(2)
            # 排除 URL/href
            if "href=" in inner or "src=" in inner or "http" in inner or "data:" in inner or ".css" in inner or ".js" in inner:
                return m.group(0)
            new_inner = inner.replace(OLD, NEW_BRAND)
            if new_inner != inner:
                changes += 1
            return m.group(1) + new_inner + m.group(3)
        new_text = pat.sub(repl, new_text)

    # Pattern 2: 在 meta property="og:title" content="..." 內
    for prop in ["og:title", "og:description", "og:site_name"]:
        pat = re.compile(rf'(<meta property="{prop}" content=")([^"]*?){OLD}([^"]*?)(">)', re.IGNORECASE)
        def repl_meta(m):
            nonlocal changes
            content = m.group(2) + OLD + m.group(3)
            if "http" in content:
                return m.group(0)
            changes += 1
            return m.group(1) + content.replace(OLD, NEW_BRAND) + m.group(4)
        new_text = pat.sub(repl_meta, new_text)

    # Pattern 3: 在 <meta name="description" content="..."> 內
    pat = re.compile(r'(<meta name="description" content=")([^"]*?)(>)')
    def repl_desc(m):
        nonlocal changes
        content = m.group(2)
        if OLD not in content:
            return m.group(0)
        changes += 1
        return m.group(1) + content.replace(OLD, NEW_BRAND) + m.group(3)
    new_text = pat.sub(repl_desc, new_text)

    if changes > 0 and new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return changes


def main():
    total = 0
    files_changed = 0
    for path in PUBLIC.rglob("*"):
        if not path.is_file() or path.suffix not in INCLUDE_EXT:
            continue
        # 跳過某些大檔避免出錯
        if path.stat().st_size > 5_000_000:
            continue
        n = rebrand_file(path)
        if n > 0:
            print(f"  {path.relative_to(ROOT)}: {n} changes")
            total += n
            files_changed += 1
    print(f"\nTotal: {total} changes in {files_changed} files")


if __name__ == "__main__":
    main()
