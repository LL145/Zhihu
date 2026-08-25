"""紫微库：结构化查表（非向量检索），data/ziwei.json。

引文编号（cite_id）规则（导入自维基文库《紫微斗數全書》，见
tools/import_wikisource_ziwei.py）：
    ziwei:2:ming:{star}           卷二·命宫·某星论断文
    ziwei:2:ming:{star}:ge:{n}    其分宫格诗行（meta.branches 记所涉宫支）
    ziwei:2:ming:{star}:male      某星入男命吉凶诀
    ziwei:2:ming:{star}:female    某星入女命吉凶诀（底本天梁缺）
    ziwei:2:ming:{star}:xian      某星入限吉凶诀
    ziwei:2:gong:{palace}:{star}  卷二·某宫诸星断语（zonglun 为宫总论，
                                  guanlu:ding{n} 为官禄宫「定公卿」等断诀）
    ziwei:1:wenda:{star}          卷一·诸星问答论
    ziwei:3:daxian / erxian       卷三·论大限十年祸福何如 / 论二限太岁吉凶

紫微库二期（卷一赋文与格局诸诀，格局识别之典据；解读语境用）：
    ziwei:1:fu:{seg}              赋文诸论整节一条（taiwei 太微赋、
                                  xingxing 形性赋、xingyuan 星垣论、
                                  zhunsheng 斗数准绳、fawei 斗数发微论、
                                  goulv 重补斗数彀率、zengtaiwei 增补太微赋、
                                  gusui 斗数骨髓赋、nvgusui 女命骨髓赋、
                                  dedifugui／shixianpinjian 十二宫诸星
                                  得地富贵论／失陷贫贱论）
    ziwei:1:shideng:{n}           定富贵贫贱十等论，逐行一论
    ziwei:1:hege:{branch}         十二宫诸星得地合格诀，按安命宫支
                                  （branches 记宫支；底本「戍」归一作「戌」）
    ziwei:1:poge:{n}              十二宫诸星失陷破格诀，行可兼数宫支
    ziwei:1:ju:{cat}:{n}          定富局(fu)/定贵局(gui)/定贫贱局(pinjian)/
                                  定杂局(za)，逐行一局（局名在 source）

查表接线（选文层取用）：hege/poge_lines 按安命宫支取格诀；desk 按星名
自赋文格诀池机械召回候选断语行（书桌，只入语境、可引不可断）。
"""

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "ziwei.json"

#: 星名 → cite_id 段（与导入脚本一致）
STAR_SEG = {
    "紫微": "ziwei", "天机": "tianji", "太阳": "taiyang", "武曲": "wuqu",
    "天同": "tiantong", "廉贞": "lianzhen", "天府": "tianfu", "太阴": "taiyin",
    "贪狼": "tanlang", "巨门": "jumen", "天相": "tianxiang", "天梁": "tianliang",
    "七杀": "qisha", "破军": "pojun",
}

#: 宫名 → cite_id 段
PALACE_SEG = {"命宫": "ming", "兄弟": "xiongdi", "妻妾": "qiqie",
              "子女": "zinv", "财帛": "caibo", "疾厄": "jie",
              "迁移": "qianyi", "奴仆": "nupu", "官禄": "guanlu",
              "田宅": "tianzhai", "福德": "fude", "父母": "fumu"}


class ZiweiKB:
    def __init__(self, path=DATA_PATH):
        raw = json.loads(Path(path).read_text("utf-8"))
        self.meta = raw["meta"]
        self._records = raw["records"]
        self._citations = {}
        self._by_gong = {}       # (宫名, 星名) → cite_id
        self._ge = {}            # 星名 → [(branches, cite_id)]
        self._hege = {}          # 安命宫支 → cite_id（得地合格诀）
        self._poge = []          # [(宫支列表, cite_id)]（失陷破格诀）
        for cid, r in self._records.items():
            label = "《紫微斗数全书》" + r["source"][len("紫微斗数全书"):]
            self._citations[cid] = {"cite_id": cid, "source": label,
                                    "text": r["text"]}
            if r["kind"] == "gong":
                for s in r["stars"]:
                    self._by_gong[(r["palace"], s)] = cid
            elif r["kind"] == "ge":
                self._ge.setdefault(r["stars"][0], []).append(
                    (r.get("branches", []), cid))
            elif r["kind"] == "hege":
                self._hege[r["branches"][0]] = cid
            elif r["kind"] == "poge":
                self._poge.append((r["branches"], cid))

    def citation(self, cite_id):
        return self._citations[cite_id]

    def citations(self):
        """全部引文单元（corpus 检索层遍历用）。"""
        return self._citations.values()

    def has(self, cite_id):
        return cite_id in self._citations

    def record(self, cite_id):
        return self._records[cite_id]

    # ── 查表 ──────────────────────────────────────────────────────────

    def ming(self, star):
        """某主星之命宫论断文 cite_id（无则 None）。"""
        cid = f"ziwei:2:ming:{STAR_SEG[star]}"
        return cid if self.has(cid) else None

    def ming_jue(self, star, tag):
        """入男命/入女命/入限吉凶诀。tag ∈ male/female/xian。"""
        cid = f"ziwei:2:ming:{STAR_SEG[star]}:{tag}"
        return cid if self.has(cid) else None

    def ge_lines(self, star, branch):
        """分宫格中涉及某宫支的诗行 cite_id 列表。"""
        return [cid for brs, cid in self._ge.get(star, []) if branch in brs]

    def gong(self, palace, star):
        """某宫某星断语 cite_id（底本缺文则 None）。"""
        return self._by_gong.get((palace, star))

    def gong_zonglun(self, palace):
        cid = f"ziwei:2:gong:{PALACE_SEG[palace]}:zonglun"
        return cid if self.has(cid) else None

    def hege(self, branch):
        """安命某宫支之得地合格诀 cite_id（十二宫支俱全）。"""
        return self._hege.get(branch)

    def poge_lines(self, branch):
        """失陷破格诀中涉及某安命宫支的行 cite_id 列表。"""
        return [cid for brs, cid in self._poge if branch in brs]

    def wenda(self, star):
        cid = f"ziwei:1:wenda:{STAR_SEG[star]}"
        return cid if self.has(cid) else None

    def lun(self, seg):
        """卷三论说：seg ∈ daxian / erxian。"""
        cid = f"ziwei:3:{seg}"
        return cid if self.has(cid) else None

    # ── 书桌（确定性召回层，DESIGN §9 v3 后续） ───────────────────────

    def desk(self, stars, cap=8):
        """按星名自赋文格诀池机械召回候选断语行（倒排，确定性）。

        池为卷一赋文诸论、十等论、定富贵贫贱杂诸局（kind ∈ fu/shideng/
        ju），依库序逐行；星名字样命中即收，每星至多 cap 行、命中总数
        如实返回（不足不补、超额截取须由调用方标注）。只入解读语境
        （可引不可断），不参与断辞。返回
        [(星名, [(cite_id, 行文), …], 命中总数), …]，无命中之星不列。
        """
        if not hasattr(self, "_desk_pool"):
            self._desk_pool = [
                (cid, line.strip())
                for cid, r in self._records.items()
                if r["kind"] in ("fu", "shideng", "ju")
                for line in r["text"].split("\n") if line.strip()]
        out = []
        for star in stars:
            hits = [(cid, ln) for cid, ln in self._desk_pool if star in ln]
            if hits:
                out.append((star, hits[:cap], len(hits)))
        return out
