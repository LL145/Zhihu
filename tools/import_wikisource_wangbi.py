"""从中文维基文库《周易正義》导入王弼《周易注》（注疏层第一期）。

来源：zh.wikisource.org 的 周易正義/* 各卦子页面（CC BY-SA 4.0；
经注原文为公版，页面标点为维基文库贡献者所加，依 CC BY-SA 使用并署名）。

各卦页面转写体例不一（乾卦式：{{+|经文}}{{*|注}}{{批|疏}}；
革卦式：行首经文 {{*|注}} [疏]疏），因此不依赖格式判经注，而是：
  - {{*|...}} 一律视为王弼注；
  - {{批|...}} 与 [疏]/【疏】 起首的行一律为孔疏，丢弃；
  - 其余文字段为经文候选，繁→简后与 hexagrams.json 的经文逐段锚定
    （精确 / 家族内连续拼接 / 子串 / 模糊 ≥0.80 四级匹配），
    注文归属其前方最近命中的经文单元；
  - 乾、坤页面遇《文言》即停（文言不在知识库，第一期不收）。

用法：
    python tools/import_wikisource_wangbi.py [--cache-dir DIR] [--out FILE]

未匹配片段与模糊匹配全部记入 meta.warnings 供人工校对。
"""

import argparse
import difflib
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
from yijing_agent.validator import normalize  # noqa: E402

API = "https://zh.wikisource.org/w/api.php"
UA = "ZhihuYijingAgent/0.1 (yijing_agent data import; one-off)"
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"

_cc = OpenCC("t2s")


def t2s(s):
    """繁→简，但保护易学专名：乾不转干（本语料中乾均指乾卦/乾乾）；
    遯统一作遁（OpenCC 不转此字，知识库用遁）。"""
    s = s.replace("乾", "")
    s = _cc.convert(s)
    return s.replace("", "乾").replace("遯", "遁")


# 页面卦名（繁体）→ 知识库卦名：OpenCC 单字直转不可靠的三例
_NAME_FIX = {"乾": "乾", "坎": "习坎", "遯": "遁"}

_YAO_NAMES = ("初九|九二|九三|九四|九五|上九|"
              "初六|六二|六三|六四|六五|上六|用九|用六")
_TRIGRAM_CH = "乾坤震巽坎离兑艮"


def api(params, tries=6):
    url = API + "?" + urllib.parse.urlencode(dict(params, format="json"))
    cmd = ["curl", "-s", "--max-time", "60", "-A", UA, url]
    if Path(CA_BUNDLE).exists():
        cmd[1:1] = ["--cacert", CA_BUNDLE]
    for i in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            time.sleep(2 * (i + 1))
    raise RuntimeError("Wikisource API 连续失败: " + url)


def fetch_page(title, cache_dir=None):
    """返回 (oldid, wikitext)，可选本地缓存。"""
    if cache_dir:
        f = Path(cache_dir) / (title.replace("/", "__") + ".json")
        if f.exists():
            d = json.loads(f.read_text("utf-8"))
            return d["oldid"], d["text"]
    d = api({"action": "query", "titles": title, "prop": "revisions",
             "rvprop": "ids|content", "rvslots": "main"})
    page = list(d["query"]["pages"].values())[0]
    rev = page["revisions"][0]
    oldid, text = rev["revid"], rev["slots"]["main"]["*"]
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"oldid": oldid, "text": text},
                                ensure_ascii=False), "utf-8")
    return oldid, text


def list_hexagram_pages(cache_dir=None):
    """周易正義/ 下的卦名子页面（排除 07.x 起的系辞等）。"""
    cache = Path(cache_dir) / "_titles.json" if cache_dir else None
    if cache and cache.exists():
        return json.loads(cache.read_text("utf-8"))
    pages, cont = [], {}
    while True:
        d = api(dict({"action": "query", "list": "allpages",
                      "apprefix": "周易正義/", "aplimit": "200"}, **cont))
        pages += [p["title"] for p in d["query"]["allpages"]]
        if "continue" not in d:
            titles = [t for t in pages
                      if re.fullmatch(r"周易正義/0[1-6][^\d.].*", t)]
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(titles, ensure_ascii=False), "utf-8")
            return titles
        cont = {"apcontinue": d["continue"]["apcontinue"]}


def clean_wiki(s):
    """去链接 / 语言转换标记 / 残余模板 / 注释。"""
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
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)  # 残余未知模板
    return s.strip()


