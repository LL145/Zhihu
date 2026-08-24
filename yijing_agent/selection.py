"""断卦规则引擎：依占法规则确定应读的经文（确定性代码，杜绝挑拣）。

- 铜钱法（可有 0-6 个动爻）：依朱熹《易学启蒙》占法（DESIGN.md 附录A）。
- 梅花易数（恒为一个动爻）：依《梅花易数》体用之说——本卦卦辞为体、
  动爻爻辞为断、之卦卦辞为势；以动爻爻辞为主断。
"""

from dataclasses import dataclass, field

from .knowledge import KnowledgeBase


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


def select_meihua(kb: KnowledgeBase, ben_id: int, zhi_id: int, moving_pos: int) -> Selection:
    return Selection(
        rule="依《梅花易数》体用之说：本卦为体，动爻为断，之卦为势",
        readings=[
            _yao(kb, ben_id, moving_pos, "动爻爻辞（主断）", True),
            _guaci(kb, ben_id, "本卦卦辞（体）", False),
            _guaci(kb, zhi_id, "之卦卦辞（势）", False),
        ],
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


def select(kb: KnowledgeBase, method: str, ben_id: int, zhi_id: int, moving: list) -> Selection:
    if method == "meihua_time":
        assert len(moving) == 1, "梅花时间起卦应恰有一个动爻"
        return select_meihua(kb, ben_id, zhi_id, moving[0])
    return select_zhuzi(kb, ben_id, zhi_id, moving)
