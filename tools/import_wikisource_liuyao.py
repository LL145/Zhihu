"""从中文维基文库导入六爻纳甲典籍层（v4 六爻起卦之典据先行）。

三书三库（藏书层：可检索可引用；不参与定例断辞，亦不入现行选文——
六爻纳甲起卦引擎为 v4 级，见 DESIGN.md 路线图）：

- 《京氏易传》（汉·京房撰）→ data/jingfang.json
  页面为标点白文＋{{*|…}}注（陆绩注与录入者按语混杂，机器不可分），
  只取京氏本文，注文一律不取（与易传补编「只取传文」同律）。
  单元：八宫六十四卦逐卦一条（jingfang:{hid}，hid 为周易通行卦序 id，
  逐条以卦符 ䷀–䷿ 码位交叉核验）；卷下总说／算法／总结三条
  （jingfang:xia:{n}；「算法」「总结」小标题为页面所加）。
- 《火珠林》（旧题宋·麻衣道者）→ data/huozhulin.json
  {{*|…}}为原书注文（「注云…」体），并入正文；逐节一条
  （huozhulin:{n}）。页面自注「节录」之节记入 warnings。
- 《黄金策》（题明·刘基；页面电子文自注按《卜筮正宗》本全文载录）
  → data/huangjince.json；逐章一条（huangjince:{n}），
  今人所加章节序号自标题剥离。

用法：
    python tools/import_wikisource_liuyao.py [--cache-dir .cache_liuyao]

许可：维基文库文本 CC BY-SA 4.0（古籍原文公版，现代标点为贡献者
所加）；meta.pages 记录页面 oldid 以为署名。繁→简 OpenCC t2s，
乾字全字保护不转干，遯统一作遁（与王弼注导入同律）。
"""

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).parent.parent
API = "https://zh.wikisource.org/w/api.php"
UA = "TianwenAgent/0.1 (typiary import; github LL145/Zhihu)"
CA = "/root/.ccr/ca-bundle.crt"
LICENSE = "文本 CC BY-SA 4.0（古籍原文公版，现代标点为维基文库贡献者所加）"

_cc = OpenCC("t2s")

#: 页面卦名 → 知识库卦名（OpenCC 单字直转不可靠或知识库用全名者）
_NAME_FIX = {"坎": "习坎", "遯": "遁"}


def t2s(s):
    """繁→简，乾字全字保护（本语料中乾均指乾卦），遯统一作遁。"""
    s = s.replace("乾", "")
    s = _cc.convert(s)
    return s.replace("", "乾").replace("遯", "遁")


def fetch_page(title, cache_dir):
    f = Path(cache_dir) / (title.replace("/", "__") + ".json")
    if f.exists():
        return json.loads(f.read_text("utf-8"))
    url = (API + "?action=query&prop=revisions&rvprop=content%7Cids"
           "&rvslots=main&format=json&titles=" + urllib.parse.quote(title))
    for i in range(6):
        r = subprocess.run(
            ["curl", "-sS", "--cacert", CA, "-H", f"User-Agent: {UA}", url],
            capture_output=True, text=True, timeout=120)
        try:
            d = json.loads(r.stdout)
            p = list(d["query"]["pages"].values())[0]
            rev = p["revisions"][0]
            out = {"title": p["title"], "oldid": rev["revid"],
                   "text": rev["slots"]["main"]["*"]}
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            return out
        except (json.JSONDecodeError, KeyError):
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"抓取失败：{title}")


