"""繁体输入归一测试：三关键词层命中、覆盖完备性（OpenCC 反向验证）。"""

import pytest

from tianwen import hanzi, redline, topic
from tianwen.ziwei import selection


def _all_keywords():
    kws = set()
    for _k, _n, _h, keywords, _note in topic._RULES:
        kws.update(keywords)
    for words in redline._CATEGORIES.values():
        kws.update(words)
    kws.update(redline._CRISIS)
    for _palace, keywords in selection.ASPECTS:
        kws.update(keywords)
    return kws


def test_coverage_via_opencc():
    """关键词表增删的守门员：每个关键词经 OpenCC 转繁（三种配置）后，
    归一必须还原为简体原词——缺字即红，提示补 hanzi._T2S。"""
    opencc = pytest.importorskip("opencc")
    kws = _all_keywords()
    assert len(kws) > 150
    for cfg in ("s2t", "s2tw", "s2hk"):
        cc = opencc.OpenCC(cfg)
        for kw in kws:
            assert hanzi.t2s(cc.convert(kw)) == kw, (cfg, kw)


def test_t2s_basic():
    assert hanzi.t2s("離職") == "离职"
    assert hanzi.t2s("离职") == "离职"          # 简体原样
    assert hanzi.t2s("") == "" and hanzi.t2s(None) == ""
    # 表外字原样保留（非通用转换器）
    assert hanzi.t2s("風雲") == "風雲"


def test_classify_traditional():
    t = topic.classify("考慮離職")
    assert t.name == "事业" and t.matched == "离职"
    assert topic.classify("今年運勢如何").name == "时运"
    assert topic.classify("該不該跳槽").name == "事业"     # 事业先于决策抉择
    # 书写变体：復合（OpenCC 词转作複合，两形皆须命中）
    assert topic.classify("想跟前任復合").name == "情感"
    assert topic.classify("想跟前任複合").name == "情感"
    assert topic.classify("我是甚麼命").name == "命格"


def test_redline_traditional():
    assert redline.check("想投資虛擬貨幣") is not None
    assert redline.check("最近該做手術嗎") is not None
    assert "12356" in redline.check("有自殺的念頭")
    assert redline.check("考慮離職") is None


def test_detect_aspect_traditional():
    assert selection.detect_aspect("戀愛運如何")[0] == "妻妾"
    assert selection.detect_aspect("想換房") == ("田宅", "房")
    assert selection.detect_aspect("明日天氣")[0] is None


def test_casting_not_normalized():
    """起卦不归一：以所书之字占之，繁简画数各随字形。"""
    from datetime import datetime
    from tianwen import casting
    dt = datetime(2026, 8, 26, 10, 0)
    a = casting.cast_wenyu("問路", dt)     # 問11画
    b = casting.cast_wenyu("问路", dt)     # 问6画
    assert "問=11画" in a.reproducibility["取数"]
    assert "问=6画" in b.reproducibility["取数"]
