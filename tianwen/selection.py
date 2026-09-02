"""断卦规则引擎：依占法规则确定应读的经文（确定性代码，杜绝挑拣）。

- 梅花易数（恒为一个动爻）：依《梅花易数》体用之说——动爻所在之卦为用、
  不动之卦为体；**体用生克为主断**（卷二体用总诀明文，tiyong.py 机断，
  所问占章之句并为主断依据），动爻爻辞为参（易辞，从卷一占例「易辞
  不吉矣……以卦论之」之序），本卦、之卦卦辞为参，本卦并附序卦（卦之
  由来）、杂卦（卦之性），体用两卦取象（《说卦传》广象）入解读。
  库中无体用总诀（缩减库）时退回旧例：动爻爻辞主断。
- 朱熹《易学启蒙》占法（select_zhuzi，0-6 个动爻）：为铜钱法/大衍法
  留存（ALGORITHM.md 七）——单一模式今用梅花，待可输入真实掷象时启用。
"""

from dataclasses import dataclass, field

from . import tiyong as tiyong_rules
from .knowledge import KnowledgeBase
from .trigrams import PINYIN

#: 断辞之义所出（《系辞上传》第三章「吉凶者，言乎其失得也……」）
XICI_DEF = "xici:shang:3"


@dataclass
class Reading:
    cite_id: str
    role: str            # 如「主断」「本卦卦辞（参）」
    primary: bool
    context_ids: list = field(default_factory=list)  # 所附传文（彖/象）
    excerpt: str = None  # 长单元之节引（呈现用；引文校验仍对全文）


@dataclass
class Selection:
    rule: str            # 占法标注
    readings: list       # [Reading]，首个 primary 为主断依据
    tiyong: object = None    # 梅花法：体用生克机断（tiyong.TiyongAnalysis）
    notes: list = field(default_factory=list)   # 呈现层如实标注

    @property
    def primary(self):
        return next(r for r in self.readings if r.primary)

    @property
    def primary_ids(self):
        """主断依据之 cite_id 集合（断语至少须据其一）。"""
        return frozenset(r.cite_id for r in self.readings if r.primary)


def _guaci(kb, hid, role, primary, with_xu_za=False):
    ctx = [f"tuan:{hid}", f"daxiang:{hid}"]
    if with_xu_za:   # 序卦（卦之由来）、杂卦（卦之性）逐卦单元，缺则不附
        ctx += [c for c in (f"xugua:{hid}:gua", f"zagua:{hid}:gua") if kb.has(c)]
    return Reading(cite_id=f"zhouyi:{hid}:guaci", role=role, primary=primary,
                   context_ids=ctx)


def _yao(kb, hid, pos, role, primary):
    return Reading(
        cite_id=f"zhouyi:{hid}:yao:{pos}", role=role, primary=primary,
        context_ids=[f"xiaoxiang:{hid}:{pos}"],
    )


def _extra(kb, hid, role, primary):
    return Reading(
        cite_id=f"zhouyi:{hid}:extra", role=role, primary=primary,
        context_ids=[f"xiaoxiang:{hid}:extra"],
    )


def tiyong(kb: KnowledgeBase, ben_id: int, moving_pos: int):
    """体用两卦（《梅花易数》：动爻所在之卦为用，不动之卦为体）。

    返回 (体卦名, 用卦名)。动爻在下卦（1-3）则下卦为用、上卦为体。
    """
    lower, upper = kb.hexagram(ben_id)["trigrams"]
    return (upper, lower) if moving_pos <= 3 else (lower, upper)