def clean(text, star_notes):
    """通用清洗。star_notes：'inline' 并入 {{*|…}} 注文，'drop' 丢弃。

    模板由内而外逐层消解（{{*|…}} 注内可嵌 {{YL|…}} 纪年等模板）：
    {{*|…}} 依 star_notes 取舍；{{YL|干支|公元}} 取干支；其余模板
    （Header、annotate 今人按语、banner 等）一律丢弃。wiki 表格
    （{| … |}，如京氏卷下八宫卦序表）为版式图表，不入文本单元。
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"</?onlyinclude>", "", text)
    text = re.sub(r"</?(?:poem|pre)[^>]*>", "", text)   # 标签去、文字留
    text = re.sub(r"-\{(.*?)\}-", r"\1", text)          # 转换保护标记
    text = re.sub(r"^\{\|.*?^\|\}", "", text, flags=re.S | re.M)

    def _tpl(m):
        inner = m.group(1)
        if inner.startswith("*|"):
            return inner[2:] if star_notes == "inline" else ""
        if inner.startswith("YL|"):
            return inner.split("|")[1]
        return ""

    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\{\{([^{}]*)\}\}", _tpl, text, flags=re.S)
    text = re.sub(r"\[\[(?:[^]|]*\|)?([^]]*)\]\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    return t2s(text)


def sections(text):
    """[(level, title, body)]，标题为 =…= 行。"""
    out = []
    heads = [(m.start(), m.end(), len(m.group(1)), m.group(2).strip())
             for m in re.finditer(r"^(=+)\s*(.+?)\s*=+\s*$", text, re.M)]
    for i, (s, e, lv, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out.append((lv, title, text[e:end]))
    return out


def _prose(body):
    lines = [re.sub(r"\s+", " ", l.strip(": ").strip())
             for l in body.splitlines()]
    return "\n".join(l for l in lines if l)


def check_units(units, warnings, book):
    seen = set()
    for u in units:
        assert u["id"] not in seen, f"{book} 单元重出：{u['id']}"
        seen.add(u["id"])
        assert u["text"], f"{book} {u['id']} 空文本"
        for ch in "{}<>=":
            assert ch not in u["text"], f"{book} {u['id']} 有残留标记 {ch}"
        if "节录" in u["title"]:
            warnings.append(f"{u['id']}（{u['title']}）：页面自注为节录，非全文")


def meta_of(work, short, page, oldid, conversion, warnings):
    return {
        "work": work,
        "short": short,
        "source": f"中文维基文库《{page}》",
        "base_url": "https://zh.wikisource.org/wiki/",
        "pages": {page: oldid},
        "license": LICENSE,
        "conversion": conversion,
        "imported": _dt.date.today().isoformat(),
        "proofread": False,
        "warnings": warnings,
    }


def import_jingfang(cache_dir, hex_names):
    d = fetch_page("京氏易傳", cache_dir)
    text = clean(d["text"], star_notes="drop")
    units, warnings, xia = [], [], 0
    for lv, title, body in sections(text):
        prose = _prose(body)
        if lv == 2 and "卷下" in title:
            xia = 1
            if prose:
                units.append({"id": "xia:1", "title": "卷下·总说",
                              "text": prose})
            continue
        if lv == 2:
            continue
        if xia:
            xia += 1
            units.append({"id": f"xia:{xia}", "title": f"卷下·{title}",
                          "text": prose})
            continue
        parts = title.split()
        assert len(parts) == 3, f"京氏卦题异常：{title}"
        symbol, name = parts[0], _NAME_FIX.get(parts[2], parts[2])
        hid = ord(symbol) - 0x4DC0 + 1
        assert 1 <= hid <= 64 and hex_names[hid] == name, \
            f"京氏卦符与卦名不符：{title}（符指 {hex_names.get(hid)}）"
        assert prose, f"京氏 {name} 空文本"
        units.append({"id": str(hid), "title": name, "text": prose})
    gua = [u for u in units if u["id"].isdigit()]
    assert len(gua) == 64, f"京氏卦单元 {len(gua)} ≠ 64"
    assert xia >= 2, "京氏卷下缺算法/总结"
    check_units(units, warnings, "京氏易传")
    meta = meta_of(
        "京氏易传（汉·京房撰）", "京氏易传", d["title"], d["oldid"],
        "繁→简 OpenCC t2s，乾字保护，遯作遁；只取京氏本文，"
        "{{*|…}}注文（陆绩注与录入者按语混杂）一律不取；"
        "卦单元 id 为周易通行卦序，逐条以卦符 ䷀–䷿ 码位核验；"
        "「卷下·算法」「卷下·总结」小标题为页面所加",
        warnings)
    return {"meta": meta, "units": units}


def import_huozhulin(cache_dir):
    d = fetch_page("火珠林", cache_dir)
    text = clean(d["text"], star_notes="inline")
    units, warnings = [], []
    for n, (lv, title, body) in enumerate(sections(text), 1):
        title = re.sub(r"^附(\d+)\s*", "附：", title)
        prose = _prose(body)
        assert prose, f"火珠林「{title}」空文本"
        units.append({"id": str(n), "title": title, "text": prose})
    assert len(units) >= 80, f"火珠林仅 {len(units)} 节"
    check_units(units, warnings, "火珠林")
    meta = meta_of(
        "火珠林（旧题宋·麻衣道者）", "火珠林", d["title"], d["oldid"],
        "繁→简 OpenCC t2s，乾字保护，遯作遁；{{*|…}}为原书注文"
        "（「注云…」体），并入正文；「附」节序号剥离",
        warnings)
    return {"meta": meta, "units": units}


def import_huangjince(cache_dir):
    d = fetch_page("黄金策", cache_dir)
    raw = d["text"]
    # 今人插注（断言存在后删除，记入 meta.fixes）：
    # 总断千金赋节内「注釋:」起之应期白话块（至空行止）；词讼章「註記:」按语行。
    assert raw.count("注釋:") == 1 and raw.count("註記:") == 1, "黄金策今人插注位点变动"
    raw = re.sub(r"^注釋:.*?(?=^\s*$)", "", raw, flags=re.S | re.M)
    raw = re.sub(r"^註記:.*$", "", raw, flags=re.M)
    assert "注釋" not in raw and "註記" not in raw
    text = clean(raw, star_notes="inline")
    units, warnings = [], [
        "页面标点半角/全角混用（如「子伏財飛,簷下曝夫猶抑鬱」行），未作归一，待校对"]
    for n, (lv, title, body) in enumerate(sections(text), 1):
        title = re.sub(r"^(附)?\d+[、：:]\s*", lambda m: "附：" if m.group(1)
                       else "", title)
        prose = _prose(body)
        assert prose, f"黄金策「{title}」空文本"
        units.append({"id": str(n), "title": title, "text": prose})
    assert len(units) >= 30, f"黄金策仅 {len(units)} 章"
    check_units(units, warnings, "黄金策")
    meta = meta_of(
        "黄金策（题明·刘基）", "黄金策", d["title"], d["oldid"],
        "繁→简 OpenCC t2s，乾字保护，遯作遁；页面电子文自注按"
        "《卜筮正宗》本全文载录；今人所加章节序号自标题剥离",
        warnings)
    meta["fixes"] = ["删总断千金赋节内今人「注釋:」应期白话块",
                     "删词讼章今人「註記:」按语行"]
    return {"meta": meta, "units": units}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(ROOT / ".cache_liuyao"))
    ap.add_argument("--out-dir", default=str(ROOT / "tianwen" / "data"))
    args = ap.parse_args()

    hexes = json.loads(
        (ROOT / "tianwen" / "data" / "hexagrams.json").read_text("utf-8"))
    hex_names = {h["id"]: h["name"] for h in hexes["hexagrams"]}

    out_dir = Path(args.out_dir)
    for fname, data in [
        ("jingfang.json", import_jingfang(args.cache_dir, hex_names)),
        ("huozhulin.json", import_huozhulin(args.cache_dir)),
        ("huangjince.json", import_huangjince(args.cache_dir)),
    ]:
        path = out_dir / fname
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        m = data["meta"]
        print(f"{m['work']}：{len(data['units'])} 单元，"
              f"警告 {len(m['warnings'])} 条 → {path}")


if __name__ == "__main__":
    sys.exit(main())
