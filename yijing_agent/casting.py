"""起卦引擎（确定性代码）。

- 梅花易数·时间起卦：完全确定，无随机数。规则出自《梅花易数》卷一：
  上卦 =（年支数+月+日）除以八之余，下卦 =（年支数+月+日+时）除以八之余，
  动爻 =（年支数+月+日+时）除以六之余；余零取八/六。数配先天八卦。
- 铜钱法·六爻：种子 = SHA-256(问题|时刻|盐)，掷六次、每次三枚。
  三背为老阳9、三字为老阴6、一背二字为少阳7、二背一字为少阴8
  （背记 3、字记 2，合计即爻值，依《卜筮正宗》）。
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime

from . import hexagrams, lunar
from .trigrams import BY_NUM, TRIGRAMS


@dataclass
class CastResult:
    method: str                 # "meihua_time" | "coin"
    lines: list                 # 六爻爻值 6/7/8/9，自下而上
    reproducibility: dict = field(default_factory=dict)

    @property
    def ben_binary(self):
        return hexagrams.lines_to_binary(self.lines)

    @property
    def moving(self):
        return hexagrams.moving_positions(self.lines)

    @property
    def zhi_binary(self):
        return hexagrams.zhi_binary(self.lines)

    @property
    def hu_binary(self):
        return hexagrams.hu_binary(self.ben_binary)


def cast_meihua(dt: datetime) -> CastResult:
    lm = lunar.from_datetime(dt)
    s_upper = lm.year_zhi_num + lm.month_num + lm.day_num
    s_lower = s_upper + lm.shichen_num
    upper_num = s_upper % 8 or 8
    lower_num = s_lower % 8 or 8
    moving = s_lower % 6 or 6
    upper, lower = BY_NUM[upper_num], BY_NUM[lower_num]
    binary = list(TRIGRAMS[lower]["lines"]) + list(TRIGRAMS[upper]["lines"])
    lines = []
    for pos, b in enumerate(binary, start=1):
        if pos == moving:
            lines.append(9 if b == 1 else 6)
        else:
            lines.append(7 if b == 1 else 8)
    repro = {
        "起卦法": "梅花易数·时间起卦（依《梅花易数》卷一）",
        "公历时刻": dt.strftime("%Y-%m-%d %H:%M"),
        "农历": lm.description,
        "取数": (f"年支{lm.year_gz[1]}={lm.year_zhi_num}，月={lm.month_num}，"
                 f"日={lm.day_num}，时{lm.shichen_zhi}={lm.shichen_num}"),
        "算式": (f"上卦=({lm.year_zhi_num}+{lm.month_num}+{lm.day_num})%8"
                 f"={upper_num}→{upper}；"
                 f"下卦=({lm.year_zhi_num}+{lm.month_num}+{lm.day_num}+{lm.shichen_num})%8"
                 f"={lower_num}→{lower}；"
                 f"动爻={s_lower}%6={moving}"),
        "约定": "；".join(lm.convention_notes),
        "复现方式": "任何人以同一公历时刻依上式复算，结果必同",
    }
    return CastResult(method="meihua_time", lines=lines, reproducibility=repro)


def cast_coin(question: str, dt: datetime, salt: str = "") -> CastResult:
    material = f"{question}|{dt.isoformat()}|{salt}"
    seed_hex = hashlib.sha256(material.encode("utf-8")).hexdigest()
    rng = random.Random(int(seed_hex, 16))
    lines, tosses = [], []
    for _ in range(6):
        coins = [rng.randint(0, 1) for _ in range(3)]  # 1 背（记3）、0 字（记2）
        value = sum(3 if c else 2 for c in coins)
        lines.append(value)
        tosses.append("".join("背" if c else "字" for c in coins) + f"={value}")
    repro = {
        "起卦法": "铜钱法·六爻（依《卜筮正宗》三背老阳、三字老阴之法）",
        "公历时刻": dt.isoformat(),
        "种子算法": "SHA-256(问题文本|时刻ISO格式|盐)",
        "种子": seed_hex,
        "六掷（自下而上）": "；".join(tosses),
        "复现方式": "以同一种子驱动同一伪随机算法（Python random.Random）复掷必同",
    }
    return CastResult(method="coin", lines=lines, reproducibility=repro)
