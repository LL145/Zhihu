"""西洋占星本命盘（第一期）：七曜落宫、本位／擢升／降卑、按宫相位。

典据（判定表逐条转录，原文见 data/tetrabiblos.json）：

- 落宫：黄道十二宫（tropical，白羊起于春分点）——托勒密论宫界以
  回归点定（tetra:1:12 论四季诸宫、1:14），落宫＝⌊视黄经/30°⌋；
- 本位（houses）：tetra:1:20——日狮子、月巨蟹、土摩羯宝瓶、
  木人马双鱼、火白羊天蝎、金金牛天秤、水双子室女；
- 擢升／降卑（exaltation/fall）：tetra:1:22——日白羊／天秤、
  月金牛／天蝎、木巨蟹／摩羯、火摩羯／巨蟹、金双鱼／室女、
  水室女／双鱼、土天秤／白羊（逐星原文明说，降卑即其对宫）；
- 相位（configurations）：tetra:1:16——按宫距：对分（六宫之距，
  180°）、三分（四宫，120°）、四分（三宫，90°）、六分（二宫，60°）；
  三分六分为和（harmonious）、对分四分为不和（discordant），
  皆原文明说。同宫并列非 1:16 所论之相位，只如实列出（约定标注）。

今法约定（凭证如实标注）：出生时辰只到时辰，取时辰中点起算
（月亮时辰内约行 1°，两端黄经列入凭证，跨宫则落宫存疑如实标注）；
生辰按北京时间折 UTC（同紫微排盘之约定）；无出生地输入，故不算
上升与宫位分府（启用条件：出生地输入，见 ALGORITHM.md 七）。
盘由生辰确定、无随机数，同输入必同输出。
"""

from collections import namedtuple
from datetime import datetime, timedelta

from ..trigrams import ZHI
from . import ephemeris

#: 黄道十二宫（白羊起；通行汉译名）
SIGNS = ("白羊", "金牛", "双子", "巨蟹", "狮子", "室女",
         "天秤", "天蝎", "人马", "摩羯", "宝瓶", "双鱼")

#: 七曜（托勒密次序）：数据键 → 汉名
PLANET_NAMES = {"sun": "太阳", "moon": "月亮", "mercury": "水星",
                "venus": "金星", "mars": "火星", "jupiter": "木星",
                "saturn": "土星"}

#: 本位（tetra:1:20）；宫序 0=白羊
DOMICILE = {"sun": (4,), "moon": (3,), "mercury": (2, 5), "venus": (1, 6),
            "mars": (0, 7), "jupiter": (8, 11), "saturn": (9, 10)}

#: 擢升／降卑（tetra:1:22，降卑为擢升之对宫，逐星原文明说）
EXALTATION = {"sun": 0, "moon": 1, "mercury": 5, "venus": 11, "mars": 9,
              "jupiter": 3, "saturn": 6}
FALL = {k: (v + 6) % 12 for k, v in EXALTATION.items()}

#: 相位按宫距（tetra:1:16）：宫距 → (名, 和/不和)
_ASPECTS = {6: ("对分", "不和"), 4: ("三分", "和"), 8: ("三分", "和"),
            3: ("四分", "不和"), 9: ("四分", "不和"),
            2: ("六分", "和"), 10: ("六分", "和")}

Placement = namedtuple("Placement", "key name lon sign_idx deg")
NatalChart = namedtuple(
    "NatalChart", "birth_dt mid_beijing utc placements dignities aspects "
                  "same_sign moon_span moon_uncertain repro")


def sign_name(idx):
    return SIGNS[idx % 12] + "宫"