def _shuogua_readings(kb, ti, yong):
    """体用两卦之取象：说卦广象为主，《梅花易数》八卦万物属类逐卦附之
    （meihua:1:xiang:wanwu:*，v3.1.5 所候）；性情章附于体卦下。缺库则不附。"""
    readings = []
    for name, role_prefix in ((ti, "体卦"), (yong, "用卦")):
        cid = f"shuogua:11:{PINYIN[name]}"
        if not kb.has(cid):
            return []
        ctx = ["shuogua:7"] if role_prefix == "体卦" and kb.has("shuogua:7") else []
        wanwu = f"meihua:1:xiang:wanwu:{PINYIN[name]}"
        if kb.has(wanwu):
            ctx.append(wanwu)
        readings.append(Reading(
            cite_id=cid, role=f"{role_prefix}{name}取象（说卦·广象，"
                              "附梅花万物属类，入解读）",
            primary=False, context_ids=ctx))
    return readings


#: 问事类别 → 《梅花易数》十八占之占章（梅花法限用；无把握的类别不映射）
TOPIC_ZHAN = {
    "career": ("qiumou", "求谋占"),
    "study": ("qiuming", "求名占"),
    "love": ("hunyin", "婚姻占"),
    "travel": ("chuxing", "出行占"),
    "dwelling": ("jiazhai", "家宅占"),
}

#: 类别未映射时按问事题材（紫微分宫关键词表）回落之占章
ASPECT_ZHAN = {
    "财帛": ("qiucai", "求财占"),
    "官禄": ("qiuming", "求名占"),
    "妻妾": ("hunyin", "婚姻占"),
    "田宅": ("jiazhai", "家宅占"),
    "迁移": ("chuxing", "出行占"),
}


#: 类别与题材俱未映射时之通例占章：人事占（「然庶务之多，岂止十八占
#: 而已乎……占者以类而推之可也」，人事占即以体用总章决吉凶之通例）
DEFAULT_ZHAN = ("renshi", "人事占")


def _pick_zhan(tp, question):
    """占章取法：类别映射优先，未中则按题材关键词回落（同一张分宫表），
    再未中则取人事占通例。"""
    zhan = TOPIC_ZHAN.get(tp.key) if tp is not None else None
    if zhan is None and question:
        from .ziwei.selection import detect_aspect
        aspect, _kw = detect_aspect(question)
        zhan = ASPECT_ZHAN.get(aspect)
    return zhan or DEFAULT_ZHAN


#: 体用总诀所附之起例（五行、互卦、卦气）与断辞之义
_TIYONG_CTX = ("meihua:1:bagong", "meihua:1:wuxing", "meihua:1:hugua",
               "meihua:1:guaqi:wang", "meihua:1:guaqi:shuai", XICI_DEF)


def select_meihua(kb: KnowledgeBase, ben_id: int, zhi_id: int, moving_pos: int,
                  tp=None, question=None, month=None) -> Selection:
    """month：农历月数（卦气旺衰用），None 则不论卦气。"""
    ti, yong = tiyong(kb, ben_id, moving_pos)
    side = "下" if moving_pos <= 3 else "上"
    zhan = _pick_zhan(tp, question)
    zhan_id = f"meihua:2:zhan:{zhan[0]}"
    if not kb.has(zhan_id):
        zhan_id = None
    if not kb.has("meihua:2:tiyong"):   # 缩减库：退回旧例，爻辞主断
        return Selection(
            rule=(f"依《梅花易数》体用之说：动爻在{side}卦，{yong}为用、{ti}为体；"
                  "动爻爻辞主断，体用取象入解读"),
            readings=[
                _yao(kb, ben_id, moving_pos, "动爻爻辞（主断）", True),
                _guaci(kb, ben_id, "本卦卦辞（参）", False, with_xu_za=True),
                _guaci(kb, zhi_id, "之卦卦辞（势）", False),
            ] + _shuogua_readings(kb, ti, yong))

    an = tiyong_rules.analyze(kb, kb.hexagram(ben_id)["binary"],
                              kb.hexagram(zhi_id)["binary"], moving_pos,
                              month=month, zhan_id=zhan_id)
    readings = [Reading(
        cite_id="meihua:2:tiyong",
        role=f"体用生克（主断）：{an.rel_yong}",
        primary=True, context_ids=[c for c in _TIYONG_CTX if kb.has(c)],
        excerpt=an.zongjue)]
    if zhan_id:
        readings.append(Reading(
            cite_id=zhan_id, role=f"所问占章（主断·梅花·{zhan[1]}）",
            primary=True, excerpt=an.zhan_clause or None))
    readings += [
        _yao(kb, ben_id, moving_pos, "动爻爻辞（参·易辞）", False),
        _guaci(kb, ben_id, "本卦卦辞（参）", False, with_xu_za=True),
        _guaci(kb, zhi_id, "之卦卦辞（势）", False),
    ] + _shuogua_readings(kb, ti, yong)
    notes = [f"体用生克：{an.summary()}"]
    if an.hu_note:
        notes.append(an.hu_note)
    return Selection(
        rule=(f"依《梅花易数》体用之说：动爻在{side}卦，{yong}为用、{ti}为体；"
              "体用生克主断（总诀明文），互变论事之中终，动爻爻辞为参，"
              "体用取象入解读"),
        readings=readings, tiyong=an, notes=notes)


