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
    # 页面分类标签非正文（如黄金策末 [[分類:術數]]），先于内链剥离去除
    text = re.sub(r"\[\[\s*(?:Category|分類|分类)\s*:[^]]*\]\]", "", text)

    def _tpl(m):
        inner = m.group(1)
        if inner.startswith("*|"):
            return inner[2:] if star_notes == "inline" else ""
        if inner.startswith("YL|"):
            return inner.split("|")[1]
        if inner.startswith("另|"):
            return inner.split("|")[1]   # 异文模板{{另|正文|一作}}取正文用字
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


# 2026-08 机扫裁定订正（断言恰一处后替换/删除；缘由详
# data/PROOFREADING.md 与 data/SUSPECTS.md）。作用于成形单元文本。
FIXES = {
    "京氏易传": [
        ("家人嗃嗃，父子嘻嘻", "家人嗃嗃，妇子嘻嘻",
         "引家人九三爻辞误字（近文「父父子子」串写）"),
        ("休复，元吉", "休复，吉",
         "引复六二爻辞衍「元」（邻行初九引文「元吉」串入）"),
        ("建起六四癸巳至戊戌", "建起癸巳至戊戌",
         "邻句「退位入六四」串入（六十四条建候体例皆无爻位）"),
        ("解者，散也", "解者，缓也",
         "引序卦传误字（近文「聚散以时」串写）"),
        ("六象，六包\n，四象分万物", "六象，六包，四象分万物",
         "按语剥离后拼回被其打断之句（管线）"),
        ("\n（五星从位起镇星，心宿从位降辛卯。）", "",
         "删今人（虎易）据体例推补句（原页自注非京氏原文）"),
    ],
    "火珠林": [
        ("戚磋若", "戚嗟若", "引离六五爻辞误字：磋→嗟"),
        ("封有三墓：宫基、鬼墓", "卦有三墓：宫墓、鬼墓",
         "封→卦、基→墓（同单元下文自证；首句漏列财墓待底本，不补）"),
        ("如中孚封，世持辛未", "如中孚卦，世持辛未", "封→卦"),
        ("寺观宙宇", "寺观庙宇", "宙→庙（同库两处「寺观庙宇」互证）"),
        ("来意俱不上封", "来意俱不上卦", "封→卦"),
        ("若乘土艾", "若乘土爻", "艾→爻（同单元「若不乘土爻」自证）"),
        ("世持辛末官墓", "世持辛未官墓", "末→未（干支）"),
        ("忌动爻应艾墓克之", "忌动爻应爻墓克之", "艾→爻"),
        ("皆被旁艾所隔", "皆被旁爻所隔", "艾→爻"),
        ("若财艾值断", "若财爻值断", "艾→爻"),
        ("第五爻申亲艾动", "第五爻申亲爻动", "艾→爻"),
        ("辰丑动雨、末戌动晴", "辰丑动雨、未戌动晴",
         "末→未（同单元三处「未戌动晴」自证）"),
        ("曰：—二三世", "曰：一二三世",
         "破折号当「一」（问句「一二三世易寻」自证）"),
        ("子托独发", "子孙独发", "托→孙（同单元「子孙独发」自证）"),
        ("父母、城池、壕寨、雄旗", "父母为城池、壕寨、雄旗",
         "补「为」（同句四项「X为Y」体例）"),
        ("逢坤则静．遇兑则说", "逢坤则静，遇兑则说", "全角句点归一作逗号"),
    ],
    "黄金策": [
        ("静须榖 ；生扶合世", "静须榖秕；生扶合世",
         "脱「秕」（《古今图书集成·艺术典》引同句「穀秕」互证）"),
        ("须防人春刑伤", "须防人眷刑伤", "春→眷（形近）"),
        ("子有跨褴之风", "子有跨灶之风", "褴→灶（跨灶成语）"),
        ("青龙父母，代居居船", "青龙父母，祖代居船",
         "脱「祖」衍「居」（《古今图书集成·艺术典》引同句互证）"),
        ("\n（右喜看弧帨说；）此段疑原文脱漏。", "", "删今人校勘按语行"),
        ("\n（此乃黄金策全篇结语）", "", "删页面编者说明"),
    ],
}


def apply_fixes(units, book, meta):
    fixes = FIXES.get(book, [])
    hits = {w: 0 for w, _, _ in fixes}
    for u in units:
        for w, r, _ in fixes:
            n = u["text"].count(w)
            if n:
                hits[w] += n
                u["text"] = u["text"].replace(w, r)
    for w, _, _ in fixes:
        assert hits[w] == 1, f"{book} 订正落空或多处命中: {w} ×{hits[w]}"
    if fixes:
        meta.setdefault("fixes", []).extend(
            f"{w}→{r or '（删）'}：{note}" for w, r, note in fixes)


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
    apply_fixes(units, "京氏易传", meta)
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
    apply_fixes(units, "火珠林", meta)
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
    apply_fixes(units, "黄金策", meta)
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
