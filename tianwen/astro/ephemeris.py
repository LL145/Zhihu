"""七曜星历：地心视黄经（date 黄道，真春分），运行时零依赖。

西洋占星本命盘（ALGORITHM.md 步骤 5b）只需七曜（日、月、水、金、火、
木、土——托勒密《占星四书》所论诸曜）落于黄道十二宫（tropical）之位，
故本模块只算地心视黄经，不算赤道坐标与宫位（上升与宫位须出生地，
输入无出生地，缓用）。

数据与算法（凭证所引，逐项可核）：

- 行星与地球：VSOP87D 周期项（Bretagnon & Francou 1988，IMCCE 公开
  科学数据），经 tools/import_ephemeris_tables.py 自 PyMeeus 转录并按
  振幅阈值截断入 data/ephemeris.json（meta 记截断规则与对照全表实测
  最大误差）；求值 L/B/R = Σ_k t^k Σ_i A·cos(B+C·t)，t 为儒略千年数。
- 月亮：Meeus《Astronomical Algorithms》第 47 章周期项表（ELP-2000
  之截断，同经导入脚本转录），含 A1/A2 金星木星摄动附加项与地球
  偏心率订正因子 E。
- 地心化：行星取光行时迭代，观测者与行星同取 t−τ 时刻位置（一阶
  含光行差之通行近似）；太阳同一通道（视作原点天体）。
- 章动：IAU 1980 主四项（Δψ = −17.20″sinΩ − 1.32″sin2L☉
  − 0.23″sin2L′ + 0.21″sin2Ω），加于黄经得真春分坐标。
- ΔT（TT−UT）：历年实测值十年点线性内插（表内注明，界外取端值）；
  其数秒之不确定仅影响月亮角秒级，凭证如实标注为约定。

同输入必同输出：全程查表与初等函数，无随机数。
"""

import json
import math
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "ephemeris.json"

#: 七曜（托勒密次序：日月与五星；数据键）
BODIES = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn")

#: ΔT = TT − UT（秒）：十年点，线性内插，界外取端值（约定；
#: 来源：天文年历历年实测值之整并，取整至 0.1s）
_DELTA_T = [
    (1900, -2.8), (1910, 10.4), (1920, 21.2), (1930, 24.0), (1940, 24.3),
    (1950, 29.1), (1960, 33.1), (1970, 40.2), (1980, 50.5), (1990, 56.9),
    (2000, 63.8), (2010, 66.1), (2020, 69.4), (2030, 72.0),
]

_LIGHT_TIME = 0.0057755183   # 光行时（日／天文单位，Meeus 33）


def _load():
    d = json.loads(DATA_PATH.read_text("utf-8"))
    return d


_data = None


def tables():
    global _data
    if _data is None:
        _data = _load()
    return _data


def delta_t(year):
    """ΔT（秒）。十年点线性内插，界外取端值。"""
    pts = _DELTA_T
    if year <= pts[0][0]:
        return pts[0][1]
    if year >= pts[-1][0]:
        return pts[-1][1]
    for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
        if y0 <= year <= y1:
            return v0 + (v1 - v0) * (year - y0) / (y1 - y0)
    raise AssertionError


def julian_day(dt_utc):
    """公历 UTC → 儒略日（UT）。标准历算（Meeus 7），无夏令时之虑。"""
    y, m = dt_utc.year, dt_utc.month
    d = (dt_utc.day + dt_utc.hour / 24 + dt_utc.minute / 1440
         + dt_utc.second / 86400)
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) \
        + d + b - 1524.5


def _vsop(body, t):
    """VSOP87D 截断表求值 → (L, B, R)（弧度、弧度、AU；date 黄道）。

    t 为儒略千年数（TT）。表项 [A, B, C] 单位 1e-8（rad / AU）。
    """
    v = tables()["vsop87"][body]
    out = []
    for key in ("L", "B", "R"):
        total, tn = 0.0, 1.0
        for series in v[key]:
            total += tn * sum(a * math.cos(b + c * t) for a, b, c in series)
            tn *= t
        out.append(total * 1e-8)
    L, B, R = out
    return L % (2 * math.pi), B, R