def merge_template_lines(lines):
    """把跨行未闭合的 {{...}} 模板并回一行（如萃卦九四注跨行）。"""
    out, buf = [], ""
    for line in lines:
        buf = (buf + line.strip()) if buf else line.strip()
        if buf.count("{{") > buf.count("}}"):
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def segments_of(text):
    """把页面拆成 (kind, 简体文本) 段序列，并统计疏标记行数。

    kind: 'text' 经文候选 / 'note' 王弼注（{{*|...}}）。
    """
    lines = text.splitlines()
    i = 0
    if lines and lines[0].startswith("{{header"):
        while i < len(lines) and lines[i].strip() != "}}":
            i += 1
        i += 1
    segs, shu_lines = [], 0
    for line in merge_template_lines(lines[i:]):
        s = line.strip().lstrip(":").strip()
        if not s or s.startswith(("==", "[[", "{{footer", "----", "__")):
            continue
        if "{{批|" in s or s.startswith(("[疏]", "【疏】")):
            shu_lines += 1
            continue
        for part in re.split(r"(\{\{[*+]\|.*?\}\})", s):
            part = part.strip()
            if not part:
                continue
            m = re.fullmatch(r"\{\{([*+])\|(.*?)\}\}", part)
            kind = "note" if (m and m.group(1) == "*") else "text"
            body = clean_wiki(m.group(2) if m else part)
            body = t2s(body)
            if body:
                segs.append((kind, body))
    return segs, shu_lines


def build_units(kb, hid):
    """按通行本顺序列出该卦全部经文单元；family 供拼接匹配用。"""
    h = kb.hexagram(hid)
    units = []

    def add(cid, family, text):
        units.append({"cid": cid, "family": family, "ntext": normalize(text)})

    add(f"zhouyi:{hid}:guaci", "guaci", h["guaci"])
    add(f"tuan:{hid}", "tuan", h["tuan"])
    add(f"daxiang:{hid}", "daxiang", h["daxiang"])
    for y in h["yao"]:
        add(f"zhouyi:{hid}:yao:{y['pos']}", "yao", y["text"])
    if h["extra"]:
        add(f"zhouyi:{hid}:extra", "yao", h["extra"]["text"])
    for y in h["yao"]:
        add(f"xiaoxiang:{hid}:{y['pos']}", "xiaoxiang", y["xiaoxiang"])
    if h["extra"]:
        add(f"xiaoxiang:{hid}:extra", "xiaoxiang", h["extra"]["xiaoxiang"])
    return units


def norm_map(s):
    """(纯汉字串, 索引表)：normalized[i] 对应 s[idx[i]]。"""
    chars, idx = [], []
    for i, ch in enumerate(s):
        if "\u3400" <= ch <= "\u9fff":
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


def variants(body, gua_name):
    """梯度剥前缀，返回 (候选序列, 剥净后的纯汉字串)。

    候选顺序：剥到爻名（标准）→ 再剥卦名（卦辞行）→ 保留爻名（用九/用六
    小象等单元文本自带爻名）→ 原文。剥净为空说明是纯页眉（卦画、「大过：」）。
    """
    sa = re.sub(rf"^[{_TRIGRAM_CH}]{{1,2}}下[{_TRIGRAM_CH}]{{1,2}}上[。，]?", "", body)
    sa = re.sub(r"^《?(彖|象)》?曰[：:，,]?", "", sa).strip()
    sb = re.sub(rf"^({_YAO_NAMES})曰?[：:，,]?", "", sa).strip()
    sc = re.sub(rf"^{re.escape(gua_name)}[：:，,]?", "", sb).strip()
    out = []
    for s in (sb, sc, sa, body):
        if s and s not in out:
            out.append(s)
    return out, normalize(sc)


def _eq_loose(a, b):
    """等长近似相等：单字异文（巳/已/己等）不破坏匹配。"""
    if len(a) != len(b) or len(a) < 4:
        return a == b
    diff = sum(1 for x, y in zip(a, b) if x != y)
    return diff <= (1 if len(a) < 8 else 2)


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


