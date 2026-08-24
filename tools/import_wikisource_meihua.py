"""从中文维基文库《梅花易數》卷二导入梅花占诀：体用总诀 + 十八占。

来源：zh.wikisource.org《梅花易數/卷二》（CC BY-SA 4.0；《梅花易数》
旧题邵雍撰、实为明人辑纂之公版古籍，页面标点为维基文库贡献者所加）。

页面为标准 MediaWiki 节结构（=== 體用總訣 ===、=== 天時占第一 === …），
按节名提取正文。占章键（pinyin）与中文名对照表见 SECTIONS；
selection.TOPIC_ZHAN 只映射与问事类别对应可靠的占章，疾病占、官讼占
等红线类别永不选取（红线拦截在前），导入仅为语料完整。

用法：
    python tools/import_wikisource_meihua.py [--cache-dir DIR] [--out FILE]
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

API = "https://zh.wikisource.org/w/api.php"
UA = "ZhihuYijingAgent/0.1 (yijing_agent data import; one-off)"
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
TITLE = "梅花易數/卷二"

_cc = OpenCC("t2s")


def t2s(s):
    """繁→简，保护乾字不被转作干（占位符走私用区字符）。"""
    s = s.replace("乾", "")
    s = _cc.convert(s)
    return s.replace("", "乾").replace("遯", "遁")


#: (页面节名简体, 单元id, 展示名)。十八占次序即《梅花易数》卷二原序。
SECTIONS = [
    ("体用总诀", "2:tiyong", "体用总诀"),
    ("天时占第一", "2:zhan:tianshi", "天时占"),
    ("人事占第二", "2:zhan:renshi", "人事占"),
    ("家宅占第三", "2:zhan:jiazhai", "家宅占"),
    ("屋舍占第四", "2:zhan:wushe", "屋舍占"),
    ("婚姻占第五", "2:zhan:hunyin", "婚姻占"),
    ("生产占第六", "2:zhan:shengchan", "生产占"),
    ("饮食占第七", "2:zhan:yinshi", "饮食占"),
    ("求谋占第八", "2:zhan:qiumou", "求谋占"),
    ("求名占第九", "2:zhan:qiuming", "求名占"),
    ("求财占第十", "2:zhan:qiucai", "求财占"),
    ("交易占第十一", "2:zhan:jiaoyi", "交易占"),
    ("出行占第十二", "2:zhan:chuxing", "出行占"),
    ("行人占第十三", "2:zhan:xingren", "行人占"),
    ("谒见占第十四", "2:zhan:yejian", "谒见占"),
    ("失物占第十五", "2:zhan:shiwu", "失物占"),
    ("疾病占第十六", "2:zhan:jibing", "疾病占"),
    ("官讼占第十七", "2:zhan:guansong", "官讼占"),
    ("坟墓占第十八", "2:zhan:fenmu", "坟墓占"),
]


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
    return rev["revid"], rev["slots"]["main"]["*"]


def clean_wiki(s):
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
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    return s.strip()


def parse_sections(text):
    """wikitext → {节名简体: 正文}。只认 === 三级节。"""
    sections, current, buf = {}, None, []

    def flush():
        if current is not None:
            sections[current] = "\n".join(buf).strip()

    for raw in text.splitlines():
        s = raw.strip()
        m = re.fullmatch(r"===\s*(.*?)\s*===", s)
        if m:
            flush()
            current, buf = t2s(m.group(1)), []
            continue
        if re.fullmatch(r"=+\s*[^=]*\s*=+", s):   # 一/二级节界
            flush()
            current, buf = None, []
            continue
        if not s or s.startswith(("{{header", "{{footer", "[[", "----", "__")):
            continue
        line = t2s(clean_wiki(s))
        if line:
            buf.append(line)
    flush()
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", help="页面缓存目录（重跑免重新抓取）")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "yijing_agent/data/meihua.json"))
    args = ap.parse_args()

    oldid, text = fetch_page(TITLE, args.cache_dir)
    sections = parse_sections(text)

    units, warnings = [], []
    for sec_name, uid, disp in SECTIONS:
        body = sections.get(sec_name, "")
        assert body, f"节未找到或为空: {sec_name}（现有节: {sorted(sections)}）"
        if "体" not in body or "用" not in body:
            warnings.append(f"{sec_name} 正文未见体/用字样，请人工核对")
        units.append({"id": uid, "title": disp, "text": body})

    out = {
        "meta": {
            "work": "《梅花易数》卷二：体用总诀与十八占",
            "source": "维基文库《梅花易數/卷二》体用生克篇（旧题邵雍撰，"
                      "实为明人辑纂；页面标点为维基文库贡献者所加）",
            "base_url": "https://zh.wikisource.org/wiki/梅花易數/卷二",
            "pages": {TITLE: oldid},
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "conversion": "繁→简 OpenCC t2s",
            "imported": "2026-08-24",
            "proofread": False,
            "warnings": warnings,
        },
        "units": units,
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(units)} 单元（总诀 1 + 十八占 18） → {args.out}")
    print(f"警告 {len(warnings)} 条")
    for w in warnings:
        print("  -", w)


if __name__ == "__main__":
    main()
