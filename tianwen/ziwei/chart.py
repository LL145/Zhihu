"""紫微斗数排盘引擎（确定性纯函数，无随机成分）。

全部安星规则出自《紫微斗数全书·卷二》（中文维基文库《紫微斗數全書/卷二》，
oldid 1963110），每条函数注明所据之诀。同一生辰必得同一盘，任何通行
排盘工具可交叉核对（个别流派分歧处见下）。

本产品流派约定（见 DESIGN.md 附录C；结果页如实标注）：
- 年干支以农历正月初一为界（非立春），与事引擎一致；
- 晚子时（23:00–23:59）不换日，时辰作子，与事引擎一致；
- 闰月安命身依《全书·安身命例》「闰正月生者要在二月内起安身命」——
  闰月整月按下月起数（流行工具多以月中分界，此处从底本明文）；
- 大限首限起于命宫、起限之岁为五行局数（通行排法；《全书·安大限诀》
  「从命前一宫起」字面另有一读，此处从通行以便用户交叉核对）；
- 壬干四化依《全书》「壬梁紫府武」：天府化科（流行诀作左辅化科）；
- 辛干魁钺依《全书》「六辛逢虎马」：天魁在寅、天钺在午（流行诀互换）；
- 魁钺诀「丙丁猪狗位」依通行本订正为「猪鸡位」（天钺在酉），见
  data/PROOFREADING.md；
- 真太阳时不启用（不收出生地）。
"""

from dataclasses import dataclass, field
from datetime import datetime

import cnlunar

from ..trigrams import GAN, ZHI
from . import brightness

# ── 基础常量 ────────────────────────────────────────────────────────────

#: 《全书·安十二宫例》：一命宫、二兄弟、三妻妾、四子女、五财帛、六疾厄、
#: 七迁移、八奴仆、九官禄、十田宅、十一福德、十二父母（男女俱从逆转）。
PALACE_NAMES = ("命宫", "兄弟", "妻妾", "子女", "财帛", "疾厄",
                "迁移", "奴仆", "官禄", "田宅", "福德", "父母")

MAJOR_STARS = ("紫微", "天机", "太阳", "武曲", "天同", "廉贞",
               "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军")

_YIN = 2  # 寅在地支序（子0 丑1 寅2 …）

# 六十甲子纳音五行（《全书·卷二·六十花甲子纳音歌》，两柱一纳音，共三十；
# 甲子海中金…壬辰长流水 与 甲午沙中金…壬戌大海水 两半恰为同一序列）
_NAYIN = "金火木土金火水土金木水土火木水" * 2

_JU_NUM = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
_JU_NAME = {"水": "水二局", "木": "木三局", "金": "金四局",
            "土": "土五局", "火": "火六局"}

# ── 数据结构 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LunarBirth:
    lunar_year: int       # 农历年份（虚岁计算用）
    year_gan: str
    year_zhi: str
    month_num: int        # 农历月数（原始，闰月未调整）
    is_leap_month: bool
    day_num: int
    shichen_zhi: str      # 时辰地支
    description: str      # 人读版，如「农历庚辰年八月十七 午时」

    @property
    def year_gz(self):
        return self.year_gan + self.year_zhi


@dataclass(frozen=True)
class PalaceStar:
    name: str
    kind: str             # major / lucky / malefic
    brightness: str       # 庙/旺/得地/利益/平和/不得地/落陷；底本未载则空串
    sihua: str            # 禄/权/科/忌；无则空串


@dataclass
class Palace:
    name: str             # 《全书》宫名（妻妾/奴仆等古称）
    branch: str
    stem: str
    stars: list           # [PalaceStar]
    is_body: bool         # 身宫所在
    daxian: tuple         # (起岁, 止岁)

    @property
    def gz(self):
        return self.stem + self.branch

    def major(self):
        return [s for s in self.stars if s.kind == "major"]


