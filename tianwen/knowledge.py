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

易传补编（十翼之说卦、系辞、序卦、杂卦、文言，data/yizhuan.json）：
    shuogua:{章}[:{卦}]       说卦传，依朱子《周易本义》章次；类象诸章
                              按八卦再分（如 shuogua:11:qian 乾之广象）。
    xici:{shang|xia}:{章}     系辞上下传，章次依所据《易傳》页面
                              （上十二章、下九章）。大衍筮法出
                              xici:shang:9，太极两仪出 xici:shang:11。
    xugua:{shang|xia}         序卦传上下篇。
    zagua:1                   杂卦传。
    xugua:{卦id}:gua           序卦传之逐卦一行（卦之由来，运行时自整篇切出）。
    zagua:{卦id}:gua           杂卦传之逐卦一行（卦之性，同上）。
    wenyan:{卦id}:{部位…}     乾坤文言，按所释经文单元锚定（wenyan:1:guaci、
                              wenyan:1:yao:3、wenyan:1:extra……）。
    以上皆孔门传文（经传原文，可引为据）；说卦供梅花体用取象，
    文言挂乾坤经文单元随选文自动附入，系辞、序卦、杂卦为可检索
    可引用之全文语料。均不参与定例断辞。

梅花语料（《梅花易数》卷一、卷二，data/meihua.json）：
    meihua:1:qi:{法}          卷一起卦诸法（qi:shijian 年月日时起例、
                              qi:zi 字占、qi:zishu 一字占至十一字占……），
                              起卦引擎（casting.py）所引原文皆在此。
    meihua:1:li:{例}          卷一占例（li:guanmei 观梅占、
                              li:xilinsi 西林寺牌额占……）。
    meihua:1:xiang:…          卷一八卦类象与八卦万物属类
                              （xiang:wanwu:{卦} 逐卦一单元）。
    meihua:1:{余}             卷一其余基础章（guashu 周易卦数、
                              guachu 卦以八除、hou:* 端法诸占附诀……）。
    meihua:2:tiyong           卷二体用总诀（梅花断法之纲，梅花法恒附）。
    meihua:2:zhan:{章}        卷二十八占之占章（如 meihua:2:zhan:hunyin），
                              按问事类别附取（selection.TOPIC_ZHAN）。
    占法之书原文，可引为据；不参与定例断辞。

六爻纳甲典籍层（藏书；v4 六爻起卦之典据先行，不入现行选文，
data/{jingfang,huozhulin,huangjince}.json，见 tools/import_wikisource_liuyao.py）：
    jingfang:{hid}            《京氏易传》八宫六十四卦逐卦本文
                              （hid 为周易通行卦序 id，只取京氏本文不取注）。
    jingfang:xia:{n}          卷下总说／算法／总结。
    huozhulin:{n}             《火珠林》逐节（原书「注云」注文并入正文）。
    huangjince:{n}            《黄金策》逐章（总断千金赋、天时……何知章）。
    占法之书原文，可检索可引用；不参与定例断辞。

西洋占星典籍层（藏书＋语境；data/tetrabiblos.json，
tools/import_gutenberg_tetrabiblos.py）：
    tetra:{卷}:{章}           托勒密《占星四书》（Tetrabiblos）四卷逐章，
                              Ashmand 英译公版底本。引文一律用英译原文
                              （校验器拉丁通道逐字比对），中译只作解释性
                              转述；本命盘语境层按判类与题材附章
                              （astro/natal.py），不参与定例断辞。
