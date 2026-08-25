"""命引擎选文与确定性结论测试。"""

from datetime import datetime

import pytest

from tianwen.ziwei import chart, selection
from tianwen.ziwei.knowledge import ZiweiKB


@pytest.fixture(scope="module")
def zkb():
    return ZiweiKB()


@pytest.fixture(scope="module")
def c2000():
    # 2000-09-14 午时男：命宫卯，太阴落陷化科，土五局阳男顺行
    return chart.cast(datetime(2000, 9, 14, 12, 0), "男")


def test_destiny_selection(zkb, c2000):
    sel = selection.select_destiny(zkb, c2000)
    assert sel.palace_name == "命宫" and sel.branch == "卯"
    assert "命身同宫" in sel.notes
    [r] = [r for r in sel.readings if r.primary]
    assert r.primary and r.cite_id == "ziwei:2:ming:taiyin"
    assert "太阴" in r.role and "落陷" in r.role and "化科" in r.role
    ctx = list(r.context_ids)
    assert "ziwei:2:ming:taiyin:male" in ctx       # 男命取男命诀
    assert "ziwei:1:wenda:taiyin" in ctx
    ge = [cid for cid in ctx if ":ge:" in cid]
    assert len(ge) == 1
    assert "卯" in zkb.citation(ge[0])["text"]


def test_destiny_female_uses_female_jue(zkb):
    c = chart.cast(datetime(2000, 9, 14, 12, 0), "女")
    sel = selection.select_destiny(zkb, c)
    ctx = list(sel.readings[0].context_ids)
    assert "ziwei:2:ming:taiyin:female" in ctx
    assert "ziwei:2:ming:taiyin:male" not in ctx


def test_destiny_verdict_weak(c2000):
    vd = selection.decide_destiny(c2000)
    assert vd["verdict"] == "弱"
    assert vd["audited"] is False
    assert "太阴落陷" in vd["basis"]
    assert vd["cite_id"] == "ziwei:2:ming:taiyin"


def test_destiny_borrow_opposite(zkb):
    # 1980-01-14 巳时男：命宫未无正曜，借对宫（丑）日月
    c = chart.cast(datetime(1980, 1, 14, 10, 0), "男")
    assert not c.palaces[0].major()
    sel = selection.select_destiny(zkb, c)
    assert any("借对宫" in n for n in sel.notes)
    primaries = [r for r in sel.readings if r.primary]
    names = {r.role for r in primaries}
    assert any("太阳" in n for n in names) and any("太阴" in n for n in names)
    assert all("借自迁移宫" in r.role for r in primaries)
    # 借宫不取分宫格；格诀仍按安命宫支取（诀本按宫支立文，与借宫无涉）
    assert all(":ge:" not in cid
               for r in sel.readings for cid in r.context_ids)
    assert any(r.cite_id.startswith("ziwei:1:hege:") for r in sel.readings)
    vd = selection.decide_destiny(c)
    assert "无正曜" in vd["basis"] and "借对宫" in vd["basis"]
    assert vd["verdict"] == "强弱互见"     # 丑宫太阴庙、太阳不得地
    assert "借宫" in vd["action"]


def test_fortune_selection(zkb, c2000):
    at = datetime(2026, 8, 24)
    sel = selection.select_fortune(zkb, c2000, at)
    assert sel.palace_name == "福德" and sel.branch == "巳"
    assert any("25–34" in n and "虚岁 27" in n for n in sel.notes)
    primaries = [r for r in sel.readings if r.primary]
    [r] = primaries
    assert r.cite_id == "ziwei:2:ming:jumen:xian"    # 巨门入限诀
    ctxs = [r for r in sel.readings if not r.primary]
    assert ctxs[0].cite_id == "ziwei:3:daxian"


def test_fortune_verdict_three_cases():
    # 中：2000 例，2026 年行福德（巨门旺 + 空劫）
    c = chart.cast(datetime(2000, 9, 14, 12, 0), "男")
    assert selection.decide_fortune(c, datetime(2026, 8, 24))["verdict"] == "中"
    # 顺 / 危：1980-01-05 卯时男，2020 行子女（破军庙无煞）／2010 行妻妾（天机陷值忌煞）
    c2 = chart.cast(datetime(1980, 1, 5, 6, 0), "男")
    v_shun = selection.decide_fortune(c2, datetime(2020, 6, 1))
    assert v_shun["verdict"] == "顺"
    assert "无煞忌同宫" in v_shun["basis"]
    v_wei = selection.decide_fortune(c2, datetime(2010, 6, 1))
    assert v_wei["verdict"] == "危"
    assert "化忌" in v_wei["basis"]
    assert v_wei["cite_id"] == "ziwei:3:daxian"


def test_detect_aspect():
    assert selection.detect_aspect("我今年财运如何") == ("财帛", "财")
    assert selection.detect_aspect("今年婚恋运势") == ("妻妾", "婚")
    assert selection.detect_aspect("事业运怎么样")[0] == "官禄"
    assert selection.detect_aspect("最近运气怎么样") == (None, "")