def _rect(body, t):
    L, B, R = _vsop(body, t)
    cb = math.cos(B)
    return (R * cb * math.cos(L), R * cb * math.sin(L), R * math.sin(B))


def _nutation_lon(tc):
    """章动 Δψ（度）。IAU 1980 主四项；tc 为儒略世纪数（TT）。"""
    rad = math.radians
    omega = 125.04452 - 1934.136261 * tc
    lsun = 280.4665 + 36000.7698 * tc
    lmoon = 218.3165 + 481267.8813 * tc
    dpsi = (-17.20 * math.sin(rad(omega)) - 1.32 * math.sin(rad(2 * lsun))
            - 0.23 * math.sin(rad(2 * lmoon)) + 0.21 * math.sin(rad(2 * omega)))
    return dpsi / 3600.0


def moon_longitude_mean(tc):
    """月亮地心黄经（度，date 平春分，未加章动）。Meeus 47。"""
    d = tables()["moon"]
    deg = math.radians
    lp = (218.3164477 + 481267.88123421 * tc - 0.0015786 * tc ** 2
          + tc ** 3 / 538841 - tc ** 4 / 65194000)
    dd = (297.8501921 + 445267.1114034 * tc - 0.0018819 * tc ** 2
          + tc ** 3 / 545868 - tc ** 4 / 113065000)
    m = (357.5291092 + 35999.0502909 * tc - 0.0001536 * tc ** 2
         + tc ** 3 / 24490000)
    mp = (134.9633964 + 477198.8675055 * tc + 0.0087414 * tc ** 2
          + tc ** 3 / 69699 - tc ** 4 / 14712000)
    f = (93.2720950 + 483202.0175233 * tc - 0.0036539 * tc ** 2
         - tc ** 3 / 3526000 + tc ** 4 / 863310000)
    e = 1 - 0.002516 * tc - 0.0000074 * tc ** 2
    a1 = 119.75 + 131.849 * tc
    a2 = 53.09 + 479264.290 * tc
    sl = 0.0
    for md, mm, mmp, mf, coeff in d["l"]:
        term = coeff * math.sin(deg(md * dd + mm * m + mmp * mp + mf * f))
        if abs(mm) == 1:
            term *= e
        elif abs(mm) == 2:
            term *= e * e
        sl += term
    sl += 3958 * math.sin(deg(a1)) + 1962 * math.sin(deg(lp - f)) \
        + 318 * math.sin(deg(a2))
    return (lp + sl / 1e6) % 360.0


def _planet_apparent(body, t):
    """行星／太阳地心视黄经（度，date 平春分；含光行时与光行差近似）。

    观测者（地球）与目标同取 t−τ 时刻位置，迭代两轮（Meeus 33 之
    一阶近似）；太阳视作原点天体走同一通道。t 为儒略千年数（TT）。
    """
    tau = 0.0
    for _ in range(2):
        t2 = t - tau / 365250.0
        xe, ye, ze = _rect("earth", t2)
        if body == "sun":
            x, y, z = -xe, -ye, -ze
        else:
            xp, yp, zp = _rect(body, t2)
            x, y, z = xp - xe, yp - ye, zp - ze
        dist = math.sqrt(x * x + y * y + z * z)
        tau = _LIGHT_TIME * dist
    return math.degrees(math.atan2(y, x)) % 360.0


def apparent_longitudes(dt_utc):
    """UTC 时刻 → {天体: 地心视黄经（度，date 黄道真春分）}，并附
    时间折算明细（凭证用）：{"jd_ut", "delta_t", "jde", "nutation"}。
    """
    jd = julian_day(dt_utc)
    dt_s = delta_t(dt_utc.year + (dt_utc.month - 0.5) / 12)
    jde = jd + dt_s / 86400.0
    t = (jde - 2451545.0) / 365250.0     # 儒略千年（TT）
    tc = t * 10.0                        # 儒略世纪（TT）
    dpsi = _nutation_lon(tc)
    lons = {}
    for body in BODIES:
        if body == "moon":
            lam = moon_longitude_mean(tc)
        else:
            lam = _planet_apparent(body, t)
        lons[body] = (lam + dpsi) % 360.0
    return lons, {"jd_ut": jd, "delta_t": dt_s, "jde": jde,
                  "nutation": dpsi}
