"""从中文维基文库导入易传补编：说卦 + 系辞上下 + 序卦 + 杂卦 + 乾坤文言。

来源（CC BY-SA 4.0；经传原文为公版，页面标点为维基文库贡献者所加）：
  - 说卦：周易正義/09.01 至 09.11 各页之经文部分（{{*|韩康伯注}}
    与 [疏] 孔疏一律丢弃，只收传文）。十一页拼成一流后按朱子
    《周易本义》十一章之章首语切分——不依赖页面边界；类象诸章
    （八、九、十、十一）再按八卦切分，供梅花体用取象逐卦引据。
  - 文言：周易正義/01乾（{{+|经文}} 模板体例）与 01坤（裸行体例）
    页面《文言》曰以下之传文，按所释经文单元（卦辞/爻位/用九）
    锚定归段。锚点表为手工整理（记入 meta），文本本身逐字出自页面。
  - 系辞上下、序卦、杂卦：白文《易傳》页面（易傳/繫辭上、繫辭下、
    序卦、雜卦）。不取《周易正義》卷七、卷八、卷十、卷十一者，因
    彼处韩康伯注有未走 {{*|}} 模板、与传文裸行混排者，机器无法
    可靠剥离；白文页面无注，逐字可据。章次依页面所分（系辞上
    十二章、下九章），杂卦页面另有「校詁版」一节不取（异文记入
    meta.variants）。

用法：
    python tools/import_wikisource_yizhuan.py [--cache-dir DIR] [--out FILE]
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from opencc import OpenCC

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yijing_agent.knowledge import KnowledgeBase  # noqa: E402
from yijing_agent.trigrams import PINYIN  # noqa: E402
from yijing_agent.validator import normalize  # noqa: E402

API = "https://zh.wikisource.org/w/api.php"
UA = "ZhihuYijingAgent/0.1 (yijing_agent data import; one-off)"
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"

_cc = OpenCC("t2s")


def t2s(s):
    """繁→简，保护乾字（本语料乾均指乾卦），遯统一作遁。"""
    s = s.replace("乾", "")
    s = _cc.convert(s)
    return s.replace("", "乾").replace("遯", "遁")


def api(params, tries=8):
    url = API + "?" + urllib.parse.urlencode(dict(params, format="json"))
    cmd = ["curl", "-s", "--max-time", "60", "-A", UA, url]
    if Path(CA_BUNDLE).exists():
        cmd[1:1] = ["--cacert", CA_BUNDLE]
    for i in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            time.sleep(45 if "too many requests" in out else 10 * (i + 1))
    raise RuntimeError("Wikisource API 连续失败: " + url)


def fetch_page(title, cache_dir=None):
    if cache_dir:
        f = Path(cache_dir) / (title.replace("/", "__") + ".json")
        if f.exists():
            d = json.loads(f.read_text("utf-8"))
            return d["oldid"], d["text"]
    d = api({"action": "query", "titles": title, "prop": "revisions",
             "rvprop": "ids|content", "rvslots": "main"})
    rev = list(d["query"]["pages"].values())[0]["revisions"][0]
    oldid, text = rev["revid"], rev["slots"]["main"]["*"]
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        (Path(cache_dir) / (title.replace("/", "__") + ".json")).write_text(
            json.dumps({"oldid": oldid, "text": text}, ensure_ascii=False), "utf-8")
    return oldid, text


def clean_wiki(s):
    """去语言转换标记 / 链接 / 注释 / 残余模板。"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)

    def conv(m):
        inner = m.group(1)
        if ";" in inner or ":" in inner:
            pairs = dict(p.split(":", 1) for p in inner.split(";") if ":" in p)
            return pairs.get("zh-hans") or pairs.get("zh") or \
                next(iter(pairs.values()), "")
        return inner
    s = re.sub(r"-\{(?:[A-Za-z]+\|)?(.*?)\}-", conv, s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    return s.strip()


def scripture_lines(text, drop_before=None):
    """页面 → 传文行序列：剥 header，弃疏与注（{{*|}} 内联剥除），
    {{+|经文}} 模板取其内文，其余裸行原样保留。"""
    lines = text.splitlines()
    i = 0
    if lines and lines[0].startswith("{{header"):
        while i < len(lines) and lines[i].strip() != "}}":
            i += 1
        i += 1
    out = []
    for raw in lines[i:]:
        s = raw.strip().lstrip(":").strip()
        if not s or s.startswith(("==", "[[", "{{footer", "----", "__")):
            continue
        if "{{批|" in s or s.startswith(("[疏]", "【疏】")):
            continue
        s = re.sub(r"\{\{\*\|.*?\}\}", "", s)          # 内联注剥除
        parts = re.findall(r"\{\{\+\|(.*?)\}\}", s)    # 模板经文
        if parts:
            for p in parts:
                p = t2s(clean_wiki(p))
                if p:
                    out.append(p)
            continue
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)           # 残余模板
        s = t2s(clean_wiki(s))
        if s:
            out.append(s)
    return out