def select_zhuzi(kb: KnowledgeBase, ben_id: int, zhi_id: int, moving: list) -> Selection:
    """朱熹《易学启蒙》占法。moving 为动爻位置列表（自下而上，升序）。"""
    rule = "依朱熹《易学启蒙》占法"
    m = len(moving)
    if m == 0:
        readings = [_guaci(kb, ben_id, "本卦卦辞（主断）", True)]
    elif m == 1:
        readings = [
            _yao(kb, ben_id, moving[0], "本卦变爻爻辞（主断）", True),
            _guaci(kb, ben_id, "本卦卦辞（参）", False),
        ]
    elif m == 2:
        lower, upper = sorted(moving)
        readings = [
            _yao(kb, ben_id, upper, "本卦上变爻爻辞（主断）", True),
            _yao(kb, ben_id, lower, "本卦下变爻爻辞（参）", False),
        ]
    elif m == 3:
        readings = [
            _guaci(kb, ben_id, "本卦卦辞（贞，主断）", True),
            _guaci(kb, zhi_id, "之卦卦辞（悔，合参）", False),
        ]
    elif m == 4:
        unchanged = sorted(set(range(1, 7)) - set(moving))
        lower, upper = unchanged
        readings = [
            _yao(kb, zhi_id, lower, "之卦下不变爻爻辞（主断）", True),
            _yao(kb, zhi_id, upper, "之卦上不变爻爻辞（参）", False),
        ]
    elif m == 5:
        (unchanged,) = sorted(set(range(1, 7)) - set(moving))
        readings = [_yao(kb, zhi_id, unchanged, "之卦不变爻爻辞（主断）", True)]
    elif m == 6:
        if ben_id in (1, 2):
            name = "用九" if ben_id == 1 else "用六"
            readings = [
                _extra(kb, ben_id, f"{name}（主断）", True),
                _guaci(kb, zhi_id, "之卦卦辞（参）", False),
            ]
        else:
            readings = [
                _guaci(kb, zhi_id, "之卦卦辞（主断）", True),
                _guaci(kb, ben_id, "本卦卦辞（参）", False),
            ]
    else:
        raise ValueError(f"动爻数异常: {m}")
    if kb.has(XICI_DEF):   # 断辞之义（系辞）随主断经文附入，可引
        readings[0].context_ids.append(XICI_DEF)
    return Selection(rule=rule, readings=readings)


def select(kb: KnowledgeBase, method: str, ben_id: int, zhi_id: int,
           moving: list, tp=None, question=None, month=None) -> Selection:
    """tp、question 与 month 只在梅花法下起作用（占章附取、卦气），
    不影响朱子占法选文。"""
    if method in ("meihua_time", "meihua_zi", "meihua_wenyu"):
        assert len(moving) == 1, "梅花起卦应恰有一个动爻"
        return select_meihua(kb, ben_id, zhi_id, moving[0], tp, question,
                             month=month)
    return select_zhuzi(kb, ben_id, zhi_id, moving)