"""

import json
import re
from pathlib import Path

from .trigrams import TRIGRAMS

DATA_PATH = Path(__file__).parent / "data" / "hexagrams.json"
WANGBI_PATH = Path(__file__).parent / "data" / "wangbi.json"
YIZHUAN_PATH = Path(__file__).parent / "data" / "yizhuan.json"
MEIHUA_PATH = Path(__file__).parent / "data" / "meihua.json"

#: 六爻纳甲典籍层：cite_id 前缀 → 数据文件
LIUYAO_PATHS = {
    "jingfang": Path(__file__).parent / "data" / "jingfang.json",
    "huozhulin": Path(__file__).parent / "data" / "huozhulin.json",
    "huangjince": Path(__file__).parent / "data" / "huangjince.json",
}

TETRA_PATH = Path(__file__).parent / "data" / "tetrabiblos.json"


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


_YAO_CH = {1: "初", 2: "二", 3: "三", 4: "四", 5: "五", 6: "上"}
_CH_NUM = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
           "十一", "十二")


def _cn_num(n):
    """1–39 → 汉数（章序展示用）。"""
    if n < 13:
        return _CH_NUM[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else _CH_NUM[tens]) + "十" + \
        (_CH_NUM[ones] if ones else "")


def _wenyan_label(gua_name, part):
    """wenyan 单元键（如 guaci / yao:3 / extra）→ 展示名。"""
    if part == "guaci":
        return f"《文言·{gua_name}》释卦辞"
    if part == "extra":
        return f"《文言·{gua_name}》释{'用九' if gua_name == '乾' else '用六'}"
    pos = int(part.split(":")[1])
    return f"《文言·{gua_name}》释{_YAO_CH[pos]}爻"


class KnowledgeBase:
    def __init__(self, path=DATA_PATH, wangbi_path=WANGBI_PATH,
                 yizhuan_path=YIZHUAN_PATH, meihua_path=MEIHUA_PATH,
                 liuyao_paths=None, tetra_path=TETRA_PATH):
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

        # 易传补编：说卦（独立单元）与文言（挂乾坤经文单元）
        self._wenyan = {}
        self.shuogua_ids = []
        yp = Path(yizhuan_path) if yizhuan_path else None
        if yp and yp.exists():
            yz = json.loads(yp.read_text("utf-8"))
            self.yizhuan_meta = yz["meta"]
            for unit in yz["shuogua"]:
                uid, chapter = unit["id"], unit["id"].split(":")[0]
                label = f"《说卦传》第{_CH_NUM[int(chapter)]}章"
                if unit.get("gua"):
                    label += f"·{unit['gua']}"
                self._add(f"shuogua:{uid}", label, unit["text"])
                self.shuogua_ids.append(f"shuogua:{uid}")
            for key, text in yz["wenyan"].items():
                hid, part = key.split(":", 1)
                gua_name = self.by_id[int(hid)]["name"]
                wid = f"wenyan:{key}"
                self._add(wid, _wenyan_label(gua_name, part), text)
                scid = f"zhouyi:{hid}:{part}"
                assert scid in self._citations, f"文言挂在未知经文单元: {scid}"
                self._wenyan[scid] = self._citations[wid]
            _pian = {"shang": "上", "xia": "下"}
            for unit in yz.get("xici", []):
                part, n = unit["id"].split(":")
                self._add(f"xici:{unit['id']}",
                          f"《系辞{_pian[part]}传》第{_CH_NUM[int(n)]}章",
                          unit["text"])
            for unit in yz.get("xugua", []):
                self._add(f"xugua:{unit['id']}",
                          f"《序卦传》{_pian[unit['id']]}篇", unit["text"])
                self._slice_xugua(unit["text"])
            for unit in yz.get("zagua", []):
                self._add(f"zagua:{unit['id']}", "《杂卦传》", unit["text"])
                self._slice_zagua(unit["text"])
        else:
            self.yizhuan_meta = None

        # 梅花语料：《梅花易数》卷一起卦诸法与占例、卷二体用总诀与十八占
        mp = Path(meihua_path) if meihua_path else None
        if mp and mp.exists():
            mh = json.loads(mp.read_text("utf-8"))
            self.meihua_meta = mh["meta"]
            for unit in mh["units"]:
                juan = {"1": "一", "2": "二"}[unit["id"].split(":", 1)[0]]
                self._add(f"meihua:{unit['id']}",
                          f"《梅花易数》·卷{juan}·{unit['title']}",
                          unit["text"])
        else:
            self.meihua_meta = None

        # 六爻纳甲典籍层：京氏易传、火珠林、黄金策（藏书，不入现行选文）
        self.liuyao_meta = {}
        for key, lp in (liuyao_paths if liuyao_paths is not None
                        else LIUYAO_PATHS).items():
            lp = Path(lp)
            if not lp.exists():
                self.liuyao_meta[key] = None
                continue
            data = json.loads(lp.read_text("utf-8"))
            self.liuyao_meta[key] = data["meta"]
            short = data["meta"]["short"]
            for unit in data["units"]:
                self._add(f"{key}:{unit['id']}",
                          f"《{short}》·{unit['title']}", unit["text"])

        # 西洋占星典籍层：托勒密《占星四书》（Ashmand 英译，藏书＋语境）
        tp = Path(tetra_path) if tetra_path else None
        if tp and tp.exists():
            tb = json.loads(tp.read_text("utf-8"))
            self.tetra_meta = tb["meta"]
            juan = {"1": "一", "2": "二", "3": "三", "4": "四"}
            for unit in tb["units"]:
                j, c = unit["id"].split(":")
                self._add(f"tetra:{unit['id']}",
                          f"《占星四书》卷{juan[j]}·第{_cn_num(int(c))}章"
                          f"（{unit['title']}）", unit["text"])
        else:
            self.tetra_meta = None

    # ── 序卦、杂卦逐卦切片（运行时自整篇派生，非数据订正） ────────────
    # 单元 xugua:{卦id}:gua / zagua:{卦id}:gua，文为整篇之整行（逐字子串，
    # 引文校验一体覆盖）；序卦按「受之以X」定所属之卦（乾坤与下篇首卦咸
    # 无此语，不切），杂卦按各分句句首之卦名（「而」字起者去「而」；
    # 「比乐师忧」式四字两卦并取），一卦只取首见之行。

    def _name_ids(self):
        names = {h["name"]: h["id"] for h in self.by_id.values()}
        if "习坎" in names:      # 序卦、杂卦称「坎」
            names.setdefault("坎", names["习坎"])
        return names

    def _slice_xugua(self, text):
        names = self._name_ids()
        for line in text.split("\n"):
            m = re.search(r"受之(?:以)?([^，。；]+?)[，。；]", line)
            if not m or m.group(1) not in names:
                continue
            hid = names[m.group(1)]
            cid = f"xugua:{hid}:gua"
            if cid not in self._citations:
                self._add(cid, f"《序卦传》·{m.group(1)}", line.strip())

    def _slice_zagua(self, text):
        names = self._name_ids()
        alt = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
        lead = re.compile(rf"^((?:{alt})(?:、(?:{alt}))*)")
        pair = re.compile(rf"^.({alt}).$")
        for line in text.split("\n"):
            subjects = []
            for clause in re.split(r"[，；]", line.strip().rstrip("。")):
                clause = clause.lstrip("而")
                m = lead.match(clause)
                if not m:
                    continue
                subjects += m.group(1).split("、")
                m2 = pair.match(clause[len(m.group(1)):])
                if m2:
                    subjects.append(m2.group(1))
            for name in subjects:
                cid = f"zagua:{names[name]}:gua"
                if cid not in self._citations:
                    self._add(cid, f"《杂卦传》·{name}", line.strip())

    def commentary(self, scripture_cite_id):
        """经文单元的王弼注 citation（无注返回 None）。"""
        return self._commentary.get(scripture_cite_id)

    def wenyan(self, scripture_cite_id):
        """经文单元的文言传 citation（仅乾坤有，无则返回 None）。"""
        return self._wenyan.get(scripture_cite_id)

    def _add(self, cite_id, label, text):
        self._citations[cite_id] = {"cite_id": cite_id, "source": label, "text": text}

    def citation(self, cite_id):
        return self._citations[cite_id]

    def citations(self):
        """全部引文单元（corpus 检索层遍历用）。"""
        return self._citations.values()

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