def norm_map(s):
    chars, idx = [], []
    for i, ch in enumerate(s):
        if "㐀" <= ch <= "鿿":
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


# ── 说卦 ────────────────────────────────

#: 朱子《周易本义》十一章之章首语（简体、去标点）
CHAPTER_OPENINGS = [
    (1, "昔者圣人之作易也幽赞"),
    (2, "昔者圣人之作易也将以顺性命之理"),
    (3, "天地定位"),
    (4, "雷以动之"),
    (5, "帝出乎震"),
    (6, "神也者"),
    (7, "乾健也"),
    (8, "乾为马"),
    (9, "乾为首"),
    (10, "乾天也"),
    (11, "乾为天"),
]

_TRIGRAM_ORDER = ("乾", "坤", "震", "巽", "坎", "离", "艮", "兑")

#: 类象诸章的逐卦起始语
TRIGRAM_STARTS = {
    8: {g: f"{g}为" for g in _TRIGRAM_ORDER},
    9: {g: f"{g}为" for g in _TRIGRAM_ORDER},
    10: {"乾": "乾天也", "坤": "坤地也", "震": "震一索", "巽": "巽一索",
         "坎": "坎再索", "离": "离再索", "艮": "艮三索", "兑": "兑三索"},
    11: {g: f"{g}为" for g in _TRIGRAM_ORDER},
}

_PAGE_FURNITURE = re.compile(r"^说卦(卷九|第九)")


def parse_shuogua(pages_text, warnings):
    """11 页拼流 → [(id, gua|None, text)]。章界依章首语，不依页面边界。"""
    lines = []
    for text in pages_text:
        for ln in scripture_lines(text):
            if _PAGE_FURNITURE.match(normalize(ln)):
                continue
            lines.append(ln)
    stream = "".join(lines)
    ns, idx = norm_map(stream)

    cuts = []
    pos = 0
    for ch, opening in CHAPTER_OPENINGS:
        p = ns.find(opening, pos)
        assert p >= 0, f"说卦第{ch}章章首语未找到: {opening}"
        cuts.append((ch, p))
        pos = p + len(opening)
    units = []
    for k, (ch, p) in enumerate(cuts):
        end = cuts[k + 1][1] if k + 1 < len(cuts) else len(ns)
        raw = stream[idx[p]:idx[end] if end < len(ns) else len(stream)]
        if ch not in TRIGRAM_STARTS:
            units.append((str(ch), None, raw.strip()))
            continue
        # 类象章：按八卦顺序切分
        nch, cidx = norm_map(raw)
        gpos, q = [], 0
        for g in _TRIGRAM_ORDER:
            gp = nch.find(TRIGRAM_STARTS[ch][g], q)
            assert gp >= 0, f"说卦第{ch}章 {g} 段未找到"
            gpos.append((g, gp))
            q = gp + 1
        for j, (g, gp) in enumerate(gpos):
            gend = gpos[j + 1][1] if j + 1 < len(gpos) else len(nch)
            seg = raw[cidx[gp]:cidx[gend] if gend < len(nch) else len(raw)]
            units.append((f"{ch}:{PINYIN[g]}", g, seg.strip()))
        if gpos[0][1] > 0:
            warnings.append(f"说卦第{ch}章卦段前有引语并入上一单元外: "
                            f"{raw[:cidx[gpos[0][1]]][:30]}")
    return units


