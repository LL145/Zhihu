"""紫微排盘引擎测试。

两层：
1. 命例回归集（tests/fixtures/ziwei_iztro.json，由 tools/gen_ziwei_fixtures.py
   以 py-iztro 生成）：21 例覆盖十天干、早子时、正月初一、腊月、闰月下半月，
   逐宫比对宫名宫干、身宫、五行局、大限、28 星落宫、四化。
   流派分歧处的对照口径见生成脚本顶注（壬干不比化科、辛干魁钺比集合）。
2. 安星诀单测：直接取《紫微斗数全书·卷二》诀文与逐局起紫微表中的明文
   例子核对各纯函数。
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from tianwen.trigrams import ZHI
from tianwen.ziwei import brightness, chart

FIXTURE = Path(__file__).parent / "fixtures" / "ziwei_iztro.json"


def _cases():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", _cases(),
                         ids=[f"{c['solar']}-{c['gender']}" for c in _cases()])
def test_regression_against_iztro(case):
    y, m, d = (int(x) for x in case["solar"].split("-"))
    hour = case["time_index"] * 2
    c = chart.cast(datetime(y, m, d, hour, 30), case["gender"])

    assert c.wuxing_ju == case["wuxing_ju"]
    assert c.shen_branch == case["body_branch"]
    assert c.lunar.year_gan == case["year_gz"]

    for p in c.palaces:
        exp = case["palaces"][p.branch]
        assert p.name == exp["name"], f"{p.branch} 宫名"
        assert p.stem == exp["stem"], f"{p.branch} 宫干"
        assert list(p.daxian) == exp["daxian"], f"{p.branch} 大限"

    ours = {}
    for p in c.palaces:
        for s in p.stars:
            ours[s.name] = p.branch
    xin_year = case["year_gz"] == "辛"
    for star, branch in case["stars"].items():
        if xin_year and star in ("天魁", "天钺"):
            continue
        assert ours[star] == branch, f"{star} 落宫"
    if xin_year:
        assert {ours["天魁"], ours["天钺"]} == \
            {case["stars"]["天魁"], case["stars"]["天钺"]}
        # 《全书》「六辛逢虎马」：魁寅钺午
        assert ours["天魁"] == "寅" and ours["天钺"] == "午"

    for hua in "禄权忌":
        assert c.sihua[hua] == case["sihua"][hua], f"化{hua}"
    if case["year_gz"] == "壬":
        assert c.sihua["科"] == "天府"   # 《全书》壬梁紫府武
    else:
        assert c.sihua["科"] == case["sihua"]["科"]


# ── 安星诀单测（例子皆出《全书·卷二》明文） ──────────────────────────


def test_ming_shen_examples():
    # 《安身命例》：正月生子时寅宫安身命；丑时丑安命卯安身；寅时子安命辰安身。
    assert chart.ming_shen(1, 0) == (2, 2)
    assert chart.ming_shen(1, 1) == (1, 3)
    assert chart.ming_shen(1, 2) == (0, 4)


def test_leap_month_next_month():
    # 「闰正月生者要在二月内起安身命」：闰月整月按下月起数。
    lb = chart.LunarBirth(lunar_year=2000, year_gan="庚", year_zhi="辰",
                          month_num=1, is_leap_month=True, day_num=5,
                          shichen_zhi="子", description="")
    assert chart._effective_month(lb) == 2
    lb2 = chart.LunarBirth(lunar_year=2000, year_gan="庚", year_zhi="辰",
                           month_num=12, is_leap_month=True, day_num=5,
                           shichen_zhi="子", description="")
    assert chart._effective_month(lb2) == 1


def test_wuhudun():
    # 《起五行寅例》：甲己起丙寅、乙庚起戊寅、丙辛起庚寅、丁壬起壬寅、戊癸起甲寅。
    assert chart.palace_stem("甲", 2) == "丙"
    assert chart.palace_stem("庚", 2) == "戊"
    assert chart.palace_stem("辛", 2) == "庚"
    assert chart.palace_stem("壬", 2) == "壬"
    assert chart.palace_stem("癸", 2) == "甲"
    # 子丑两宫续排（与寅卯同干）：庚年子宫戊、丑宫己。
    assert chart.palace_stem("庚", 0) == "戊"
    assert chart.palace_stem("庚", 1) == "己"


def test_nayin():
    # 《六十花甲子纳音歌》抽查。
    assert chart.nayin_element("甲", "子") == "金"   # 海中金
    assert chart.nayin_element("己", "卯") == "土"   # 城头土
    assert chart.nayin_element("辛", "卯") == "木"   # 松柏木
    assert chart.nayin_element("壬", "寅") == "金"   # 金箔金
    assert chart.nayin_element("庚", "午") == "土"   # 路旁土
    assert chart.nayin_element("癸", "亥") == "水"   # 大海水
    assert chart.nayin_element("戊", "午") == "火"   # 天上火


def test_ziwei_pos_against_book_tables():
    # 《全书·卷二》逐局起紫微表抽查（诀：水二局初一起丑初二寅；木三局
    # 初一起龙初二牛；金四局初一寻猪惟有初二辰上起；土五局初一午上二亥宫；
    # 火六局初一酉）。
    z = ZHI.index
    assert chart.ziwei_pos(2, 1) == z("丑")
    assert chart.ziwei_pos(2, 2) == z("寅")
    assert chart.ziwei_pos(2, 3) == z("寅")
    assert chart.ziwei_pos(2, 8) == z("巳")
    assert chart.ziwei_pos(3, 1) == z("辰")
    assert chart.ziwei_pos(3, 2) == z("丑")
    assert chart.ziwei_pos(3, 3) == z("寅")
    assert chart.ziwei_pos(3, 30) == z("亥")
    assert chart.ziwei_pos(4, 1) == z("亥")
    assert chart.ziwei_pos(4, 2) == z("辰")
    assert chart.ziwei_pos(5, 1) == z("午")
    assert chart.ziwei_pos(5, 2) == z("亥")
    assert chart.ziwei_pos(6, 1) == z("酉")


def test_major_stars_relative_layout():
    # 《安南北斗诸星诀》：紫微在寅时天府同宫寅（对称于寅申轴）。
    pos = chart.major_star_positions(2)
    assert pos["天府"] == 2
    assert pos["天机"] == 1      # 紫微逆一
    assert pos["太阳"] == 11     # 隔一
    assert pos["武曲"] == 10
    assert pos["天同"] == 9
    assert pos["廉贞"] == 6      # 又隔二位
    assert pos["破军"] == 0      # 天府顺十
    assert pos["七杀"] == 8


def test_brightness_from_book_table():
    # 《全书·卷二》庙陷表抽查，含与流行工具不同的底本特征值。
    assert brightness.of("紫微", "午") == "庙"
    assert brightness.of("太阴", "卯") == "落陷"
    assert brightness.of("七杀", "酉") == "旺"     # 底本作旺（流行多作庙）
    assert brightness.of("太阳", "未") == "得地"
    assert brightness.of("擎羊", "子") == "落陷"
    assert brightness.of("陀罗", "子") is None     # 陀罗永不在子，底本不载
    assert brightness.of("左辅", "子") is None     # 此表不载辅弼


def test_sihua_book_school():
    c = chart.cast(datetime(2012, 3, 8, 8, 30), "女")   # 壬辰年
    assert c.sihua == {"禄": "天梁", "权": "紫微", "科": "天府", "忌": "武曲"}


def test_determinism():
    a = chart.cast(datetime(2000, 9, 14, 12, 0), "男")
    b = chart.cast(datetime(2000, 9, 14, 12, 0), "男")
    assert a == b


def test_late_zi_hour_same_day():
    # 晚子时不换日：23:30 与当日 0:30 同盘。
    a = chart.cast(datetime(2000, 9, 14, 23, 30), "男")
    b = chart.cast(datetime(2000, 9, 14, 0, 30), "男")
    assert a.ming_branch == b.ming_branch
    assert a.lunar.day_num == b.lunar.day_num
    assert a.lunar.shichen_zhi == "子" == b.lunar.shichen_zhi


def test_gender_affects_daxian_direction_only():
    m = chart.cast(datetime(2000, 9, 14, 12, 0), "男")   # 庚辰阳男顺行
    f = chart.cast(datetime(2000, 9, 14, 12, 0), "女")   # 阳女逆行
    assert m.daxian_forward and not f.daxian_forward
    assert m.palaces[0].daxian == f.palaces[0].daxian == (5, 14)
    assert m.palaces[11].daxian == (15, 24)   # 父母宫为顺行第二限
    assert f.palaces[1].daxian == (15, 24)    # 兄弟宫为逆行第二限
    for pm, pf in zip(m.palaces, f.palaces):
        assert [s.name for s in pm.stars] == [s.name for s in pf.stars]


def test_invalid_gender():
    with pytest.raises(ValueError):
        chart.cast(datetime(2000, 9, 14, 12, 0), "?")