def _mid_shichen(birth_dt):
    """出生时辰（birth_dt.hour 所在时辰）→ 时辰中点时刻（北京时间）。

    时辰跨两小时（X 时正前后各一小时），中点即 X 时整；亥末之后的
    23 时属次日子时，中点为次日 0 时。
    """
    idx = ((birth_dt.hour + 1) // 2) % 12
    mid = birth_dt.replace(hour=2 * idx, minute=0, second=0, microsecond=0)
    if birth_dt.hour == 23:
        mid += timedelta(days=1)
    return mid, ZHI[idx]


def cast(birth_dt: datetime) -> NatalChart:
    """生辰（北京时间，时辰精度）→ 本命盘。确定性，同输入必同输出。"""
    mid, shichen = _mid_shichen(birth_dt)
    utc = mid - timedelta(hours=8)
    lons, tmeta = ephemeris.apparent_longitudes(utc)

    placements = []
    for key in ephemeris.BODIES:
        lon = lons[key]
        placements.append(Placement(key, PLANET_NAMES[key], lon,
                                    int(lon // 30) % 12, lon % 30))

    dignities = []
    for p in placements:
        if p.sign_idx in DOMICILE[p.key]:
            dignities.append((p.name, "本位", sign_name(p.sign_idx)))
        if EXALTATION[p.key] == p.sign_idx:
            dignities.append((p.name, "擢升", sign_name(p.sign_idx)))
        if FALL[p.key] == p.sign_idx:
            dignities.append((p.name, "降卑", sign_name(p.sign_idx)))

    aspects, same_sign = [], []
    for i, a in enumerate(placements):
        for b in placements[i + 1:]:
            d = (b.sign_idx - a.sign_idx) % 12
            if d == 0:
                same_sign.append((a.name, b.name, sign_name(a.sign_idx)))
            elif d in _ASPECTS:
                kind, harmony = _ASPECTS[d]
                aspects.append((a.name, b.name, kind, harmony))

    # 月亮时辰两端漂移（时辰中点 ±1 小时）；跨宫则落宫存疑
    lo = ephemeris.apparent_longitudes(utc - timedelta(hours=1))[0]["moon"]
    hi = ephemeris.apparent_longitudes(utc + timedelta(hours=1))[0]["moon"]
    moon = next(p for p in placements if p.key == "moon")
    moon_uncertain = not (int(lo // 30) % 12 == int(hi // 30) % 12
                          == moon.sign_idx)

    repro = {
        "排盘法": "西洋占星本命盘（第一期：七曜落宫、本位／擢升／降卑、"
                  "按宫相位；据托勒密《占星四书》，判定表逐条注于 natal.py）",
        "生辰": f"{birth_dt:%Y-%m-%d} {shichen}时（北京时间，时辰精度）",
        "时刻折算": (f"时辰中点 {mid:%Y-%m-%d %H:%M} 北京时间 → UTC −8h ＝ "
                     f"{utc:%Y-%m-%d %H:%M}；ΔT＝{tmeta['delta_t']:.1f}s"
                     f"（十年点内插约定）→ JDE {tmeta['jde']:.5f}"),
        "星历": ("VSOP87D 截断表＋Meeus 月表（data/ephemeris.json，来源与"
                 "对照全表实测误差见其 meta；黄经 date 黄道真春分，"
                 f"章动 {tmeta['nutation'] * 3600:+.1f}″已计）"),
        "七曜黄经": "；".join(
            f"{p.name} {p.lon:.2f}°→{sign_name(p.sign_idx)}{p.deg:.2f}°"
            for p in placements),
        "落宫算式": "宫序＝⌊视黄经/30°⌋，白羊宫起于春分点（tropical）",
        "月亮时辰漂移": (f"时辰两端黄经 {lo:.2f}°–{hi:.2f}°"
                         + ("；两端跨宫，落宫须精确时刻方定（如实存疑）"
                            if moon_uncertain else "；同宫，落宫不因时辰"
                            "精度而移")),
        "约定": ("时辰中点起算；北京时间折 UTC（同紫微排盘）；无出生地"
                 "输入，不算上升与宫位分府（启用条件：出生地输入）；"
                 "同宫并列如实列出，非 1:16 所论相位"),
    }
    return NatalChart(birth_dt, mid, utc, placements, dignities, aspects,
                      same_sign, (lo, hi), moon_uncertain, repro)


def facts_lines(chart: NatalChart):
    """盘面事实行（语境块 notes 用；纯盘面，无断语）。"""
    lines = ["七曜落宫：" + "；".join(
        f"{p.name}在{sign_name(p.sign_idx)}{p.deg:.1f}°"
        for p in chart.placements)]
    if chart.moon_uncertain:
        lines.append("月亮落宫存疑：出生时辰两端跨宫（凭证列两端黄经），"
                     "涉月亮落宫之文勿引")
    if chart.dignities:
        lines.append("得位（本位 houses／擢升 exaltation／降卑 fall）：" + "；".join(
            f"{name}{status}于{sign}" for name, status, sign in chart.dignities))
    else:
        lines.append("七曜皆不在本位／擢升／降卑之宫")
    if chart.aspects:
        lines.append("相位（按宫距，见 1:16）：" + "；".join(
            f"{a}与{b}{kind}（{harmony}）" for a, b, kind, harmony
            in chart.aspects))
    if chart.same_sign:
        lines.append("同宫并列（如实列出，非 1:16 所论相位）：" + "；".join(
            f"{a}与{b}同在{s}" for a, b, s in chart.same_sign))
    return lines


def render_repro(chart: NatalChart):
    out = ["── 本命盘凭证（西洋占星·可复现） " + "─" * 12]
    for k, v in chart.repro.items():
        out.append(f"  {k}：{v}")
    return "\n".join(out)


#: 恒附之总纲章：吉星凶星、相位、本位、擢升（盘面事实之所据）
BASE_CHAPTERS = ("1:5", "1:16", "1:20", "1:22")

#: 判类 → 论题章（卷三卷四论本命诸事；寿夭疾病生死诸章属红线主题，
#: 一律不入语境——藏书仍可检索）
TOPIC_CHAPTERS = {"destiny": ("3:18",),    # 心性（THE QUALITY OF THE MIND）
                  "fortune": ("4:10",)}    # 大限分期（PERIODICAL DIVISIONS）

#: 问事分宫（紫微 ASPECTS 之宫名）→ 论题章
ASPECT_CHAPTERS = {"妻妾": ("4:5",), "官禄": ("4:4",), "财帛": ("4:2",),
                   "子女": ("4:6",), "奴仆": ("4:7",), "兄弟": ("3:6",),
                   "父母": ("3:5",), "迁移": ("4:8",)}


def context_chapters(topic_key, aspect=None):
    """判类＋问事题材 → 附入语境的章 id 序列（恒附总纲＋论题章）。"""
    out = list(BASE_CHAPTERS)
    for cid in TOPIC_CHAPTERS.get(topic_key, ()):
        out.append(cid)
    if aspect:
        for cid in ASPECT_CHAPTERS.get(aspect, ()):
            if cid not in out:
                out.append(cid)
    return out