def test_fortune_with_aspect(zkb, c2000):
    # 问财运：大限主断之外加取财帛宫诸星断语；限势总论仍垫底
    sel = selection.select_fortune(zkb, c2000, datetime(2026, 8, 24), "财帛")
    aspect = [r for r in sel.readings if "所问之宫" in r.role]
    assert aspect and all(r.cite_id.startswith("ziwei:2:gong:caibo:")
                          for r in aspect)
    assert any("财帛宫" in r.role for r in aspect)
    assert any("题材宫只入解读，不另出结论" in n for n in sel.notes)
    assert any(r.role == "限势总论" for r in sel.readings)
    assert sel.readings[-1].role == "二限太岁总说"   # 流年块垫底
    # 大限主断仍居首
    assert sel.readings[0].cite_id == "ziwei:2:ming:jumen:xian"


def test_destiny_with_aspect(zkb, c2000):
    sel = selection.select_destiny(zkb, c2000, "官禄")
    assert any(r.cite_id.startswith("ziwei:2:gong:guanlu:")
               for r in sel.readings)
    # 命宫主断仍在
    assert sel.readings[0].cite_id == "ziwei:2:ming:taiyin"


def test_select_context_for_event(zkb, c2000):
    # 合参（§6.2）：问事业的具体事 → 官禄宫断语，仅作语境（无 primary）
    from tianwen import topic
    tp = topic.classify("近期换一份工作是否合适")
    sel = selection.select_context(zkb, c2000, tp, "近期换一份工作是否合适")
    assert sel.readings
    assert all(not r.primary for r in sel.readings)
    assert all(r.cite_id.startswith("ziwei:2:gong:guanlu:")
               for r in sel.readings)
    assert "不出第二结论" in sel.rule


def test_select_context_fallback_ming(zkb, c2000):
    # 无专属之宫的问事 → 命宫主星论断文作语境
    from tianwen import topic
    tp = topic.classify("明日天气如何")
    sel = selection.select_context(zkb, c2000, tp, "明日天气如何")
    assert sel.readings
    assert sel.readings[0].cite_id == "ziwei:2:ming:taiyin"
    assert all(not r.primary for r in sel.readings)


def test_fortune_before_qixian(zkb):
    # 未及起限之岁（虚岁 < 局数）：以命宫论并标注
    c = chart.cast(datetime(2000, 9, 14, 12, 0), "男")   # 土五局 5 岁起限
    sel = selection.select_fortune(zkb, c, datetime(2001, 6, 1))
    assert any("未及起限" in n for n in sel.notes)
    assert sel.palace_name == "命宫"


# ── v2.5 接线：格诀查表、流年二限、书桌 ─────────────────────────────


def test_destiny_gejue_by_branch(zkb, c2000):
    # 命宫卯：合格诀取卯安命一条、破格诀取涉卯之行，均只作语境参照
    sel = selection.select_destiny(zkb, c2000)
    [h] = [r for r in sel.readings if r.cite_id.startswith("ziwei:1:hege:")]
    assert h.cite_id == "ziwei:1:hege:mao" and not h.primary
    assert "卯安命" in zkb.citation(h.cite_id)["text"]
    poge = [r for r in sel.readings if r.cite_id.startswith("ziwei:1:poge:")]
    assert poge and all(not r.primary for r in poge)
    assert all("卯" in zkb.record(r.cite_id)["branches"] for r in poge)
    assert any("格诀按安命宫支" in n for n in sel.notes)
    # 时运问不取格诀（格诀论安命，非论限）
    fsel = selection.select_fortune(zkb, c2000, datetime(2026, 8, 24))
    assert not any(r.cite_id.startswith("ziwei:1:hege:")
                   for r in fsel.readings)


def test_fortune_liunian(zkb, c2000):
    # 2026 丙午年：太岁午在田宅；庚辰男 27 虚岁小限在子（申子辰起戌顺行）
    sel = selection.select_fortune(zkb, c2000, datetime(2026, 8, 24))
    assert any("太岁在午（田宅宫）" in n and "小限在子" in n
               for n in sel.notes)
    assert any("太岁冲小限（子）" in n for n in sel.notes)
    # 小限宫（子女，破军庙）主星附入限诀为参；二限太岁总说垫底
    xiao = [r for r in sel.readings if r.role.startswith("小限")]
    assert xiao and xiao[0].cite_id == "ziwei:2:ming:pojun:xian"
    assert all(not r.primary for r in xiao)
    assert sel.readings[-1].cite_id == "ziwei:3:erxian"
    # 结论仍单源：定例仍依《论大限》三例
    vd = selection.decide_fortune(c2000, datetime(2026, 8, 24))
    assert vd["cite_id"] == "ziwei:3:daxian"


def test_desk_stars_recorded(zkb, c2000):
    assert selection.select_destiny(zkb, c2000).desk_stars == ("太阴",)
    sel = selection.select_fortune(zkb, c2000, datetime(2026, 8, 24))
    assert sel.desk_stars == ("巨门",)