class PageMatcher:
    """经文锚定状态机：单元剩余文本前缀消耗 + 精确/拼接/融合/模糊多级匹配。"""

    def __init__(self, units):
        self.units = units
        self.matched = set()
        self.current = None
        self.offset = 0
        self.notes = {}
        self.log = []

    def _remainder(self):
        if self.current is None:
            return ""
        return self.current["ntext"][self.offset:]

    def _anchor(self, unit, offset, how, body):
        self.matched.add(unit["cid"])
        self.current, self.offset = unit, offset
        if how not in ("exact", "prefix", "cont"):
            self.log.append(f"{unit['cid']} {how}: {body[:30]}")

    def add_note(self, text):
        if self.current is None:
            return False
        cid = self.current["cid"]
        self.notes[cid] = self.notes.get(cid, "") + text
        return True

    def _open(self):
        return [u for u in self.units if u["cid"] not in self.matched]

    def feed(self, body, gua_name):
        """尝试把一个经文候选段对齐到某单元。返回是否成功。"""
        cands, stripped_all = variants(body, gua_name)
        if not stripped_all:
            return True  # 纯页眉（卦画、「大过：」之类），静默丢弃
        vs = []
        for s in cands:
            n, idx = norm_map(s)
            if len(n) >= 1:
                vs.append((s, n, idx))
        if not vs:
            return True
        # 第一轮：高精度规则。规则为外层、变体为内层——精确匹配须先于
        # 前缀匹配尝试所有变体（否则「泰：小往大来」会先撞上彖传引文）。
        for s, n, idx in vs:  # 续段（当前单元剩余文本的前缀，容单字异文）
            rem = self._remainder()
            if rem and len(n) <= len(rem) and _eq_loose(n, rem[:len(n)]):
                self._anchor(self.current, self.offset + len(n), "cont", body)
                return True
            if rem and n.startswith(rem) and len(n) - len(rem) >= 2:
                # 续段收尾 + 融合裸注
                cut = idx[len(rem)] if len(rem) < len(idx) else len(s)
                self._anchor(self.current, len(self.current["ntext"]),
                             "fused-tail", body)
                self.add_note(s[cut:].lstrip("。，、：；」』）"))
                return True
        for s, n, idx in vs:  # 整单元（近似）相等
            for u in self._open():
                if _eq_loose(u["ntext"], n):
                    self._anchor(u, len(n), "exact" if u["ntext"] == n
                                 else "loose-eq", body)
                    return True
        for s, n, idx in vs:  # 家族内连续拼接（乾卦小象多条并一行）
            run = self._concat_run(n)
            if run:
                for u in run:
                    self.matched.add(u["cid"])
                self._anchor(run[-1], len(run[-1]["ntext"]), "concat", body)
                return True
        for s, n, idx in vs:  # 单元开头（近似）前缀
            hits = [u for u in self._open()
                    if len(u["ntext"]) >= len(n)
                    and _eq_loose(n, u["ntext"][:len(n)])]
            if len(hits) == 1:
                self._anchor(hits[0], len(n), "prefix", body)
                return True
        for s, n, idx in vs:  # 整单元 + 尾随裸注（经注融合行）
            fused = [u for u in self._open()
                     if n.startswith(u["ntext"]) and len(n) - len(u["ntext"]) >= 2]
            if len(fused) == 1:
                u = fused[0]
                cut = idx[len(u["ntext"])]
                self._anchor(u, len(u["ntext"]), "fused", body)
                self.add_note(s[cut:].lstrip("。，、：；」』）"))
                return True
        # 第二轮：模糊与子串
        for s, n, idx in vs:
            rem = self._remainder()
            if rem and len(n) >= 4 and _ratio(n, rem[:len(n) + 2]) >= 0.78:
                self._anchor(self.current, self.offset + len(n),
                             "cont-fuzzy", body)
                return True
            if len(n) >= 5:
                pool = self._open() + ([self.current] if self.current else [])
                hits = [u for u in pool if n in u["ntext"]]
                if len(hits) == 1:
                    u = hits[0]
                    self._anchor(u, u["ntext"].index(n) + len(n), "substr", body)
                    return True
            scored = sorted(((_ratio(n, u["ntext"]), u) for u in self._open()),
                            key=lambda x: -x[0])
            if scored and scored[0][0] >= 0.80:
                u = scored[0][1]
                self._anchor(u, len(u["ntext"]), f"fuzzy:{scored[0][0]:.2f}", body)
                return True
            if len(n) >= 4:
                pref = sorted(((_ratio(n, u["ntext"][:len(n) + 2]), u)
                               for u in self._open()), key=lambda x: -x[0])
                if pref and pref[0][0] >= 0.80:
                    self._anchor(pref[0][1], len(n),
                                 f"fuzzy-prefix:{pref[0][0]:.2f}", body)
                    return True
        return False

    def _concat_run(self, n):
        """家族内连续拼接（乾卦小象多条并一行），逐段容单字异文。"""
        for fam in ("yao", "xiaoxiang", "tuan"):
            fam_units = [u for u in self.units if u["family"] == fam]
            for a in range(len(fam_units)):
                pos, run = 0, []
                for u in fam_units[a:]:
                    length = len(u["ntext"])
                    if pos + length > len(n):
                        break
                    if not _eq_loose(n[pos:pos + length], u["ntext"]):
                        break
                    run.append(u)
                    pos += length
                    if pos == len(n):
                        break
                if len(run) > 1 and pos == len(n):
                    return run
        return None


