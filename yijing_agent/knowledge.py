"""典籍知识库：结构化查表（非向量检索）。

引文编号（cite_id）规则：
    zhouyi:{卦id}:guaci       卦辞
    zhouyi:{卦id}:yao:{爻位}   爻辞（爻位 1-6 自下而上）
    zhouyi:{卦id}:extra       用九 / 用六（仅乾、坤）
    tuan:{卦id}               彖传
    daxiang:{卦id}            象传·大象
    xiaoxiang:{卦id}:{爻位}    象传·小象
    xiaoxiang:{卦id}:extra    用九 / 用六之小象
"""

import json
from pathlib import Path

from .trigrams import TRIGRAMS

DATA_PATH = Path(__file__).parent / "data" / "hexagrams.json"


class KnowledgeBase:
    def __init__(self, path=DATA_PATH):
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
