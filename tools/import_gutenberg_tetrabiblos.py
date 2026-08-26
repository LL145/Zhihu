"""从 Project Gutenberg 导入托勒密《占星四书》（Tetrabiblos）英译本。

西洋占星语料第一期（藏书＋语境层；见 DESIGN.md v3.9 与 ALGORITHM.md）：

- 底本：PG #70850《Ptolemy's Tetrabiblos; or, Quadripartite》，
  J. M. Ashmand 英译（1822 初版之 1900 Foulsham 重印本，PGDP 精校
  电子文）。Ashmand 译自题为普罗克鲁斯（Proclus）之希腊文释本
  （paraphrase），非托勒密原文直译——公版英译中唯此本有精校电子文；
  Robbins 1940 直译本（Loeb）未入公版，希腊原文无可靠电子文本，
  均缓收（引文约定与缓收缘由见 data/PROOFREADING.md）。
- 单元：四卷 70 章逐章一条（tetra:{卷}:{章}，卷 1–4、章依原书罗马
  数字转阿拉伯数字；卷一 27、卷二 14、卷三 19、卷四 10，逐项断言）。
- 取舍：只取托勒密本文之英译。译者序（Ashmand 自撰）、译者脚注
  （集中于文末 footnotes 容器，正文只剥其锚标 [n]）、附录（《至大论》
  节录与伪托之《百言》）一律不取；正文内表格（界埃及分度表等 3 处）
  机器不入引文文本，逐处记 warnings；插图与页码标记剥离。

用法：
    python tools/import_gutenberg_tetrabiblos.py [--cache-dir .cache_tetra]

许可：原文（约公元 2 世纪）与英译（1822，译者 Ashmand 卒于 19 世纪）
均为公版；Project Gutenberg 电子文按其许可可自由再用（PG 商标条款
仅约束冠名，本库不冠 PG 名）。meta 记 sha256 以为底本存证。
"""

import argparse
import datetime as _dt
import hashlib
import html as _html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
URL = "https://www.gutenberg.org/cache/epub/70850/pg70850-images.html"
UA = "TianwenAgent/0.1 (typiary import; github LL145/Zhihu)"
CA = "/root/.ccr/ca-bundle.crt"
LICENSE = ("公版（原文约公元 2 世纪；Ashmand 英译 1822；"
           "Project Gutenberg #70850 电子文，依 PG 许可自由再用）")

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}

_BOOK_NUM = {"BOOK THE FIRST": 1, "BOOK THE SECOND": 2,
             "BOOK THE THIRD": 3, "BOOK THE FOURTH": 4}

#: 各卷章数（Ashmand 本卷章结构；逐项断言，底本页面变动即失败）
_CHAPTERS = {1: 27, 2: 14, 3: 19, 4: 10}


