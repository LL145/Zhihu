"""典籍知识库：结构化查表（非向量检索）。

引文编号（cite_id）规则：
    zhouyi:{卦id}:guaci       卦辞
    zhouyi:{卦id}:yao:{爻位}   爻辞（爻位 1-6 自下而上）
    zhouyi:{卦id}:extra       用九 / 用六（仅乾、坤）
    tuan:{卦id}               彖传
    daxiang:{卦id}            象传·大象
    xiaoxiang:{卦id}:{爻位}    象传·小象
    xiaoxiang:{卦id}:extra    用九 / 用六之小象

注疏层（v1.5 第一期：王弼《周易注》，data/wangbi.json）：
    wangbi:{卦id}:{部位…}     对应经文单元的王弼注，如 wangbi:49:yao:5、
                              wangbi:1:tuan、wangbi:2:xiaoxiang:extra。
    注疏只作解读语境与引文来源，不参与断辞结论。
"""

import json
from pathlib import Path

from .trigrams import TRIGRAMS

DATA_PATH = Path(__file__).parent / "data" / "hexagrams.json"
WANGBI_PATH = Path(__file__).parent / "data" / "wangbi.json"


def wangbi_id(scripture_cite_id):
    """经文 cite_id → 对应王弼注 cite_id。"""
    parts = scripture_cite_id.split(":")
    if parts[0] == "zhouyi":          # zhouyi:i:guaci / yao:p / extra
        return "wangbi:" + ":".join(parts[1:])
    if parts[0] in ("tuan", "daxiang"):
        return f"wangbi:{parts[1]}:{parts[0]}"
    if parts[0] == "xiaoxiang":       # xiaoxiang:i:p / extra
        return f"wangbi:{parts[1]}:xiaoxiang:{parts[2]}"
    raise ValueError(f"未知经文 cite_id: {scripture_cite_id}")


class KnowledgeBase:
    def __init__(self, path=DATA_PATH, wangbi_path=WANGBI_PATH):
        raw = json.loads(Path(path).read_text("utf-8"))
        self.meta = raw["meta"]
        self.by_id = {h["id"]: h for h in raw["hexagrams"]}
        self.by_binary = {tuple(h["binary"]): h["id"] for h in raw["hexagrams"]}
        self._citations = {}
        for h in raw["hexagrams"]:
            n, i = h["name"], h["id"]
            self._add(f"zhouyi:{i}:guaci", f"《周易·{n}》卦辞", h["guaci"])
            self._add(f"tuan:{i}", f"《彖传·{n}》", h["tuan"])
            self._add(f"daxiang:{i}", f"《象传·{n}·大象》", h["daxiang"])
            for y in h["yao"]:
                self._add(f"zhouyi:{i}:yao:{y['pos']}", f"《周易·{n}·{y['name']}》爻辞", y["text"])
                self._add(f"xiaoxiang:{i}:{y['pos']}", f"《象传·{n}·{y['name']}》小象", y["xiaoxiang"])
            if h["extra"]:
                self._add(f"zhouyi:{i}:extra", f"《周易·{n}·{h['extra']['name']}》", h["extra"]["text"])
                self._add(f"xiaoxiang:{i}:extra", f"《象传·{n}·{h['extra']['name']}》小象", h["extra"]["xiaoxiang"])

        # 注疏层：王弼注挂到对应经文单元（缺文件则静默降级为无注疏）
        self._commentary = {}
        wp = Path(wangbi_path) if wangbi_path else None
        if wp and wp.exists():
            wb = json.loads(wp.read_text("utf-8"))
            self.wangbi_meta = wb["meta"]
            for scid, text in wb["notes"].items():
                wid = wangbi_id(scid)
                label = "王弼《周易注》·注" + self._citations[scid]["source"]
                self._add(wid, label, text)
                self._commentary[scid] = self._citations[wid]
        else:
            self.wangbi_meta = None

    def commentary(self, scripture_cite_id):
        """经文单元的王弼注 citation（无注返回 None）。"""
        return self._commentary.get(scripture_cite_id)

    def _add(self, cite_id, label, text):
        self._citations[cite_id] = {"cite_id": cite_id, "source": label, "text": text}

    def citation(self, cite_id):
        return self._citations[cite_id]

    def has(self, cite_id):
        return cite_id in self._citations

    def hexagram(self, hid):
        return self.by_id[hid]

    def id_of(self, binary):
        return self.by_binary[tuple(binary)]

    def full_name(self, hid):
        """通行卦名，如「水雷屯」「乾为天」。"""
        h = self.by_id[hid]
        lower, upper = h["trigrams"]
        if lower == upper:
            return f"{h['name']}为{TRIGRAMS[lower]['nature']}"
        return f"{TRIGRAMS[upper]['nature']}{TRIGRAMS[lower]['nature']}{h['name']}"