# ── 系辞 / 序卦 / 杂卦（白文《易傳》页面）────────

XICI_PAGES = {"shang": "易傳/繫辭上", "xia": "易傳/繫辭下"}
XUGUA_PAGE = "易傳/序卦"
ZAGUA_PAGE = "易傳/雜卦"

_CH_ORDER = ("一", "二", "三", "四", "五", "六", "七", "八", "九",
             "十", "十一", "十二")


def parse_plain_sections(text):
    """白文《易傳》页面 → {节名简体: 正文}。二级节（== 第一章 ==），
    段落以换行相接；{{gap}}/链接/转换标记剥除，行首 : 缩进剥除。"""
    sections, current, buf = {}, None, []

    def flush():
        if current is not None:
            sections[current] = "\n".join(buf).strip()

    for raw in text.splitlines():
        s = raw.strip()
        m = re.fullmatch(r"==\s*([^=].*?)\s*==", s)
        if m:
            flush()
            current, buf = t2s(m.group(1)), []
            continue
        s = s.lstrip(":").strip()
        if not s or s.startswith(("{{Header", "{{header", "{{NoteTA",
                                  "{{footer", "----", "__")):
            continue
        s = re.sub(r"'{2,}", "", s)
        s = re.sub(r"\{\{[Gg]ap\}\}", "", s)
        s = t2s(clean_wiki(re.sub(r"\{\{[^{}]*\}\}", "", s)))
        if s:
            buf.append(s)
    flush()
    return sections


def parse_xici(part, text, warnings):
    """系辞上/下页面 → [(章号, text)]。章节名须为「第N章」且连续。"""
    sections = parse_plain_sections(text)
    units = []
    for n, ch in enumerate(_CH_ORDER, 1):
        name = f"第{ch}章"
        if name not in sections:
            break
        assert sections[name], f"系辞{part} {name} 为空"
        units.append((n, sections[name]))
    leftover = set(sections) - {f"第{c}章" for c in _CH_ORDER[:len(units)]}
    if leftover:
        warnings.append(f"系辞{part} 页面有未取节: {sorted(leftover)}")
    return units


def parse_xugua(text):
    """序卦页面 → {"shang": text, "xia": text}。"""
    sections = parse_plain_sections(text)
    assert "上篇" in sections and "下篇" in sections, \
        f"序卦应分上下篇，实得: {sorted(sections)}"
    return {"shang": sections["上篇"], "xia": sections["下篇"]}


def parse_zagua(text, warnings):
    """杂卦页面 → 正文。只取「一篇」；「校詁版」为整理者参校本，不取。"""
    sections = parse_plain_sections(text)
    assert "一篇" in sections, f"杂卦「一篇」未找到: {sorted(sections)}"
    skipped = sorted(set(sections) - {"一篇"})
    if skipped != ["校诂版"]:
        warnings.append(f"杂卦页面节名有变: {sorted(sections)}")
    return sections["一篇"]


# ── 文言 ────────────────────────────────

#: 归段锚点（手工整理；长键优先匹配）。文本逐字出自页面，锚点只定归属。
WENYAN_ANCHORS = {
    1: [
        ("extra", ("乾元用九",)),
        ("guaci", ("《文言》曰", "文言曰", "元者善之长", "乾元者")),
        ("yao:1", ("初九曰", "潜龙勿用", "潜之为言", "君子以成德为行")),
        ("yao:2", ("九二曰", "见龙在田", "君子学以聚之")),
        ("yao:3", ("九三曰", "九三重刚", "终日乾乾")),
        ("yao:4", ("九四曰", "九四重刚", "或跃在渊")),
        ("yao:5", ("九五曰", "飞龙在天", "夫大人者")),
        ("yao:6", ("上九曰", "亢龙有悔", "亢之为言")),
    ],
    2: [
        ("guaci", ("《文言》曰", "文言曰", "坤至柔")),
        ("yao:1", ("积善之家", "履霜坚冰")),
        ("yao:2", ("直其正也", "直方大")),
        ("yao:3", ("阴虽有美", "含章可贞")),
        ("yao:4", ("天地变化", "括囊无咎")),
        ("yao:5", ("君子黄中", "黄中通理")),
        ("yao:6", ("阴疑于阳", "为其嫌于无阳", "犹未离其类", "夫玄黄者")),
    ],
}