@dataclass
class Chart:
    solar_desc: str
    lunar: LunarBirth
    gender: str           # 男 / 女
    yinyang: str          # 阳男 / 阴男 / 阳女 / 阴女
    ming_branch: str
    shen_branch: str
    wuxing_ju: str        # 如「土五局」
    ju_num: int
    daxian_forward: bool  # 大限顺行与否
    palaces: list = field(default_factory=list)   # 12 项，palaces[0] 为命宫
    sihua: dict = field(default_factory=dict)     # {"禄": 星名, …}
    conventions: list = field(default_factory=list)

    def palace_of_branch(self, branch):
        for p in self.palaces:
            if p.branch == branch:
                return p
        raise KeyError(branch)

    def palace_named(self, name):
        for p in self.palaces:
            if p.name == name:
                return p
        raise KeyError(name)

    def star_palace(self, star_name):
        for p in self.palaces:
            for s in p.stars:
                if s.name == star_name:
                    return p
        return None

    def xu_age(self, at: datetime) -> int:
        """at 时之虚岁（农历年份差 + 1；年界依正月初一约定）。"""
        return cnlunar.Lunar(at, godType="8char").lunarYear \
            - self.lunar.lunar_year + 1

    def current_daxian(self, at: datetime):
        """按虚岁定当前大限。"""
        age = self.xu_age(at)
        for p in self.palaces:
            lo, hi = p.daxian
            if lo <= age <= hi:
                return p, age
        return None, age

    def year_branch(self, at: datetime) -> str:
        """at 所在农历年之年支（太岁；年界依正月初一约定）。"""
        return ZHI[(cnlunar.Lunar(at, godType="8char").lunarYear - 4) % 12]

    def xiaoxian_branch(self, age: int) -> str:
        """小限所在宫支。《安小限诀》：不论阴阳男俱顺数、不论阴阳女俱
        逆数；寅午戌人起辰宫，申子辰人自戌宫，巳酉丑人起未宫，亥卯未人
        起丑宫——起宫当一岁，逐年一宫。"""
        start = _XIAOXIAN_START[self.lunar.year_zhi]
        step = age - 1 if self.gender == "男" else 1 - age
        return ZHI[(start + step) % 12]


# ── 农历换算（生辰用） ──────────────────────────────────────────────────

_CN_MONTH = {1: "正", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
             7: "七", 8: "八", 9: "九", 10: "十", 11: "冬", 12: "腊"}


