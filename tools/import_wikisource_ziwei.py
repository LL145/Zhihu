"""从中文维基文库《紫微斗數全書》导入紫微库第一期 → tianwen/data/ziwei.json。

范围（DESIGN §9 v2 第 2 项：十四主星入十二宫断语 + 庙旺平陷）：
- 卷二「一命宫」节：十四主星逐星之命宫断语（论断文 + 分宫格诗 +
  入男命/入女命/入限吉凶诀）；
- 卷二「二兄弟」至「十二父母」十一节：逐星入各宫断语（含昌曲辅弼
  禄存羊陀火铃空劫天马等辅煞与斗君行）；
- 卷一「诸星问答论」：十四主星及所安辅煞诸星问答（解读语境用）；
- 卷三「论大限十年祸福何如」「论二限太岁吉凶」（时运问语境用）。
庙陷表已单独转录为代码表（tianwen/ziwei/brightness.py），不入此库。

用法：
    python tools/import_wikisource_ziwei.py [--cache-dir .cache_ziwei] [--out tianwen/data/ziwei.json]

许可：维基文库文本 CC BY-SA 4.0（古籍原文公版，现代标点为贡献者所加）；
meta.pages 记录各页面 oldid 以为署名。繁→简用 OpenCC t2s。
订正（FIXES，逐条断言存在，详见 data/PROOFREADING.md）：
- 删卷二兄弟节廉贞行混入之现代白话「兄弟感情融洽，但兄弟不多。」；
- 「羊玲克害」误字订正为「羊铃克害」。
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
PAGES = ["紫微斗數全書/卷一", "紫微斗數全書/卷二", "紫微斗數全書/卷三"]

_cc = OpenCC("t2s")

MAIN14 = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府",
          "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"]

STAR_KEY = {
    "紫微": "ziwei", "天机": "tianji", "太阳": "taiyang", "武曲": "wuqu",
    "天同": "tiantong", "廉贞": "lianzhen", "天府": "tianfu", "太阴": "taiyin",
    "贪狼": "tanlang", "巨门": "jumen", "天相": "tianxiang", "天梁": "tianliang",
    "七杀": "qisha", "破军": "pojun",
    "文昌": "wenchang", "文曲": "wenqu", "左辅": "zuofu", "右弼": "youbi",
    "天魁": "tiankui", "天钺": "tianyue", "禄存": "lucun", "天马": "tianma",
    "擎羊": "qingyang", "陀罗": "tuoluo", "火星": "huoxing", "铃星": "lingxing",
    "地空": "dikong", "地劫": "dijie", "化禄": "hualu", "化权": "huaquan",
    "化科": "huake", "化忌": "huaji", "斗君": "doujun",
}

# 宫断语行首识别词（长词优先）→（本盘星名列表, 序秩）。
# 「天空」在《全书》中即空劫之空，对应本盘之地空（安星依〈天空地劫诀〉）。
_TOKENS = [
    ("文昌文曲", ["文昌", "文曲"], 14), ("文昌", ["文昌"], 14), ("文曲", ["文曲"], 14),
    ("左辅右弼", ["左辅", "右弼"], 15), ("左辅", ["左辅"], 15), ("右弼", ["右弼"], 15),
    ("天魁天钺", ["天魁", "天钺"], 16), ("魁钺", ["天魁", "天钺"], 16),
    ("禄存", ["禄存"], 17),
    ("擎羊陀罗", ["擎羊", "陀罗"], 18), ("羊陀", ["擎羊", "陀罗"], 18),
    ("擎羊", ["擎羊"], 18), ("陀罗", ["陀罗"], 18),
    ("羊铃", ["擎羊", "铃星"], 18),
    ("火铃", ["火星", "铃星"], 19), ("火星", ["火星"], 19), ("铃星", ["铃星"], 19),
    ("天空地劫", ["地空", "地劫"], 20), ("地空地劫", ["地空", "地劫"], 20),
    ("劫空", ["地空", "地劫"], 20), ("天空", ["地空"], 20),
    ("地劫", ["地劫"], 20), ("地空", ["地空"], 20),
    ("天马", ["天马"], 21),
    ("化禄", ["化禄"], 22), ("化权", ["化权"], 22),
    ("化科", ["化科"], 22), ("化忌", ["化忌"], 22),
    ("斗君", ["斗君"], 90),
] + [(s, [s], i) for i, s in enumerate(MAIN14)]

PALACES = [("二兄弟", "兄弟", "xiongdi"), ("三妻妾", "妻妾", "qiqie"),
           ("四子女", "子女", "zinv"), ("五财帛", "财帛", "caibo"),
           ("六疾厄", "疾厄", "jie"), ("七迁移", "迁移", "qianyi"),
           ("八奴仆", "奴仆", "nupu"), ("九官禄", "官禄", "guanlu"),
           ("十田宅", "田宅", "tianzhai"), ("十一福德", "福德", "fude"),
           ("十二父母", "父母", "fumu")]

# 卷一问答导入白名单：问答标题星名 →（本盘星名列表, cite 段）
WENDA = {
    "紫微": (["紫微"], "ziwei"), "天机": (["天机"], "tianji"),
    "太阳": (["太阳"], "taiyang"), "武曲": (["武曲"], "wuqu"),
    "天同": (["天同"], "tiantong"), "廉贞": (["廉贞"], "lianzhen"),
    "天府": (["天府"], "tianfu"), "太阴": (["太阴"], "taiyin"),
    "贪狼": (["贪狼"], "tanlang"), "巨门": (["巨门"], "jumen"),
    "天相": (["天相"], "tianxiang"), "天梁": (["天梁"], "tianliang"),
    "七杀": (["七杀"], "qisha"), "破军": (["破军"], "pojun"),
    "文昌": (["文昌"], "wenchang"), "文曲": (["文曲"], "wenqu"),
    "左辅": (["左辅"], "zuofu"), "右弼": (["右弼"], "youbi"),
    "天魁天钺": (["天魁", "天钺"], "kuiyue"), "禄存": (["禄存"], "lucun"),
    "天马": (["天马"], "tianma"), "擎羊": (["擎羊"], "qingyang"),
    "陀罗": (["陀罗"], "tuoluo"), "火": (["火星"], "huoxing"),
    "铃": (["铃星"], "lingxing"), "天空地劫": (["地空", "地劫"], "kongjie"),
    "化禄": (["化禄"], "hualu"), "化权": (["化权"], "huaquan"),
    "化科": (["化科"], "huake"), "化忌": (["化忌"], "huaji"),
}

FIXES = [
    ("兄弟感情融洽，但兄弟不多。", "", "删维基文库贡献者所加现代白话注"),
    ("羊玲克害", "羊铃克害", "误字：玲→铃"),
]

BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


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


def clean(text):
    text = _cc.convert(text)
    text = text.replace("<onlyinclude>", "").replace("</onlyinclude>", "")
    text = re.sub(r"<nowiki>.*?</nowiki>", "", text, flags=re.S)
    text = re.sub(r"\[\[(?:[^]|]*\|)?([^]]*)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)   # Header2/footer 等模板
    text = text.replace("'''", "")
    for wrong, right, _ in FIXES:
        w = _cc.convert(wrong)
        if w in text:
            text = text.replace(w, right)
    return text


def sections(text):
    """[(level, title, body)]，标题为 =…= 行。"""
    out = []
    heads = [(m.start(), m.end(), len(m.group(1)), m.group(2).strip())
             for m in re.finditer(r"^(=+)\s*(.+?)\s*=+\s*$", text, re.M)]
    for i, (s, e, lv, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out.append((lv, title, text[e:end]))
    return out


def _prose(lines):
    return "\n".join(l.strip() for l in lines if l.strip())


def _poem_split(body):
    """→ [('poem'|'text', 内容)] 依 <poem> 标签切块。"""
    out, pos = [], 0
    for m in re.finditer(r"<poem>(.*?)</poem>", body, re.S):
        if body[pos:m.start()].strip():
            out.append(("text", body[pos:m.start()]))
        out.append(("poem", m.group(1)))
        pos = m.end()
    if body[pos:].strip():
        out.append(("text", body[pos:]))
    return out


def parse_ming(body, records, warnings):
    """卷二「一命宫」节：十四主星（其后昌曲以下诸星本期不取）。"""
    pos = 0
    for star in MAIN14:
        key = STAR_KEY[star]
        marks = {}
        for tag, mark in (("male", "入男命吉凶诀"), ("female", "入女命吉凶诀"),
                          ("xian", "入限吉凶诀")):
            i = body.find(star + mark, pos)
            if i < 0 and tag == "female":   # 底本天梁无入女命诀
                warnings.append(f"命宫 {star} 无入女命吉凶诀")
                continue
            assert i >= 0, f"命宫节缺 {star}{mark}"
            marks[tag] = i
        head = body[pos:marks["male"]]
        chunks = _poem_split(head)
        prose = _prose(sum((c.splitlines() for k, c in chunks if k == "text"),
                           []))
        assert prose.startswith(star), f"命宫 {star} 论断文行首异常：{prose[:20]}"
        records[f"ziwei:2:ming:{key}"] = {
            "text": prose, "kind": "ming", "stars": [star], "palace": "命宫",
            "source": f"紫微斗数全书·卷二·命宫·{star}",
        }
        ge_lines = sum((c.splitlines() for k, c in chunks if k == "poem"), [])
        n = 0
        for line in ge_lines:
            line = line.strip()
            if not line:
                continue
            n += 1
            brs = [b for b in BRANCHES if b in line]
            if not brs:
                warnings.append(f"命宫 {star} 分宫格第{n}行无宫支：{line[:20]}")
            records[f"ziwei:2:ming:{key}:ge:{n}"] = {
                "text": line, "kind": "ge", "stars": [star], "palace": "命宫",
                "branches": brs,
                "source": f"紫微斗数全书·卷二·命宫·{star}（分宫格）",
            }
        for tag, label in (("male", "入男命吉凶诀"), ("female", "入女命吉凶诀"),
                           ("xian", "入限吉凶诀")):
            if tag not in marks:
                continue
            after = body[marks[tag]:]
            m = re.search(r"<poem>(.*?)</poem>", after, re.S)
            assert m, f"命宫 {star}{label} 无诗"
            records[f"ziwei:2:ming:{key}:{tag}"] = {
                "text": _prose(m.group(1).splitlines()), "kind": tag,
                "stars": [star], "palace": "命宫",
                "source": f"紫微斗数全书·卷二·{star}{label}",
            }
        m = re.search(r"<poem>.*?</poem>", body[marks["xian"]:], re.S)
        pos = marks["xian"] + m.end()


def _leading_token(line):
    for tok, stars, rank in _TOKENS:
        if line.startswith(tok):
            return tok, stars, rank
    return None


def parse_gong(body, palace, pkey, records, warnings):
    """卷二某宫节：逐星一行（可折行），按行首星名切分。

    - 节首非星名行为本宫总论（如子女宫「凡看子女先看本宫星宿…」）；
    - 主星须依《安南北斗诸星诀》序出现，序退视为折行并入前行；
    - 辅星各宫次序不一（如子女宫辅弼在昌曲之前），不限序，凡未出即为新条；
    - 行首「X同…」通常是折行（如妻妾宫太阳行折出「太阴同内助…」），
      仅当 X 恰为下一个未出主星时作新条（如迁移宫「紫微同左右…」）；
    - 官禄宫末「定公卿」等题名断诀各自成条。
    """
    text = re.sub(r"</?poem>", "", body)
    intro, entries, ding = [], [], []
    seen, last_main = set(), -1
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^定[一-鿿]{1,6}$", line):
            ding.append([line, []])
            continue
        if ding:
            ding[-1][1].append(line)
            continue
        hit = _leading_token(line)
        new = False
        if hit:
            tok, stars, rank = hit
            if line[len(tok):][:1] in ("同", "会"):
                nxt = next((s for s in MAIN14 if s not in seen), None)
                new = tok == nxt
            elif tok in seen:
                warnings.append(f"{palace}宫 {tok} 行重出，并入前行")
            elif rank < 14:
                new = rank > last_main
                if not new:
                    warnings.append(f"{palace}宫疑似折行（{tok}…序退），并入前行")
            else:
                new = True
        if new:
            entries.append((tok, stars, [line]))
            seen.add(tok)
            if rank < 14:
                last_main = rank
        elif entries:
            entries[-1][2].append(line)
        else:
            intro.append(line)
    if intro:
        records[f"ziwei:2:gong:{pkey}:zonglun"] = {
            "text": _prose(intro), "kind": "zonglun", "stars": [],
            "palace": palace,
            "source": f"紫微斗数全书·卷二·{palace}宫（总论）",
        }
    for n, (title, lines) in enumerate(ding, 1):
        assert lines, f"{palace}宫 {title} 无文"
        records[f"ziwei:2:gong:{pkey}:ding{n}"] = {
            "text": _prose(lines), "kind": "ding", "stars": [],
            "palace": palace,
            "source": f"紫微斗数全书·卷二·{palace}宫·{title}",
        }
    for s in MAIN14:
        if s not in seen:
            warnings.append(f"{palace}宫底本无{s}独立断语行（缺文，待校对）")
    for tok, stars, lines in entries:
        seg = "".join(STAR_KEY[s] for s in stars) if all(
            s in STAR_KEY for s in stars) else None
        assert seg, f"{palace}宫未知星 {tok}"
        records[f"ziwei:2:gong:{pkey}:{seg}"] = {
            "text": _prose(lines), "kind": "gong", "stars": stars,
            "palace": palace,
            "source": f"紫微斗数全书·卷二·{palace}宫诸星断语·{tok}",
        }


def parse_wenda(secs, records, warnings):
    got = set()
    for lv, title, body in secs:
        m = re.match(r"^问(.+?)(?:二?星)?所主(?:若何|如何|为何)", title)
        if not m:
            continue
        name = m.group(1)
        if name not in WENDA:
            continue
        stars, seg = WENDA[name]
        text = _prose(re.sub(r"</?poem>", "", body).splitlines())
        assert len(text) > 40, f"问答 {name} 过短"
        records[f"ziwei:1:wenda:{seg}"] = {
            "text": text, "kind": "wenda", "stars": stars, "palace": None,
            "source": f"紫微斗数全书·卷一·诸星问答论·问{name}",
        }
        got.add(seg)
    missing = {STAR_KEY[s] for s in MAIN14} - got
    assert not missing, f"问答缺主星：{missing}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(ROOT / ".cache_ziwei"))
    ap.add_argument("--out", default=str(ROOT / "tianwen" / "data" / "ziwei.json"))
    args = ap.parse_args()

    pages, texts = {}, {}
    for title in PAGES:
        d = fetch_page(title, args.cache_dir)
        pages[d["title"]] = d["oldid"]
        texts[title[-2:]] = clean(d["text"])

    records, warnings = {}, []

    secs2 = sections(texts["卷二"])
    body_ming = next(b for _, t, b in secs2 if re.sub(r"\s", "", t) == "一命宫")
    parse_ming(body_ming, records, warnings)
    for sect, palace, pkey in PALACES:
        body = next(b for _, t, b in secs2
                    if re.sub(r"\s", "", t) == sect.replace(" ", ""))
        parse_gong(body, palace, pkey, records, warnings)

    parse_wenda(sections(texts["卷一"]), records, warnings)

    for t3, seg, label in [("论大限十年祸福何如", "daxian", "论大限十年祸福何如"),
                           ("论二限太岁吉凶", "erxian", "论二限太岁吉凶")]:
        body = next(b for _, t, b in sections(texts["卷三"]) if t == t3)
        records[f"ziwei:3:{seg}"] = {
            "text": _prose(body.splitlines()), "kind": "lun", "stars": [],
            "palace": None, "source": f"紫微斗数全书·卷三·{label}",
        }

    # 质检：无 wiki 残留；现代语气词入警告队列
    for cid, r in records.items():
        assert not re.search(r"[{}<>\[\]=]|''", r["text"]), f"{cid} 有残留标记"
        assert r["text"], f"{cid} 空文本"
        if "的" in r["text"]:
            warnings.append(f"{cid} 含「的」，疑今语或误字，待校对")

    kinds = {}
    for r in records.values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"共 {len(records)} 条：{kinds}")
    print(f"警告 {len(warnings)} 条")

    out = {
        "meta": {
            "work": "紫微斗数全书（题陈抟撰）",
            "source": "中文维基文库《紫微斗數全書》卷一至卷三",
            "base_url": "https://zh.wikisource.org/wiki/",
            "pages": pages,
            "license": "文本 CC BY-SA 4.0（古籍原文公版，现代标点为维基文库贡献者所加）",
            "conversion": "繁→简 OpenCC t2s；《全书》「天空」（空劫之空）对应本盘星名「地空」",
            "fixes": [f"{w}→{r or '（删）'}：{note}" for w, r, note in FIXES],
            "imported": _dt.date.today().isoformat(),
            "proofread": False,
            "warnings": warnings,
        },
        "records": records,
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {args.out}")


if __name__ == "__main__":
    sys.exit(main())
