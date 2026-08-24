"""公历 → 农历转换（起卦用），基于 cnlunar（纯 Python）。

本产品显式约定（流派差异，如实标注，见 DESIGN.md 附录C）：
- 全程一律北京时间（东八区）：农历由东八区定义，「当前时刻」起卦取
  now_beijing()，同一时刻在任何时区起卦结果一致（可复现）；
- 年支以农历正月初一为界（非立春），依《梅花易数》以农历年月日时起数的传统；
- 闰月取本月月数（闰七月按七月起数），并在凭证中标注；
- 晚子时（23:00-23:59）不换日，取当日农历日，时辰数为子（1）。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import cnlunar

_CST = timezone(timedelta(hours=8))   # 北京时间：固定 +8，无夏令时


def now_beijing() -> datetime:
    """当前时刻的北京时间（naive datetime）。

    起卦/论限的「当前时刻」一律经此取得：系统时钟在哪个时区都得到
    同一北京时间，农历换算（东八区定义）随之正确，结果全球可复现。
    """
    return datetime.now(_CST).replace(tzinfo=None)

from .trigrams import GAN, ZHI


@dataclass
class LunarMoment:
    year_gz: str          # 农历年干支，如「丙午」
    year_zhi_num: int     # 年支数：子1 … 亥12
    month_num: int        # 农历月数（闰月同本月）
    is_leap_month: bool
    day_num: int          # 农历日数
    shichen_zhi: str      # 时辰地支
    shichen_num: int      # 时辰数：子1 … 亥12
    description: str      # 人读版，如「农历丙午年七月十二 申时」

    @property
    def convention_notes(self):
        notes = ["年支以正月初一为界", "晚子时不换日"]
        if self.is_leap_month:
            notes.append(f"闰{_CN_MONTH[self.month_num]}月按{self.month_num}起数")
        return notes


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


def from_datetime(dt: datetime) -> LunarMoment:
    a = cnlunar.Lunar(dt, godType="8char")
    lunar_year = a.lunarYear
    gan = GAN[(lunar_year - 4) % 10]
    zhi_idx = (lunar_year - 4) % 12
    shichen_idx = ((dt.hour + 1) // 2) % 12
    month = a.lunarMonth
    leap = bool(a.isLunarLeapMonth)
    day = a.lunarDay
    desc = (f"农历{gan}{ZHI[zhi_idx]}年{'闰' if leap else ''}"
            f"{_CN_MONTH[month]}月{_cn_day(day)} {ZHI[shichen_idx]}时")
    return LunarMoment(
        year_gz=gan + ZHI[zhi_idx],
        year_zhi_num=zhi_idx + 1,
        month_num=month,
        is_leap_month=leap,
        day_num=day,
        shichen_zhi=ZHI[shichen_idx],
        shichen_num=shichen_idx + 1,
        description=desc,
    )