def _cn_day(d):
    tens = ["初", "十", "廿", "三"]
    if d == 10:
        return "初十"
    if d == 20:
        return "二十"
    if d == 30:
        return "三十"
    return tens[d // 10] + "一二三四五六七八九"[d % 10 - 1]


def lunar_birth(dt: datetime) -> LunarBirth:
    """公历生辰 → 农历（年干支以正月初一为界；晚子时不换日）。"""
    a = cnlunar.Lunar(dt, godType="8char")
    gan = GAN[(a.lunarYear - 4) % 10]
    zhi = ZHI[(a.lunarYear - 4) % 12]
    shichen = ZHI[((dt.hour + 1) // 2) % 12]
    leap = bool(a.isLunarLeapMonth)
    desc = (f"农历{gan}{zhi}年{'闰' if leap else ''}"
            f"{_CN_MONTH[a.lunarMonth]}月{_cn_day(a.lunarDay)} {shichen}时")
    return LunarBirth(lunar_year=a.lunarYear, year_gan=gan, year_zhi=zhi,
                      month_num=a.lunarMonth, is_leap_month=leap,
                      day_num=a.lunarDay, shichen_zhi=shichen,
                      description=desc)


# ── 安星诸函数（每条注明《全书·卷二》所据之诀） ─────────────────────────


def _effective_month(lunar: LunarBirth) -> int:
    """安命身用月数。《安身命例》：「闰正月生者要在二月内起安身命，
    凡有闰月俱要依此为例」——闰月整月按下月起数。"""
    m = lunar.month_num + (1 if lunar.is_leap_month else 0)
    return 1 if m == 13 else m


def ming_shen(month: int, hz: int):
    """《安身命例》：寅上起正月顺数至生月，自生月起子时逆数至生时安命、
    顺数至生时安身。hz 为时辰序（子0…亥11）。返回（命宫支序, 身宫支序）。"""
    base = (_YIN + month - 1) % 12
    return (base - hz) % 12, (base + hz) % 12


def palace_stem(year_gan: str, branch_idx: int) -> str:
    """宫干。《起五行寅例》（五虎遁）：甲己之岁起丙寅，乙庚起戊寅，
    丙辛起庚寅，丁壬起壬寅，戊癸起甲寅；自寅顺行，子丑续排。"""
    start = (GAN.index(year_gan) % 5) * 2 + 2
    return GAN[(start + (branch_idx - _YIN) % 12) % 10]


def nayin_element(gan: str, zhi: str) -> str:
    """干支纳音五行（《六十花甲子纳音歌》）。"""
    idx60 = (GAN.index(gan) * 6 - ZHI.index(zhi) * 5) % 60
    return _NAYIN[idx60 // 2]


def wuxing_ju(ming_gan: str, ming_zhi: str):
    """五行局：命宫干支之纳音（《安身命例》「纳音甲子歌」）。"""
    e = nayin_element(ming_gan, ming_zhi)
    return _JU_NAME[e], _JU_NUM[e]


def ziwei_pos(ju: int, day: int) -> int:
    """安紫微。依局数除生日：商（不足进一）自寅顺行，借数偶则再顺行
    借数、奇则逆行借数（与《全书·卷二》各局起紫微表逐格一致，测试中
    抽查核对）。"""
    q, r = divmod(day, ju)
    if r:
        q += 1
    borrow = q * ju - day
    step = borrow if borrow % 2 == 0 else -borrow
    return (_YIN + q - 1 + step) % 12


def major_star_positions(zw: int) -> dict:
    """十四主星。《安南北斗诸星诀》：紫微天机逆行旁，隔一阳武天同当，
    又隔二位廉贞地；天府（与紫微对称于寅申轴）太阴与贪狼、巨门天相及
    天梁、七杀空三破军位，八星顺数。"""
    tf = (4 - zw) % 12
    pos = {"紫微": zw, "天机": zw - 1, "太阳": zw - 3, "武曲": zw - 4,
           "天同": zw - 5, "廉贞": zw - 8,
           "天府": tf, "太阴": tf + 1, "贪狼": tf + 2, "巨门": tf + 3,
           "天相": tf + 4, "天梁": tf + 5, "七杀": tf + 6, "破军": tf + 10}
    return {k: v % 12 for k, v in pos.items()}


# 禄存（《安禄存星诀》论本生年干）：甲寅 乙卯 丙巳 丁午 戊巳 己午
# 庚申 辛酉 壬亥 癸子。
_LUCUN = {"甲": 2, "乙": 3, "丙": 5, "丁": 6, "戊": 5,
          "己": 6, "庚": 8, "辛": 9, "壬": 11, "癸": 0}

# 天魁天钺（《安天魁天钺诀》）：甲戊庚牛羊，乙己鼠猴乡，六辛逢虎马，
# 壬癸兔蛇藏，丙丁猪鸡位（底本「猪狗」依通行本订正为「猪鸡」）。
# 辛年从底本「虎马」：魁寅钺午（流行诀作「马虎」互换）。
_KUIYUE = {"甲": (1, 7), "戊": (1, 7), "庚": (1, 7),
           "乙": (0, 8), "己": (0, 8),
           "辛": (2, 6),
           "壬": (3, 5), "癸": (3, 5),
           "丙": (11, 9), "丁": (11, 9)}

# 小限起宫（《安小限诀》论本生年支）：寅午戌人起辰宫，申子辰人自戌宫，
# 巳酉丑人起未宫，亥卯未人起丑宫。
_XIAOXIAN_START = {"寅": 4, "午": 4, "戌": 4, "申": 10, "子": 10, "辰": 10,
                   "巳": 7, "酉": 7, "丑": 7, "亥": 1, "卯": 1, "未": 1}

# 天马（《安天马星诀》论本生年支）：寅午戌人马居申，申子辰人马居寅，
# 巳酉丑人马居亥，亥卯未人马居巳。
_TIANMA = {"寅": 8, "午": 8, "戌": 8, "申": 2, "子": 2, "辰": 2,
           "巳": 11, "酉": 11, "丑": 11, "亥": 5, "卯": 5, "未": 5}

# 火铃起宫（《安火铃二星诀》）：寅午戌人丑卯方，申子辰人寅戌扬，
# 巳酉丑人卯戌位，亥卯未人酉戌房；自起宫起子时顺数至本生时（通行）。
_HUOLING = {"寅": (1, 3), "午": (1, 3), "戌": (1, 3),
            "申": (2, 10), "子": (2, 10), "辰": (2, 10),
            "巳": (3, 10), "酉": (3, 10), "丑": (3, 10),
            "亥": (9, 10), "卯": (9, 10), "未": (9, 10)}

# 四化（《安禄权科忌四星变化诀》论生年干）：甲廉破武阳，乙机梁紫月，
# 丙同机昌廉，丁月同机巨，戊贪月弼机，己武贪梁曲，庚日武阴同，
# 辛巨阳曲昌，壬梁紫府武（天府化科，流行诀作左辅），癸破巨阴贪。
_SIHUA = {
    "甲": ("廉贞", "破军", "武曲", "太阳"),
    "乙": ("天机", "天梁", "紫微", "太阴"),
    "丙": ("天同", "天机", "文昌", "廉贞"),
    "丁": ("太阴", "天同", "天机", "巨门"),
    "戊": ("贪狼", "太阴", "右弼", "天机"),
    "己": ("武曲", "贪狼", "天梁", "文曲"),
    "庚": ("太阳", "武曲", "太阴", "天同"),
    "辛": ("巨门", "太阳", "文曲", "文昌"),
    "壬": ("天梁", "紫微", "天府", "武曲"),
    "癸": ("破军", "巨门", "太阴", "贪狼"),
}


def minor_star_positions(lunar: LunarBirth, month: int, hz: int) -> dict:
    """吉星与煞星（诀名见各行注释）。返回 {星名: (支序, kind)}。"""
    yg, yz = lunar.year_gan, lunar.year_zhi
    lucun = _LUCUN[yg]
    kui, yue = _KUIYUE[yg]
    huo0, ling0 = _HUOLING[yz]
    pos = {
        # 《安文昌文曲星诀》论本生时：子时戌上起文昌逆数，辰上起文曲顺数。
        "文昌": ((10 - hz) % 12, "lucky"),
        "文曲": ((4 + hz) % 12, "lucky"),
        # 《安左辅右弼星诀》论本生月：左辅辰上起正月顺数，右弼戌上起正月逆数。
        "左辅": ((4 + month - 1) % 12, "lucky"),
        "右弼": ((10 - (month - 1)) % 12, "lucky"),
        # 《安天魁天钺诀》论本生年干。
        "天魁": (kui, "lucky"),
        "天钺": (yue, "lucky"),
        # 《安禄存星诀》论本生年干。
        "禄存": (lucun, "lucky"),
        # 《安天马星诀》论本生年支。
        "天马": (_TIANMA[yz], "lucky"),
        # 《安擎羊陀罗二星诀》：禄前擎羊后陀罗。
        "擎羊": ((lucun + 1) % 12, "malefic"),
        "陀罗": ((lucun - 1) % 12, "malefic"),
        # 《安火铃二星诀》论本生年支起宫、顺数至生时。
        "火星": ((huo0 + hz) % 12, "malefic"),
        "铃星": ((ling0 + hz) % 12, "malefic"),
        # 《天空地劫诀》论本生时：亥上起子顺安劫，逆向便是天空乡。
        "地劫": ((11 + hz) % 12, "malefic"),
        "地空": ((11 - hz) % 12, "malefic"),
    }
    return pos


# ── 排盘主函数 ──────────────────────────────────────────────────────────

CONVENTIONS = (
    "年干支以正月初一为界（非立春）",
    "晚子时不换日（23:00 后仍作当日子时）",
    "闰月依《全书·安身命例》整月按下月起数",
    "大限首限起命宫、起限之岁为局数（通行排法）",
    "壬干四化依《全书》天府化科（流行诀作左辅化科）",
    "辛干魁钺依《全书》「六辛逢虎马」魁寅钺午（流行诀互换）",
    "未用真太阳时",
    "时刻一律按北京时间（东八区）解释：生辰按出生地钟表时间填写"
    "（中国大陆即北京时间；海外出生请先自行换算），论限时刻自动取北京时间",
)


def cast(birth: datetime, gender: str) -> Chart:
    """排盘：公历生辰 + 性别 → 命盘。全程查表推演，无随机成分。"""
    if gender not in ("男", "女"):
        raise ValueError("性别须为「男」或「女」")
    lunar = lunar_birth(birth)
    hz = ZHI.index(lunar.shichen_zhi)
    month = _effective_month(lunar)

    ming, shen = ming_shen(month, hz)
    ming_stem = palace_stem(lunar.year_gan, ming)
    ju_name, ju = wuxing_ju(ming_stem, ZHI[ming])
    zw = ziwei_pos(ju, lunar.day_num)

    # 阳干阳年。阳男阴女大限顺行，阴男阳女逆行（《安大限诀》）。
    year_yang = GAN.index(lunar.year_gan) % 2 == 0
    yinyang = ("阳" if year_yang else "阴") + gender
    forward = yinyang in ("阳男", "阴女")

    star_at = {}
    for name, b in major_star_positions(zw).items():
        star_at.setdefault(b, []).append((name, "major"))
    for name, (b, kind) in minor_star_positions(lunar, month, hz).items():
        star_at.setdefault(b, []).append((name, kind))

    sihua_stars = _SIHUA[lunar.year_gan]
    sihua_of = {name: hua for name, hua in zip(sihua_stars, "禄权科忌")}

    palaces = []
    for i, pname in enumerate(PALACE_NAMES):
        b = (ming - i) % 12   # 十二宫自命宫逆布（《安十二宫例》）
        stars = []
        for sname, kind in star_at.get(b, []):
            stars.append(PalaceStar(
                name=sname, kind=kind,
                brightness=brightness.of(sname, ZHI[b]) or "",
                sihua=sihua_of.get(sname, ""),
            ))
        stars.sort(key=lambda s: (s.kind != "major",))
        # 大限：首限起命宫，起限之岁为局数，每限十年，顺逆依阴阳男女。
        # palaces[i] 在支序 ming-i；顺行第 k 限在支序 ming+k，故 k=(-i)%12。
        k = (-i) % 12 if forward else i
        lo = ju + 10 * k
        palaces.append(Palace(name=pname, branch=ZHI[b],
                              stem=palace_stem(lunar.year_gan, b),
                              stars=stars, is_body=(b == shen),
                              daxian=(lo, lo + 9)))

    return Chart(
        solar_desc=birth.strftime("%Y-%m-%d %H:%M"),
        lunar=lunar, gender=gender, yinyang=yinyang,
        ming_branch=ZHI[ming], shen_branch=ZHI[shen],
        wuxing_ju=ju_name, ju_num=ju, daxian_forward=forward,
        palaces=palaces,
        sihua={hua: name for name, hua in sihua_of.items()},
        conventions=list(CONVENTIONS),
    )
