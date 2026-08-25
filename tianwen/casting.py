"""起卦引擎（确定性代码）。

- 梅花易数·时间起卦：完全确定，无随机数。规则出自《梅花易数》卷一：
  上卦 =（年支数+月+日）除以八之余，下卦 =（年支数+月+日+时）除以八之余，
  动爻 =（年支数+月+日+时）除以六之余；余零取八/六。数配先天八卦。
- 梅花易数·字占：以所占之字（如姓名）的笔画起卦，与时刻无关。规则出自
  《梅花易数》卷一「一字占至十一字占」（二字两仪平分、三字一上二下），
  占例见「西林寺牌额占」（系字画占例）。
- 梅花易数·问语起卦（事类主断，v3.5）：书写来意，以其字占之（卷一
  「为人占」）。二三字依字画（同姓名卦法）；四字以上「字数分之」——
  少一半为上卦、多一半为下卦（均平对半），各以字数配先天八卦（「听其
  语声……即如其字数分之起卦」；「十一字以上……止用字数」）；动爻＝
  （总数＋时辰数）除六（「爻以六除」末句「取爻当以时加之」，时辰由此
  入卦）。四至十字书例之平仄声调法（古四声含入声）无四声底本不可机断，
  一律字数分之，如实标注。
- 铜钱法·六爻（留存，不入单一模式，ALGORITHM.md 七）：《卜筮正宗》
  明说掷真钱，以伪随机数代掷非古籍明说，故待能接收用户真实掷象输入
  时启用。cast_coin 的种子法（SHA-256(问题|时刻|盐)，三背老阳9、
  三字老阴6、一背二字少阳7、二背一字少阴8）保留为将来对照。
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime

from . import hexagrams, lunar, strokes
from .trigrams import BY_NUM, TRIGRAMS


@dataclass
class CastResult:
    method: str                 # "meihua_time" | "meihua_zi" | "coin"
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


def _one_moving_lines(upper: str, lower: str, moving: int) -> list:
    """上下卦名 + 动爻位 → 六爻爻值（梅花法恒一动爻）。"""
    binary = list(TRIGRAMS[lower]["lines"]) + list(TRIGRAMS[upper]["lines"])
    lines = []
    for pos, b in enumerate(binary, start=1):
        if pos == moving:
            lines.append(9 if b == 1 else 6)
        else:
            lines.append(7 if b == 1 else 8)
    return lines


def cast_meihua(dt: datetime) -> CastResult:
    lm = lunar.from_datetime(dt)
    s_upper = lm.year_zhi_num + lm.month_num + lm.day_num
    s_lower = s_upper + lm.shichen_num
    upper_num = s_upper % 8 or 8
    lower_num = s_lower % 8 or 8
    moving = s_lower % 6 or 6
    upper, lower = BY_NUM[upper_num], BY_NUM[lower_num]
    lines = _one_moving_lines(upper, lower, moving)
    repro = {
        "起卦法": "梅花易数·时间起卦（依《梅花易数》卷一）",
        "公历时刻": dt.strftime("%Y-%m-%d %H:%M") + "（北京时间）",
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


def cast_zi(chars: str) -> CastResult:
    """字占·以字画起卦（《梅花易数》卷一「一字占至十一字占」）。

    二字为两仪平分：一字为上卦，一字为下卦；三字为三才：一字为上卦，
    二字为下卦。各取总笔画配先天八卦数，总画数除六取动爻——悉从
    「西林寺牌额占」例（系字画占例），不加时数，纯由所占之字确定。
    一字须辨字形左右阴阳画、四至十字改以平仄声音取数（古四声），
    皆非笔画表所能机断，故如实拒之，不另造新法。
    """
    chars = "".join((chars or "").split())
    if not chars:
        raise ValueError("字占需提供所占之字（两字或三字，如姓名）")
    n = len(chars)
    if n == 1:
        raise ValueError(
            "一字占须辨字形左右阴阳画（「以左为阳画，右为阴画」），"
            "本引擎无字形数据，暂不受理；请以两三字起之（如姓名），或改用铜钱法")
    if n > 3:
        raise ValueError(
            "四字以上古法不数画数、改以平仄声音取数（「只以平仄声音调之」），"
            "需古四声之学，本引擎暂未收录；请取两三字（如姓名），或改用铜钱法")
    counts = []
    for ch in chars:
        c = strokes.total_strokes(ch)
        if c is None:
            raise ValueError(f"「{ch}」不在笔画表内（Unihan kTotalStrokes，"
                             "覆盖 CJK 基本区与扩展A区）；字占仅受理汉字")
        counts.append(c)
    if n == 2:
        s_upper, s_lower = counts
        fen = "二字为两仪平分：一字为上卦，一字为下卦"
        upper_expr = f"{chars[0]}{counts[0]}画"
        lower_expr = f"{chars[1]}{counts[1]}画"
    else:
        s_upper, s_lower = counts[0], counts[1] + counts[2]
        fen = "三字为三才：一字为上卦，二字为下卦"
        upper_expr = f"{chars[0]}{counts[0]}画"
        lower_expr = (f"{chars[1]}{counts[1]}画+{chars[2]}{counts[2]}画"
                      f"={s_lower}画")
    total = sum(counts)
    upper_num = s_upper % 8 or 8
    lower_num = s_lower % 8 or 8
    moving = total % 6 or 6
    upper, lower = BY_NUM[upper_num], BY_NUM[lower_num]
    lines = _one_moving_lines(upper, lower, moving)
    sm = strokes.meta()
    repro = {
        "起卦法": "梅花易数·字占（以字画起卦，依《梅花易数》卷一"
                  "「一字占至十一字占」；占例「西林寺牌额占」）",
        "所占之字": f"「{chars}」（{fen}）",
        "笔画": "；".join(f"{ch}={c}画" for ch, c in zip(chars, counts))
                + f"（依 {sm['source']}，Unicode {sm['unicode_version']}）",
        "算式": (f"上卦={upper_expr}，{s_upper}%8={upper_num}→{upper}；"
                 f"下卦={lower_expr}，{s_lower}%8={lower_num}→{lower}；"
                 f"动爻=总{total}画%6={moving}"),
        "约定": "笔画依 Unihan 现代通行画数，古籍计画偶异（西林寺占记"
                "「西」七画，今作六画）；动爻不加时数，从「西林寺牌额占」例"
                "（「爻以六除」章“取爻当以时加之”之异说不取）；"
                "起卦纯由所占之字确定，与提问时刻无关",
        "复现方式": "任何人以同一字、同版笔画表依上式复算，结果必同",
    }
    return CastResult(method="meihua_zi", lines=lines, reproducibility=repro)


def _is_hanzi(ch: str) -> bool:
    """汉字判定（CJK 基本区＋扩展A区）：问语「只数汉字」，标点、字母、
    数字非字不入数。"""
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def cast_wenyu(question: str, dt: datetime) -> CastResult:
    """问语起卦（书写来意，以其字占之；《梅花易数》卷一「为人占」）。

    二三字依字画起（两仪平分／三才，同姓名卦法）；四字以上「字数分之」：
    少一半为上卦、多一半为下卦（均平对半），各以字数配先天八卦。动爻＝
    （总数＋时辰数）除六——「取爻当以时加之」（爻以六除），时辰由此入卦，
    与姓名卦不加时有别（姓名所占者字，非时事）。四至十字书例之平仄声调法
    需古四声，无底本不可机断，一律字数分之，凭证如实标注。
    问语无汉字可数或仅一字（一字占须辨字形阴阳画）则抛 ValueError，
    调用方回落时间卦并声明。
    """
    hanzi = "".join(ch for ch in (question or "") if _is_hanzi(ch))
    n = len(hanzi)
    if n == 0:
        raise ValueError("问语无汉字可数（只数汉字，标点、字母、数字不入数）")
    if n == 1:
        raise ValueError("问语仅一字：一字占须辨字形左右阴阳画，无字形数据不可机断")
    lm = lunar.from_datetime(dt)
    shi = lm.shichen_num
    if n <= 3:
        counts = []
        for ch in hanzi:
            c = strokes.total_strokes(ch)
            if c is None:
                raise ValueError(f"「{ch}」不在笔画表内，二三字问语依字画起卦不可缺")
            counts.append(c)
        if n == 2:
            s_upper, s_lower = counts
            fen = "二字为两仪平分：一字为上卦，一字为下卦"
        else:
            s_upper, s_lower = counts[0], counts[1] + counts[2]
            fen = "三字为三才：一字为上卦，二字为下卦"
        total = sum(counts)
        qushu = ("；".join(f"{ch}={c}画" for ch, c in zip(hanzi, counts))
                 + f"（{fen}，字画起）")
        suanshi = (f"上卦={s_upper}画%8；下卦={s_lower}画%8；"
                   f"动爻=(总{total}画+时{lm.shichen_zhi}{shi})%6")
    else:
        s_upper, s_lower = n // 2, n - n // 2
        total = n
        fen = ("字数均平，对半分之" if n % 2 == 0
               else "字数不匀，少一半为上卦（取天轻清之义）")
        qushu = f"汉字 {n} 字（{fen}）：前{s_upper}字为上卦，后{s_lower}字为下卦"
        suanshi = (f"上卦={s_upper}%8；下卦={s_lower}%8；"
                   f"动爻=(总{total}+时{lm.shichen_zhi}{shi})%6")
    upper_num = s_upper % 8 or 8
    lower_num = s_lower % 8 or 8
    moving = (total + shi) % 6 or 6
    upper, lower = BY_NUM[upper_num], BY_NUM[lower_num]
    lines = _one_moving_lines(upper, lower, moving)
    repro = {
        "起卦法": "梅花易数·问语起卦（书写来意，以其字占之；《梅花易数》"
                  "卷一「为人占」，分法依「一字占至十一字占」「字占」）",
        "公历时刻": dt.strftime("%Y-%m-%d %H:%M") + "（北京时间）",
        "农历": lm.description,
        "所问之语": f"「{hanzi}」" + ("" if hanzi == "".join((question or "").split())
                                     else "（只数汉字，标点、字母、数字不入数）"),
        "取数": qushu,
        "算式": suanshi + f"：上卦{upper_num}→{upper}；下卦{lower_num}→{lower}；"
                          f"动爻{moving}",
        "约定": "四至十字书例用平仄声调取数（古四声含入声），无四声底本"
                "不可机断，一律以字数分之（同「听其语声……即如其字数分之」例）；"
                "动爻加时数从「爻以六除」末句「取爻当以时加之」通例"
                "（姓名卦不加时，从西林寺牌额占例）；"
                + "；".join(lm.convention_notes),
        "复现方式": "任何人以同一问语、同一时辰依上式复算，结果必同",
    }
    return CastResult(method="meihua_wenyu", lines=lines, reproducibility=repro)


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
        "公历时刻": dt.isoformat() + "（北京时间）",
        "种子算法": "SHA-256(问题文本|时刻ISO格式|盐)",
        "种子": seed_hex,
        "六掷（自下而上）": "；".join(tosses),
        "复现方式": "以同一种子驱动同一伪随机算法（Python random.Random）复掷必同",
    }
    return CastResult(method="coin", lines=lines, reproducibility=repro)