def _find_anchors(nseg, anchors):
    """段内所有锚点命中 → [(pos, part)]，同位取长键，升序去重。"""
    hits = {}
    for part, keys in anchors:
        for key in keys:
            k = normalize(key)
            start = 0
            while True:
                p = nseg.find(k, start)
                if p < 0:
                    break
                if p not in hits or len(k) > hits[p][1]:
                    hits[p] = (part, len(k))
                start = p + 1
    return sorted((p, part) for p, (part, _l) in hits.items())


_OPEN_PUNCT = "「『《（"


def _cut(seg, idx, p):
    """切点：锚点首字的原文位置，向前回收左引号等开符号。"""
    oi = idx[p] if p < len(idx) else len(seg)
    while oi > 0 and seg[oi - 1] in _OPEN_PUNCT:
        oi -= 1
    return oi


def parse_wenyan(hid, text, warnings):
    """乾/坤页面 → {part: text}。《文言》曰以下逐段锚定归属。"""
    marker = "《文言》曰"
    # 乾页：文言在 {{+|《文言》曰…}} 模板；坤页：裸行「《文言》曰：…」
    pos = text.find("{{+|" + marker)
    if pos < 0:
        pos = text.find("\n" + marker)
        assert pos >= 0, f"卦 {hid} 页面未找到《文言》曰"
    segs = scripture_lines(text[pos:])
    sections, current = {}, None
    for seg in segs:
        nseg, idx = norm_map(seg)
        hits = _find_anchors(nseg, WENYAN_ANCHORS[hid])
        # 段首无锚点的前缀归 current
        if not hits or hits[0][0] > 0:
            head = seg[:_cut(seg, idx, hits[0][0])] if hits else seg
            if current is None:
                warnings.append(f"文言卦{hid} 无锚点弃段: {head[:24]}")
            else:
                sections[current] = sections.get(current, "") + head
        for k, (p, part) in enumerate(hits):
            end = hits[k + 1][0] if k + 1 < len(hits) else len(nseg)
            piece = seg[_cut(seg, idx, p):
                        _cut(seg, idx, end) if end < len(nseg) else len(seg)]
            if part == current:
                sections[part] = sections.get(part, "") + piece
            else:
                sections[part] = sections.get(part, "") + \
                    ("\n" if part in sections else "") + piece
            current = part
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", help="页面缓存目录（重跑免重新抓取）")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "yijing_agent/data/yizhuan.json"))
    args = ap.parse_args()

    kb = KnowledgeBase(yizhuan_path=None)
    warnings, pages_meta = [], {}

    sg_texts = []
    for i in range(1, 12):
        title = f"周易正義/09.{i:02d}"
        oldid, text = fetch_page(title, args.cache_dir)
        pages_meta[title] = oldid
        sg_texts.append(text)
        time.sleep(0.5)
    shuogua = parse_shuogua(sg_texts, warnings)

    wenyan = {}
    for hid, title in ((1, "周易正義/01乾"), (2, "周易正義/01坤")):
        oldid, text = fetch_page(title, args.cache_dir)
        pages_meta[title] = oldid
        for part, body in parse_wenyan(hid, text, warnings).items():
            body = body.strip()
            if body:
                wenyan[f"{hid}:{part}"] = body
        time.sleep(0.5)

    # 系辞上下、序卦、杂卦（白文《易傳》页面）
    xici = []
    for part, title in XICI_PAGES.items():
        oldid, text = fetch_page(title, args.cache_dir)
        pages_meta[title] = oldid
        for n, body in parse_xici(part, text, warnings):
            xici.append({"id": f"{part}:{n}", "text": body})
        time.sleep(0.5)
    n_shang = sum(1 for u in xici if u["id"].startswith("shang:"))
    assert n_shang == 12, f"系辞上应十二章，实得 {n_shang}"
    assert len(xici) - n_shang == 9, f"系辞下应九章，实得 {len(xici) - n_shang}"
    stream = "".join(u["text"] for u in xici)
    for phrase in ("大衍之数五十", "易有太极", "河出图，洛出书",
                   "古者包牺氏之王天下也", "书不尽言，言不尽意"):
        assert phrase in stream, f"系辞完整性校验未见: {phrase}"

    oldid, text = fetch_page(XUGUA_PAGE, args.cache_dir)
    pages_meta[XUGUA_PAGE] = oldid
    xugua = parse_xugua(text)
    assert xugua["shang"].startswith("有天地，然后万物生焉")
    assert "故受之以未济" in xugua["xia"].replace("《", "").replace("》", "")
    time.sleep(0.5)

    oldid, text = fetch_page(ZAGUA_PAGE, args.cache_dir)
    pages_meta[ZAGUA_PAGE] = oldid
    zagua = parse_zagua(text, warnings)
    assert zagua.startswith("乾刚坤柔") and "小人道" in zagua

    # 完整性：文言单元须挂真实经文；乾八单元、坤七单元
    for key in wenyan:
        hid, part = key.split(":", 1)
        assert kb.has(f"zhouyi:{hid}:{part}"), f"文言挂在未知经文: {key}"
    for part in ["guaci", "extra"] + [f"yao:{p}" for p in range(1, 7)]:
        assert f"1:{part}" in wenyan, f"乾文言缺 {part}"
    for part in ["guaci"] + [f"yao:{p}" for p in range(1, 7)]:
        assert f"2:{part}" in wenyan, f"坤文言缺 {part}"

    out = {
        "meta": {
            "work": "易传补编：《说卦传》＋《系辞上下传》＋《序卦传》"
                    "＋《杂卦传》＋乾坤《文言》",
            "source": "说卦、文言取维基文库《周易正義》相应页面之传文部分"
                      "（不含韩康伯注、孔颖达疏）；系辞上下、序卦、杂卦取"
                      "白文《易傳》页面（正义卷七八十十一之韩注有与传文"
                      "裸行混排者，机器无法可靠剥离，故不取）",
            "base_url": "https://zh.wikisource.org/wiki/",
            "pages": pages_meta,
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "conversion": "繁→简 OpenCC t2s",
            "chapters": "说卦章次依朱熹《周易本义》十一章之分；"
                        "类象诸章（八、九、十、十一）按八卦再分；"
                        "系辞章次依《易傳》页面所分：上十二章（「天一地二」"
                        "节居「大衍」前，同朱子《本义》改序后之次），"
                        "下九章（与《本义》分下篇十二章不同）",
            "wenyan_anchors": "文言按所释经文单元锚定归段，锚点表手工整理"
                              "（见 tools/import_wikisource_yizhuan.py），"
                              "文本逐字出自页面",
            "variants": "杂卦页面另有「校詁版」一节不取；其与所取「一篇」"
                        "之显异文：蒙杂而著/蒙稚而著、随无故也/随无事也、"
                        "亲寡旅也/旅寡亲也、小人道消也/小人道忧也"
                        "（通行注疏本作「小人道忧也」）",
            "imported": "2026-08-25",
            "proofread": False,
            "warnings": warnings,
        },
        "shuogua": [dict({"id": uid, "text": txt},
                         **({"gua": gua} if gua else {}))
                    for uid, gua, txt in shuogua],
        "wenyan": wenyan,
        "xici": xici,
        "xugua": [{"id": "shang", "text": xugua["shang"]},
                  {"id": "xia", "text": xugua["xia"]}],
        "zagua": [{"id": "1", "text": zagua}],
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"说卦 {len(shuogua)} 单元；文言 {len(wenyan)} 单元；"
          f"系辞 {len(xici)} 章；序卦 2 篇；杂卦 1 篇 → {args.out}")
    print(f"警告 {len(warnings)} 条")
    for w in warnings:
        print("  -", w)


if __name__ == "__main__":
    main()
