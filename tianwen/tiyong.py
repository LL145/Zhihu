"""梅花体用生克（确定性代码）：《梅花易数》卷二「体用总诀」之机断。

体卦为主、用卦为事（动爻所在之卦为用，不动为体），以八卦五行论生克：
「体克用，诸事吉；用克体，诸事凶。体生用，有耗失之患；用生体，有进益
之喜。体用比和，则百事顺遂」（meihua:2:tiyong）。互卦为事之中间、变卦
为事之终（「用为事之端……互为事之中间……变为事之终」），各与体论生克；
卦气以月令论旺衰（meihua:1:guaqi:wang / shuai）；体党用党计其多寡。

全程无随机数、无模型：同卦同月必同。所引句一律为库文逐字子串（测试
钉住），解读层引用仍过校验闸门。今法约定（凭证如实标注）：
- 辰戌丑未月（农历三、六、九、十二月）依「四季之月」条论旺衰，余月
  依四时——底本春/四季两条于辰月等处重叠，取四季之月条为准；
- 乾坤纯卦无互（「乾坤无互，互其变卦」），依文取变卦之互；
- 占章之句按体用关系字样自所问占章机械截取，无对应字样则不取。
"""

import re
from dataclasses import dataclass, field

from . import hexagrams
from .trigrams import BY_LINES, PINYIN

#: 八宫所属五行（meihua:1:bagong「乾、兑，金；坤、艮，土；震、巽，木；坎，水；离，火」）
WUXING = {"乾": "金", "兑": "金", "坤": "土", "艮": "土",
          "震": "木", "巽": "木", "坎": "水", "离": "火"}

#: 五行生克（meihua:1:wuxing）
SHENG = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}

#: 他卦与体之关系 → 用卦之称谓（总诀字样）
YONG_LABEL = {"生体": "用生体", "克体": "用克体", "体生": "体生用",
              "体克": "体克用", "比和": "体用比和"}

#: 总诀明文（逐字子串，测试钉住）：用卦五种关系之断
ZONGJUE = {
    "用生体": "用生体，有进益之喜",
    "体克用": "体克用，诸事吉",
    "用克体": "用克体，诸事凶",
    "体生用": "体生用，有耗失之患",
    "体用比和": "体用比和，则百事顺遂",
}

#: 互变之义（总诀明文）
HU_BIAN_SENTENCE = "用为事之端……互为事之中间……变为事之终"
HU_BIAN_QUOTES = ("互乃中间之应，变乃末后之期",
                  "用吉变凶者，先吉后凶；用凶变吉者，先凶后吉")
DANG_QUOTE = "体党多而体势盛，用党多则体势衰"
GUAQI_QUOTE = "体盛则吉，体衰则凶"

#: 月令 → 四时（农历月；辰戌丑未月＝三六九十二月作「季」，约定见模块说明）
_SEASON = {1: "春", 2: "春", 3: "季", 4: "夏", 5: "夏", 6: "季",
           7: "秋", 8: "秋", 9: "季", 10: "冬", 11: "冬", 12: "季"}
_WANG = {"春": {"震", "巽"}, "夏": {"离"}, "秋": {"乾", "兑"},
         "冬": {"坎"}, "季": {"坤", "艮"}}
_SHUAI = {"春": {"坤", "艮"}, "夏": {"乾", "兑"}, "秋": {"震", "巽"},
          "冬": {"离"}, "季": {"坎"}}
_SEASON_LABEL = {"春": "春", "夏": "夏", "秋": "秋", "冬": "冬",
                 "季": "四季之月（辰戌丑未）"}


def relation(ti, other):
    """他卦对体卦之五行关系：生体 / 克体 / 体生 / 体克 / 比和。"""
    a, b = WUXING[ti], WUXING[other]
    if a == b:
        return "比和"
    if SHENG[b] == a:
        return "生体"
    if KE[b] == a:
        return "克体"
    if SHENG[a] == b:
        return "体生"
    assert KE[a] == b
    return "体克"


