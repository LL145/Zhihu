"""断卦规则引擎：依占法规则确定应读的经文（确定性代码，杜绝挑拣）。

- 梅花易数（恒为一个动爻）：依《梅花易数》体用之说——动爻所在之卦为用、
  不动之卦为体；动爻爻辞为主断，本卦、之卦卦辞为参，体用两卦取象
  （《说卦传》广象）入解读。
- 朱熹《易学启蒙》占法（select_zhuzi，0-6 个动爻）：为铜钱法/大衍法
  留存（ALGORITHM.md 七）——单一模式今用梅花，待可输入真实掷象时启用。
"""

from dataclasses import dataclass, field

from .knowledge import KnowledgeBase
from .trigrams import PINYIN


@dataclass
class Reading:
    cite_id: str
    role: str            # 如「主断」「本卦卦辞（参）」
    primary: bool
    context_ids: list = field(default_factory=list)  # 所附传文（彖/象）


@dataclass
class Selection:
    rule: str            # 占法标注
    readings: list       # [Reading]，首个 primary 为主断依据

    @property
    def primary(self):
        return next(r for r in self.readings if r.primary)


def _guaci(kb, hid, role, primary):
    return Reading(
        cite_id=f"zhouyi:{hid}:guaci", role=role, primary=primary,
        context_ids=[f"tuan:{hid}", f"daxiang:{hid}"],
    )


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
    """体用两卦之广象（说卦第十一章）；性情章附于体卦下。缺库则不附。"""
    readings = []
    for name, role_prefix in ((ti, "体卦"), (yong, "用卦")):
        cid = f"shuogua:11:{PINYIN[name]}"
        if not kb.has(cid):
            return []
        ctx = ["shuogua:7"] if role_prefix == "体卦" and kb.has("shuogua:7") else []
        readings.append(Reading(
            cite_id=cid, role=f"{role_prefix}{name}取象（说卦·广象，入解读）",
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


def _pick_zhan(tp, question):
    """占章取法：类别映射优先，未中则按题材关键词回落（同一张分宫表）。"""
    zhan = TOPIC_ZHAN.get(tp.key) if tp is not None else None
    if zhan is None and question:
        from .ziwei.selection import detect_aspect
        aspect, _kw = detect_aspect(question)
        zhan = ASPECT_ZHAN.get(aspect)
    return zhan


def _meihua_jue_readings(kb, tp, question=None):
    """体用总诀恒附；所问有对应占章则并附。缺库则不附。"""
    readings = []
    if kb.has("meihua:2:tiyong"):
        readings.append(Reading(cite_id="meihua:2:tiyong",
                                role="体用总诀（梅花断法之纲）", primary=False))
    zhan = _pick_zhan(tp, question)
    if zhan and kb.has(f"meihua:2:zhan:{zhan[0]}"):
        readings.append(Reading(cite_id=f"meihua:2:zhan:{zhan[0]}",
                                role=f"所问类占诀（梅花·{zhan[1]}）", primary=False))
    return readings


def select_meihua(kb: KnowledgeBase, ben_id: int, zhi_id: int, moving_pos: int,
                  tp=None, question=None) -> Selection:
    ti, yong = tiyong(kb, ben_id, moving_pos)
    return Selection(
        rule=(f"依《梅花易数》体用之说：动爻在{'下' if moving_pos <= 3 else '上'}卦，"
              f"{yong}为用、{ti}为体；动爻爻辞主断，体用取象入解读"),
        readings=[
            _yao(kb, ben_id, moving_pos, "动爻爻辞（主断）", True),
            _guaci(kb, ben_id, "本卦卦辞（参）", False),
            _guaci(kb, zhi_id, "之卦卦辞（势）", False),
        ] + _shuogua_readings(kb, ti, yong)
          + _meihua_jue_readings(kb, tp, question),
    )


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
    return Selection(rule=rule, readings=readings)


def select(kb: KnowledgeBase, method: str, ben_id: int, zhi_id: int,
           moving: list, tp=None, question=None) -> Selection:
    """tp 与 question 只在梅花法下决定占章附取，不影响朱子占法选文。"""
    if method in ("meihua_time", "meihua_zi", "meihua_wenyu"):
        assert len(moving) == 1, "梅花起卦应恰有一个动爻"
        return select_meihua(kb, ben_id, zhi_id, moving[0], tp, question)
    return select_zhuzi(kb, ben_id, zhi_id, moving)