def parse_page(kb, hid, gua_name, text):
    """返回 (notes {经文cite_id: 注文}, report)。"""
    units = build_units(kb, hid)
    segs, shu_lines = segments_of(text)
    m = PageMatcher(units)
    skipped, rescued = [], []

    for kind, body in segs:
        if kind == "text" and re.match(r"^《?文言》?曰", body):
            break  # 乾坤：文言不在知识库，第一期不收
        if re.match(r"^音[\u3400-\u9fff]{1,12}[。]?$", body):
            continue  # 陆氏音义类小注，不收
        if kind == "note" and m.current is not None:
            # 个别页面把小象误包进注模板（如比六三）：拆出可锚定的《象》曰段
            head, sep, tail = body.partition("《象》曰")
            prev_cid = m.current["cid"]
            if sep and m.feed(sep + tail, gua_name):
                if head.strip():  # 注文头部仍归拆分前的单元
                    m.notes[prev_cid] = m.notes.get(prev_cid, "") + head
                rescued.append(f"注内拆出小象 ← {(sep + tail)[:30]}")
            else:
                m.add_note(body)
            continue
        # 经文候选（以及 current 未定时的 note 段——个别页面首行经注模板写反）
        if m.feed(body, gua_name):
            continue
        if kind == "note" and m.current is None:
            # 卦辞之前的注（释卦名，如习坎「险陷之名也」）归卦辞
            m.notes[units[0]["cid"]] = m.notes.get(units[0]["cid"], "") + body
            rescued.append(f"{units[0]['cid']}(卦名注) ← {body[:30]}")
        elif (kind == "text" and shu_lines > 0 and m.current is not None
                and len(body) <= 200):
            # 裸注救回：页面有疏标记（疏必被剔）的短段，视为未加模板的注
            m.add_note(body)
            rescued.append(f"{m.current['cid']} ← {body[:30]}")
        else:
            skipped.append(body[:40])

    report = {
        "units_total": len(units),
        "units_matched": len(m.matched),
        "notes": len(m.notes),
        "skipped": skipped,
        "fuzzy": m.log,
        "rescued": rescued,
        "missing_units": [u["cid"] for u in units if u["cid"] not in m.matched],
    }
    return m.notes, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", help="页面缓存目录（重跑免重新抓取）")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "yijing_agent/data/wangbi.json"))
    args = ap.parse_args()

    kb = KnowledgeBase()
    name_to_id = {h["name"]: i for i, h in kb.by_id.items()}

    titles = list_hexagram_pages(args.cache_dir)
    print(f"候选页面 {len(titles)} 个")

    # 卦名（繁→简）→ 页面；同名取解析质量高者（隨卦存在重复页）
    all_notes, pages_meta, warnings = {}, {}, []
    best = {}  # hid -> (score, title, oldid, notes, report)
    for title in titles:
        raw = title.split("/")[-1][2:]
        simp = _NAME_FIX.get(raw, t2s(raw))
        if simp not in name_to_id:
            warnings.append(f"页面卦名未识别，跳过: {title}")
            continue
        hid = name_to_id[simp]
        oldid, text = fetch_page(title, args.cache_dir)
        notes, rep = parse_page(kb, hid, simp, text)
        score = (rep["units_matched"], rep["notes"], -len(rep["skipped"]))
        print(f"{title}: 单元 {rep['units_matched']}/{rep['units_total']}, "
              f"注 {rep['notes']}, 跳过 {len(rep['skipped'])}, "
              f"模糊 {len(rep['fuzzy'])}")
        if hid not in best or score > best[hid][0]:
            best[hid] = (score, title, oldid, notes, rep)
        time.sleep(0.5)

    missing = [i for i in range(1, 65) if i not in best]
    assert not missing, f"缺卦页面: {missing}"

    for hid in sorted(best):
        _, title, oldid, notes, rep = best[hid]
        all_notes.update(notes)
        pages_meta[title] = oldid
        for s in rep["skipped"]:
            warnings.append(f"{title} 未匹配片段: {s}")
        for s in rep["fuzzy"]:
            warnings.append(f"{title} 非精确对齐: {s}")
        for s in rep["rescued"]:
            warnings.append(f"{title} 裸注归属: {s}")
        if rep["units_matched"] < rep["units_total"]:
            warnings.append(f"{title} 经文单元未全对齐: "
                            f"{rep['units_matched']}/{rep['units_total']}，"
                            f"缺 {','.join(rep['missing_units'])}")

    for cid in all_notes:
        assert kb.has(cid), f"注文挂在未知 cite_id: {cid}"

    out = {
        "meta": {
            "work": "王弼《周易注》",
            "source": "维基文库《周易正義》各卦页面之经注部分（不含孔颖达疏、文言）",
            "base_url": "https://zh.wikisource.org/wiki/周易正義",
            "pages": pages_meta,
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "conversion": "繁→简 OpenCC t2s",
            "imported": "2026-08-24",
            "proofread": False,
            "warnings": warnings,
        },
        "notes": all_notes,
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"\n共 {len(all_notes)} 条王弼注 → {args.out}")
    print(f"警告 {len(warnings)} 条（详见 meta.warnings）")


if __name__ == "__main__":
    main()