def guaqi(trigram, month):
    """卦气旺衰：旺 / 衰 / 平（不在旺衰之列）。month 为农历月数。"""
    season = _SEASON[month]
    if trigram in _WANG[season]:
        return "旺"
    if trigram in _SHUAI[season]:
        return "衰"
    return "平"


def trigram_names(binary):
    """六爻爻画（自下而上）→ (下卦名, 上卦名)。"""
    b = tuple(binary)
    return BY_LINES[b[:3]], BY_LINES[b[3:]]


@dataclass
class Other:
    """与体相对之一卦：用 / 下互 / 上互 / 变。"""
    role: str
    name: str
    rel: str            # 生体 / 克体 / 体生 / 体克 / 比和

    @property
    def wx(self):
        return WUXING[self.name]


@dataclass
class TiyongAnalysis:
    ti: str
    yong: str
    rel_yong: str                 # 总诀字样：用生体 / 体克用 / …
    hu: list                      # [Other, Other]（下互、上互）
    bian: Other
    hu_note: str = ""             # 乾坤无互之约定
    month: int = None
    guaqi_ti: str = None          # 旺 / 衰 / 平；月未知则 None
    dang_ti: int = 0
    dang_yong: int = 0
    sheng_ti: list = field(default_factory=list)   # [(Other, 总诀句)]
    ke_ti: list = field(default_factory=list)
    zhan_id: str = None
    zhan_title: str = ""
    zhan_clause: str = ""         # 所问占章中对应关系之句（逐字）
    zhan_qi: list = field(default_factory=list)    # 占章论应期之句
    shixu: list = field(default_factory=list)      # [(卦名, 万物属类时序句, cite_id)]

    @property
    def zongjue(self):
        return ZONGJUE[self.rel_yong]

    @property
    def others(self):
        return [Other("用", self.yong, _rel_of_label(self.rel_yong))] \
            + list(self.hu) + [self.bian]

    def summary(self):
        """一览用的一行：体用与互变生克。"""
        hu = "、".join(f"{o.name}{o.wx}（{o.rel}）" for o in self.hu)
        return (f"体{self.ti}{WUXING[self.ti]}／用{self.yong}{WUXING[self.yong]}"
                f"→{self.rel_yong}；互{hu}；变{self.bian.name}{self.bian.wx}"
                f"（{self.bian.rel}）" + self.guaqi_text(short=True))

    def guaqi_text(self, short=False):
        if self.guaqi_ti is None:
            return "" if short else "月令未知，不论卦气"
        season = _SEASON_LABEL[_SEASON[self.month]]
        s = f"体{self.ti}{WUXING[self.ti]}于{season}为{self.guaqi_ti}"
        if self.guaqi_ti == "平":
            s += "（不在旺衰之列）"
        return f"；卦气：{s}" if short else s

    def lines(self):
        """凭证与提示词用的逐行说明（机断结果，非原文）。"""
        out = [f"体卦{self.ti}（{WUXING[self.ti]}），用卦{self.yong}"
               f"（{WUXING[self.yong]}）：{self.rel_yong}——总诀「{self.zongjue}」"]
        hu = "、".join(f"{o.name}（{o.wx}，{o.rel}）" for o in self.hu)
        out.append(f"互卦{hu}为事之中间；变卦{self.bian.name}"
                   f"（{self.bian.wx}，{self.bian.rel}）为事之终"
                   + (f"（{self.hu_note}）" if self.hu_note else ""))
        out.append(f"卦气：{self.guaqi_text()}")
        out.append(f"体党{self.dang_ti}、用党{self.dang_yong}"
                   f"（用互变三卦中与体、用同五行者之数；「{DANG_QUOTE}」）")
        if self.sheng_ti:
            out.append("生体之卦：" + "；".join(
                f"{o.name}（{o.role}）「{s}」" for o, s in self.sheng_ti))
        if self.ke_ti:
            out.append("克体之卦：" + "；".join(
                f"{o.name}（{o.role}）「{s}」" for o, s in self.ke_ti))
        if self.zhan_clause:
            out.append(f"所问占章（{self.zhan_title}）：「{self.zhan_clause}」")
        for s in self.zhan_qi:
            out.append(f"应期之法（{self.zhan_title}）：「{s}」")
        for name, s, _cid in self.shixu:
            out.append(f"{name}卦时序（万物属类，应期之参）：「{s}」")
        return out


