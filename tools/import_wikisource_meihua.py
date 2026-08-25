"""从中文维基文库《梅花易數》卷一、卷二导入梅花语料。

来源：zh.wikisource.org《梅花易數》（CC BY-SA 4.0；《梅花易数》
旧题邵雍撰、实为明人辑纂之公版古籍，页面标点为维基文库贡献者所加）。

卷一：起卦诸法（年月日时、物数、声音、字占诸章、端法后天）、
      占例（观梅占、西林寺牌额占等）与八卦类象、八卦万物属类。
      起卦引擎（casting.py）所引起卦法原文均出于此卷，导入后
      逐条可检索、可引用。「八卦万物属类」大章按八卦切为八单元。
卷二：体用总诀 + 十八占。selection.TOPIC_ZHAN 只映射与问事类别
      对应可靠的占章，疾病占、官讼占等红线类别永不选取（红线拦截
      在前），导入仅为语料完整。

页面为标准 MediaWiki 节结构（=== 體用總訣 ===、=== 觀梅占 === …），
按节名提取正文。单元 id 首段为卷次（1: / 2:）。

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
TITLES = {"1": "梅花易數/卷一", "2": "梅花易數/卷二"}

_cc = OpenCC("t2s")


def t2s(s):
    """繁→简，保护乾字不被转作干（占位符走私用区字符）。"""
    s = s.replace("乾", "")
    s = _cc.convert(s)
    return s.replace("", "乾").replace("遯", "遁")


#: 卷一：(页面节名简体, 单元id, 展示名, 完整性关键词)。
#: 关键词须见于该节正文（简体、含标点原文），否则报错——防错位串节。
SECTIONS_J1 = [
    ("周易卦数", "1:guashu", "周易卦数", "乾，一"),
    ("五行生克", "1:wuxing", "五行生克", "金生水"),
    ("八宫所属五行", "1:bagong", "八宫所属五行", "乾、兑，金"),
    ("卦气旺", "1:guaqi:wang", "卦气旺", None),
    ("卦气衰", "1:guaqi:shuai", "卦气衰", None),
    ("十天干", "1:tiangan", "十天干", "甲"),
    ("十二地支", "1:dizhi", "十二地支", "子"),
    ("八卦象例", "1:xiangli", "八卦象例", "三连"),
    ("占法", "1:zhanfa", "占法", None),
    ("玩法", "1:wanfa", "玩法", None),
    ("卦以八除", "1:guachu", "卦以八除", "八数递除"),
    ("爻以六除", "1:yaochu", "爻以六除", "余数作动爻"),
    ("互卦起例", "1:hugua", "互卦起例", "中间四爻"),
    ("年月日时起例", "1:qi:shijian", "年月日时起例", "年月日为上卦"),
    ("物数占例", "1:qi:wushu", "物数占例", "可数之物"),
    ("声音占例", "1:qi:shengyin", "声音占例", "凡闻声音"),
    ("字占", "1:qi:zi", "字占", "平分"),
    ("一字占至十一字占", "1:qi:zishu", "一字占至十一字占", "三才"),
    ("丈尺占", "1:qi:zhangchi", "丈尺占", None),
    ("尺寸占", "1:qi:chicun", "尺寸占", "尺数为上卦"),
    ("为人占", "1:qi:weiren", "为人占", "以其字占之"),
    ("自己占", "1:qi:ziji", "自己占", None),
    ("占动物", "1:qi:dongwu", "占动物", None),
    ("占静物", "1:qi:jingwu", "占静物", None),
    ("物卦起例（端法后天起卦）", "1:qi:duanfa", "物卦起例（端法后天起卦）",
     "方位为下卦"),
    ("八卦万物属类（并为上卦）", "1:qi:wanwu", "八卦万物属类（并为上卦）",
     None),
    ("八卦方位图", "1:qi:fangwei", "八卦方位图", "离南坎北"),
    ("观梅占", "1:li:guanmei", "观梅占", "二雀争枝坠地"),
    ("牡丹占", "1:li:mudan", "牡丹占", "天风姤"),
    ("邻夜扣门借物占", "1:li:koumen", "邻夜扣门借物占", "借斧"),
    ("今日动静如何", "1:li:dongjing", "今日动静如何", "地风升"),
    ("西林寺牌额占", "1:li:xilinsi", "西林寺牌额占", "山地剥"),
    ("老人有忧色占", "1:li:laoren", "老人有忧色占", "天风姤"),
    ("少年有喜色占", "1:li:shaonian", "少年有喜色占", "山火贲"),
    ("牛哀鸣占", "1:li:niu", "牛哀鸣占", "地水师"),
    ("鸡悲鸣占", "1:li:ji", "鸡悲鸣占", "风天小畜"),
    ("枯枝坠地占", "1:li:kuzhi", "枯枝坠地占", "火泽睽"),
    ("风觉鸟占", "1:hou:fengjueniao", "风觉鸟占", None),
    ("风觉占", "1:hou:fengjue", "风觉占", "见风而觉"),
    ("鸟占", "1:hou:niao", "鸟占", None),
    ("听声音占", "1:hou:tingsheng", "听声音占", None),
    ("形物占", "1:hou:xingwu", "形物占", None),
    ("验色占", "1:hou:yanse", "验色占", None),
    ("八卦类象", "1:xiang:leixiang", "八卦类象", "玄黄"),
    # 「八卦万物属类」大章另行按八卦切分，见 split_wanwu()
]

#: 卷二：(页面节名简体, 单元id, 展示名)。十八占次序即原序。
SECTIONS_J2 = [
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

#: 「八卦万物属类」逐卦拼音段（与 trigrams.PINYIN 一致）
_WANWU_PINYIN = {"乾": "qian", "坤": "kun", "震": "zhen", "巽": "xun",
                 "坎": "kan", "离": "li", "艮": "gen", "兑": "dui"}


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
            time.sleep(45 if "too many requests" in out.lower() else 10 * (i + 1))
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
            json.dumps({"oldid": oldid, "text": text}, ensure_ascii=False),
            "utf-8")
    return oldid, text


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
    """wikitext → {节名简体: 正文}。只认 === 三级节；保留粗体标记
    （'''乾卦''' 等作 split_wanwu 分段锚点，输出前再剥除）。"""
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


def strip_bold(s):
    return re.sub(r"'{2,}", "", s)


def split_wanwu(body):
    """「八卦万物属类」大章按 '''某卦''' 粗体行切为八单元。"""
    marker = re.compile(r"^'{2,}([乾坤震巽坎离艮兑])卦'{2,}$", re.M)
    hits = [(m.start(), m.end(), m.group(1)) for m in marker.finditer(body)]
    assert len(hits) == 8, f"万物属类应分八卦，实得 {len(hits)}"
    units = []
    for k, (_s, e, gua) in enumerate(hits):
        end = hits[k + 1][0] if k + 1 < len(hits) else len(body)
        units.append((gua, strip_bold(body[e:end]).strip()))
    return units


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", help="页面缓存目录（重跑免重新抓取）")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "yijing_agent/data/meihua.json"))
    args = ap.parse_args()

    units, warnings, pages_meta = [], [], {}

    # 卷一：起卦诸法、占例与类象
    oldid, text = fetch_page(TITLES["1"], args.cache_dir)
    pages_meta[TITLES["1"]] = oldid
    sec1 = parse_sections(text)
    for sec_name, uid, disp, keyword in SECTIONS_J1:
        body = sec1.get(sec_name, "")
        assert body, f"卷一节未找到或为空: {sec_name}（现有节: {sorted(sec1)}）"
        assert keyword is None or keyword in body, \
            f"卷一「{sec_name}」未见关键词「{keyword}」，疑串节，请人工核对"
        units.append({"id": uid, "title": disp, "text": strip_bold(body)})
    wanwu = sec1.get("八卦万物属类", "")
    assert wanwu, "卷一「八卦万物属类」大章未找到"
    for gua, body in split_wanwu(wanwu):
        assert body, f"万物属类·{gua} 为空"
        units.append({"id": f"1:xiang:wanwu:{_WANWU_PINYIN[gua]}",
                      "title": f"八卦万物属类·{gua}", "text": body,
                      "gua": gua})

    # 卷二：体用总诀 + 十八占
    time.sleep(1)
    oldid, text = fetch_page(TITLES["2"], args.cache_dir)
    pages_meta[TITLES["2"]] = oldid
    sec2 = parse_sections(text)
    for sec_name, uid, disp in SECTIONS_J2:
        body = sec2.get(sec_name, "")
        assert body, f"卷二节未找到或为空: {sec_name}（现有节: {sorted(sec2)}）"
        if "体" not in body or "用" not in body:
            warnings.append(f"{sec_name} 正文未见体/用字样，请人工核对")
        units.append({"id": uid, "title": disp, "text": body})

    out = {
        "meta": {
            "work": "《梅花易数》卷一（起卦诸法与占例）·卷二（体用总诀与十八占）",
            "source": "维基文库《梅花易數》卷一、卷二（旧题邵雍撰，"
                      "实为明人辑纂；页面标点为维基文库贡献者所加）",
            "base_url": "https://zh.wikisource.org/wiki/梅花易數",
            "pages": pages_meta,
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "conversion": "繁→简 OpenCC t2s",
            "notes": "卷一「八卦万物属类」大章按八卦切为八单元"
                     "（1:xiang:wanwu:*）；单元 id 首段为卷次",
            "imported": "2026-08-25",
            "proofread": False,
            "warnings": warnings,
        },
        "units": units,
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    n1 = sum(1 for u in units if u["id"].startswith("1:"))
    n2 = len(units) - n1
    print(f"卷一 {n1} 单元 + 卷二 {n2} 单元 → {args.out}")
    print(f"警告 {len(warnings)} 条")
    for w in warnings:
        print("  -", w)


if __name__ == "__main__":
    main()