def fetch(cache_dir):
    f = Path(cache_dir) / "pg70850.html"
    if not f.exists():
        for i in range(6):
            r = subprocess.run(
                ["curl", "-sSL", "--cacert", CA, "-H", f"User-Agent: {UA}",
                 URL], capture_output=True, text=True, timeout=180)
            if r.returncode == 0 and "PTOLEMY" in r.stdout:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                f.write_text(r.stdout, encoding="utf-8")
                break
            time.sleep(5 * (i + 1))
        else:
            raise RuntimeError("抓取失败：" + URL)
    raw = f.read_text("utf-8")
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _strip_tags(fragment):
    """HTML 片段 → 纯文本：剥脚注锚 [n]、页码标记、其余标签；实体解码。"""
    s = re.sub(r'<a class="fnanchor[^"]*"[^>]*>.*?</a>', "", fragment,
               flags=re.S)
    s = re.sub(r'<span class="pagenum"[^>]*>.*?</span>', "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _roman(s):
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN[ch]
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total


def parse(raw):
    """→ (units, warnings)。units: [{id, title, text}]，卷章序。"""
    # 只取四卷本文：自「BOOK THE FIRST」标题起，至附录标题止
    # （目录以表格排版无此标题文本，两锚点全文各唯一）
    start = raw.index(">BOOK THE FIRST<")
    end = raw.index('id="APPENDIX">APPENDIX</h2>')
    body = raw[raw.rindex("<h2", 0, start):raw.rindex("<h2", 0, end)]

    units, warnings = [], []
    book = None
    # 卷题 h2 与章题 h3 依序扫描；章题至下一标题之间为章文
    heads = list(re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", body, re.S))
    for i, m in enumerate(heads):
        head = _strip_tags(m.group(2))
        seg = body[m.end():heads[i + 1].start() if i + 1 < len(heads)
                   else len(body)]
        bm = re.fullmatch(r"BOOK THE \w+", head)
        if bm:
            book = _BOOK_NUM[head]
            continue
        cm = re.match(r"CHAPTER ([IVXL]+)\s*(.*)", head)
        assert cm and book, f"章头异常：{head!r}"
        chap = _roman(cm.group(1))
        title = re.sub(r"\[\d+\]", "", cm.group(2)).strip()
        assert title, f"章无标题：卷{book}章{chap}"

        for _t in re.findall(r"<table.*?</table>", seg, re.S):
            warnings.append(f"{book}:{chap}（{title}）：正文内表格不入"
                            "引文文本（版式图表，机器不可靠转文）")
        seg = re.sub(r"<table.*?</table>", "", seg, flags=re.S)
        seg = re.sub(r'<div class="figcenter".*?</div>', "", seg, flags=re.S)
        paras = [_strip_tags(p)
                 for p in re.findall(r"<p\b[^>]*>(.*?)</p>", seg, re.S)]
        text = "\n".join(p for p in paras if p)
        assert text, f"卷{book}章{chap}（{title}）空文本"
        units.append({"id": f"{book}:{chap}", "title": title, "text": text})

    counts = {}
    for u in units:
        counts[int(u["id"].split(":")[0])] = counts.get(
            int(u["id"].split(":")[0]), 0) + 1
    assert counts == _CHAPTERS, f"卷章数不符：{counts} ≠ {_CHAPTERS}"
    seen = set()
    for u in units:
        assert u["id"] not in seen, f"单元重出：{u['id']}"
        seen.add(u["id"])
        for ch in "<>{}":
            assert ch not in u["text"], f"{u['id']} 有残留标记 {ch}"
        assert not re.search(r"\[\d+\]", u["text"]), f"{u['id']} 残留脚注号"
    return units, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(ROOT / ".cache_tetra"))
    ap.add_argument("--out", default=str(ROOT / "tianwen" / "data"
                                         / "tetrabiblos.json"))
    args = ap.parse_args()

    raw, sha = fetch(args.cache_dir)
    units, warnings = parse(raw)
    data = {
        "meta": {
            "work": "占星四书（Tetrabiblos，托勒密撰；J. M. Ashmand 英译，"
                    "1822/1900 Foulsham 重印本）",
            "short": "占星四书",
            "language": "en",
            "source": "Project Gutenberg #70850（PGDP 精校电子文；Ashmand "
                      "译自题为普罗克鲁斯之希腊文释本，非原文直译）",
            "base_url": URL,
            "sha256": sha,
            "license": LICENSE,
            "conversion": "只取四卷本文之英译，逐章一单元（tetra:{卷}:{章}，"
                          "罗马数字转阿拉伯）；译者序、译者脚注（正文剥锚标）、"
                          "附录（《至大论》节录、伪托《百言》）不取；正文内"
                          "表格不入引文文本（逐处记 warnings）；插图、页码"
                          "标记剥离，章题内脚注号剥离；引文一律用英译原文，"
                          "中译只可作解释性转述（引文约定，DESIGN.md）",
            "imported": _dt.date.today().isoformat(),
            "proofread": False,
            "warnings": warnings,
        },
        "units": units,
    }
    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{data['meta']['work']}：{len(units)} 单元，"
          f"警告 {len(warnings)} 条 → {out}")


if __name__ == "__main__":
    sys.exit(main())