def _rel_of_label(label):
    return next(k for k, v in YONG_LABEL.items() if v == label)


def _sentence_after(text, head):
    """自 head 起截至句号（含头不含号）；无 head 返回空。"""
    i = text.find(head)
    if i < 0:
        return ""
    j = text.find("。", i)
    return text[i:j] if j >= 0 else text[i:]


def _zhan_clause(text, label):
    """所问占章中对应关系之句：字样起，至句号/分号止（「用生体。不谋
    而成」式标点讹为句号者，跳过紧随字样之一个标点）。"""
    m = re.search(re.escape(label) + r"[，。；、]?[^。；]*", text)
    return m.group(0).rstrip("，、") if m else ""


def _zhan_qi_sentences(text):
    """占章中论应期之句（含「卦气」「时序」「日期」「之日」字样者）。"""
    out = []
    for s in re.split(r"[。\n]", text):
        s = s.strip()
        if s and re.search("卦气|时序|日期|之日", s):
            out.append(s)
    return out


def analyze(kb, ben_binary, zhi_binary, moving_pos, month=None, zhan_id=None):
    """体用生克机断。kb 须有 meihua:2:tiyong（缺库则调用方不走此路）。"""
    lower, upper = trigram_names(ben_binary)
    zl, zu = trigram_names(zhi_binary)
    if moving_pos <= 3:
        ti, yong, bian_name = upper, lower, zl
    else:
        ti, yong, bian_name = lower, upper, zu
    rel_yong = YONG_LABEL[relation(ti, yong)]

    hu_note = ""
    src = list(ben_binary)
    if len(set(src)) == 1:            # 乾坤纯卦：「乾坤无互，互其变卦」
        src = list(zhi_binary)
        hu_note = "乾坤无互，互其变卦"
    hl, hu_ = trigram_names(hexagrams.hu_binary(src))
    hu = [Other("下互", hl, relation(ti, hl)), Other("上互", hu_, relation(ti, hu_))]
    bian = Other("变", bian_name, relation(ti, bian_name))

    an = TiyongAnalysis(ti=ti, yong=yong, rel_yong=rel_yong, hu=hu, bian=bian,
                        hu_note=hu_note, month=month,
                        guaqi_ti=guaqi(ti, month) if month else None)
    ti_wx, yong_wx = WUXING[ti], WUXING[yong]
    for o in [Other("用", yong, relation(ti, yong))] + hu + [bian]:
        if o.wx == ti_wx:
            an.dang_ti += 1
        elif o.wx == yong_wx:
            an.dang_yong += 1

    zong = kb.citation("meihua:2:tiyong")["text"]
    for o in an.others:
        if o.rel == "生体":
            an.sheng_ti.append((o, _sentence_after(zong, f"{o.name}卦生体")))
        elif o.rel == "克体":
            an.ke_ti.append((o, _sentence_after(zong, f"{o.name}卦克体")))

    if zhan_id and kb.has(zhan_id):
        c = kb.citation(zhan_id)
        an.zhan_id = zhan_id
        an.zhan_title = c["source"].rsplit("·", 1)[-1]
        an.zhan_clause = _zhan_clause(c["text"], rel_yong)
        an.zhan_qi = _zhan_qi_sentences(c["text"])
        if an.zhan_qi:
            seen = set()
            for o, _s in an.sheng_ti + an.ke_ti:
                cid = f"meihua:1:xiang:wanwu:{PINYIN[o.name]}"
                if o.name in seen or not kb.has(cid):
                    continue
                seen.add(o.name)
                m = re.search(r"时序：[^。\n]*", kb.citation(cid)["text"])
                if m:
                    an.shixu.append((o.name, m.group(0), cid))
    return an
