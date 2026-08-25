"""藏书检索层：全部典籍的统一门面（数据模块的出口）。

三个入口：
    catalog()             藏书目录：书名、来源、许可、单元数、校对状态
    get(cite_id)          按引文编号取全文（跨易类与紫微两库）
    search(query, ...)    标点无关的关键词检索，返回命中单元与上下文摘要

检索是确定性查表加线性扫描——全部语料不足 1MB，内存即索引，
毫秒可回，无数据库、无向量库。将来语料涨到此法吃力时，在本模块
之下换 SQLite FTS 之类即可，三个入口不变。

命令行（数据模块自查用，亦可日常翻书）：
    python -m yijing_agent.corpus 大衍之数            # 关键词检索
    python -m yijing_agent.corpus --cite xici:shang:9  # 按编号取全文
    python -m yijing_agent.corpus --catalog            # 藏书目录
"""

import argparse
from functools import lru_cache

from . import strokes
from .knowledge import KnowledgeBase
from .ziwei.knowledge import ZiweiKB

#: 藏书划分：cite_id 前缀 → 所属书目。次序即目录次序。
BOOKS = [
    ("zhouyi", "周易（经文＋彖传＋象传）",
     ("zhouyi:", "tuan:", "daxiang:", "xiaoxiang:")),
    ("yizhuan", "易传补编（说卦、系辞、序卦、杂卦、文言）",
     ("shuogua:", "xici:", "xugua:", "zagua:", "wenyan:")),
    ("wangbi", "王弼《周易注》", ("wangbi:",)),
    ("meihua", "《梅花易数》卷一、卷二", ("meihua:",)),
    ("ziwei", "《紫微斗数全书》卷一至卷三", ("ziwei:",)),
]


@lru_cache(maxsize=1)
def _kbs():
    return KnowledgeBase(), ZiweiKB()


def _book_key(cite_id):
    for key, _title, prefixes in BOOKS:
        if cite_id.startswith(prefixes):
            return key
    return None


@lru_cache(maxsize=1)
def _units():
    """[(cite_id, source, text, 规整文, 规整→原文位置表)]，藏书目录次序。"""
    kb, zkb = _kbs()
    order = {key: i for i, (key, _t, _p) in enumerate(BOOKS)}
    rows = []
    for c in list(kb.citations()) + list(zkb.citations()):
        ntext, idx = _norm_map(c["text"])
        rows.append((c["cite_id"], c["source"], c["text"], ntext, idx))
    rows.sort(key=lambda r: (order.get(_book_key(r[0]), 99), r[0]))
    return rows


def _norm_map(s):
    """仅保留汉字，并记各汉字在原文中的位置（摘要定位用）。"""
    chars, idx = [], []
    for i, ch in enumerate(s):
        if "㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿":
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


def catalog():
    """藏书目录：[{key, work, source, license, units, proofread}, …]。"""
    kb, zkb = _kbs()
    metas = {"zhouyi": kb.meta, "yizhuan": kb.yizhuan_meta,
             "wangbi": kb.wangbi_meta, "meihua": kb.meihua_meta,
             "ziwei": zkb.meta}
    counts = {}
    for cid, *_rest in _units():
        key = _book_key(cid)
        counts[key] = counts.get(key, 0) + 1
    out = []
    for key, title, _prefixes in BOOKS:
        m = metas.get(key) or {}
        out.append({
            "key": key,
            "work": m.get("work") or m.get("title") or title,
            "source": m.get("source", ""),
            "license": m.get("license", "公版"),
            "units": counts.get(key, 0),
            "proofread": bool(m.get("proofread", False)),
        })
    sm = strokes.meta()
    out.append({"key": "strokes", "work": "汉字总笔画表（数据表，非典籍）",
                "source": sm.get("source", ""),
                "license": sm.get("license", ""),
                "units": sum(1 for n in strokes.counts() if n),
                "proofread": True})
    return out


def get(cite_id):
    """按引文编号取全文 → {cite_id, source, text}；未知编号 KeyError。"""
    kb, zkb = _kbs()
    for k in (kb, zkb):
        if k.has(cite_id):
            return k.citation(cite_id)
    raise KeyError(f"未知引文编号: {cite_id}（检索可用 search()）")


def search(query, limit=8, context=18):
    """标点无关关键词检索 → [{cite_id, source, snippet, count}, …]。

    query 只取其中汉字与全库规整文比对；每单元至多一条命中记录，
    snippet 为首处命中的原文上下文（含标点），count 为该单元命中次数。
    """
    nq, _ = _norm_map(query)
    if not nq:
        raise ValueError("检索词须含汉字")
    hits = []
    for cite_id, source, text, ntext, idx in _units():
        pos = ntext.find(nq)
        if pos < 0:
            continue
        count = ntext.count(nq)
        start, end = idx[pos], idx[pos + len(nq) - 1] + 1
        lo, hi = max(0, start - context), min(len(text), end + context)
        snippet = ("…" if lo else "") + text[lo:hi].replace("\n", " ") \
            + ("…" if hi < len(text) else "")
        hits.append({"cite_id": cite_id, "source": source,
                     "snippet": snippet, "count": count})
        if len(hits) >= limit:
            break
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m yijing_agent.corpus",
        description="藏书检索：关键词查典籍、按引文编号取全文、看藏书目录")
    ap.add_argument("query", nargs="*", help="检索关键词（标点无关）")
    ap.add_argument("--cite", help="按引文编号取全文，如 xici:shang:9")
    ap.add_argument("--catalog", action="store_true", help="打印藏书目录")
    ap.add_argument("--limit", type=int, default=8, help="检索结果条数上限")
    args = ap.parse_args(argv)

    if args.catalog:
        for b in catalog():
            mark = "已校" if b["proofread"] else "未校"
            print(f"[{b['key']}] {b['work']}（{b['units']} 单元，"
                  f"{b['license']}，{mark}）")
            if b["source"]:
                print(f"    来源：{b['source']}")
        return 0
    if args.cite:
        try:
            c = get(args.cite)
        except KeyError as e:
            print(e.args[0])
            return 1
        print(f"{c['source']}（{c['cite_id']}）")
        print(c["text"])
        return 0
    if not args.query:
        ap.print_help()
        return 1
    try:
        hits = search("".join(args.query), limit=args.limit)
    except ValueError as e:
        print(e)
        return 1
    if not hits:
        print("无命中。")
        return 1
    for h in hits:
        times = f"（{h['count']} 处）" if h["count"] > 1 else ""
        print(f"{h['source']}（{h['cite_id']}）{times}")
        print(f"    {h['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
