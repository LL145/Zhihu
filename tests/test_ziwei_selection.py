"""命引擎选文与确定性结论测试。"""

from datetime import datetime

import pytest

from yijing_agent.ziwei import chart, selection
from yijing_agent.ziwei.knowledge import ZiweiKB


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
    [r] = sel.readings
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
    names = {r.role for r in sel.readings}
    assert any("太阳" in n for n in names) and any("太阴" in n for n in names)
    assert all("借自迁移宫" in r.role for r in sel.readings)
    # 借宫不取分宫格
    assert all(":ge:" not in cid
               for r in sel.readings for cid in r.context_ids)
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


def test_fortune_before_qixian(zkb):
    # 未及起限之岁（虚岁 < 局数）：以命宫论并标注
    c = chart.cast(datetime(2000, 9, 14, 12, 0), "男")   # 土五局 5 岁起限
    sel = selection.select_fortune(zkb, c, datetime(2001, 6, 1))
    assert any("未及起限" in n for n in sel.notes)
    assert sel.palace_name == "命宫"
