"""汉字总笔画表（字占取画数用）。

数据由 tools/import_unihan_strokes.py 自 Unicode 官方 Unihan 数据库
（kTotalStrokes，现代通行总笔画）导入为 data/strokes.json，附版本与
许可信息；覆盖 U+3400–U+9FFF（CJK 扩展A区＋基本区）。

古籍计画偶与今异（如《梅花易数·西林寺牌额占》记「西」为七画，今作
六画），故约定一律依本表，起卦凭证逐字列明画数以便核对。
"""

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "strokes.json"


@lru_cache(maxsize=1)
def _table():
    d = json.loads(_DATA.read_text("utf-8"))
    return d["meta"], d["counts"]


def meta() -> dict:
    """数据来源信息（Unicode 版本、许可等），入起卦凭证。"""
    return _table()[0]


def total_strokes(ch):
    """单字总笔画数；不在表内（非汉字或罕见字）返回 None。"""
    m, counts = _table()
    idx = ord(ch) - m["start"]
    if 0 <= idx < len(counts) and counts[idx]:
        return counts[idx]
    return None
