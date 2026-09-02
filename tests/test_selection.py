"""断卦规则引擎测试：朱子占法七种情形 + 梅花体用。"""

import pytest

from tianwen.knowledge import KnowledgeBase
from tianwen.selection import select, select_meihua, select_zhuzi

kb = KnowledgeBase()


def _primary(sel):
    return sel.primary.cite_id


def test_zhuzi_0_moving():
    sel = select_zhuzi(kb, 3, 3, [])
    assert _primary(sel) == "zhouyi:3:guaci"
    assert len(sel.readings) == 1


def test_zhuzi_1_moving():
    sel = select_zhuzi(kb, 1, 44, [1])
    assert _primary(sel) == "zhouyi:1:yao:1"     # 乾初九
    roles = [r.role for r in sel.readings]
    assert any("参" in r for r in roles)


def test_zhuzi_2_moving_upper_primary():
    sel = select_zhuzi(kb, 1, 64, [2, 5])
    assert _primary(sel) == "zhouyi:1:yao:5"     # 以上爻为主
    ids = [r.cite_id for r in sel.readings]
    assert "zhouyi:1:yao:2" in ids


def test_zhuzi_3_moving_both_guaci():
    sel = select_zhuzi(kb, 11, 12, [1, 2, 3])
    assert _primary(sel) == "zhouyi:11:guaci"    # 本卦为贞（主）
    ids = [r.cite_id for r in sel.readings]
    assert "zhouyi:12:guaci" in ids


def test_zhuzi_4_moving_zhi_unchanged_lower_primary():
    sel = select_zhuzi(kb, 1, 2, [1, 2, 3, 4])   # 不变爻为 5、6
    assert _primary(sel) == "zhouyi:2:yao:5"     # 之卦，以下爻为主
    ids = [r.cite_id for r in sel.readings]
    assert "zhouyi:2:yao:6" in ids


def test_zhuzi_5_moving():
    sel = select_zhuzi(kb, 1, 2, [1, 2, 3, 4, 6])
    assert _primary(sel) == "zhouyi:2:yao:5"     # 之卦不变爻


def test_zhuzi_6_moving_qian_uses_yongjiu():
    sel = select_zhuzi(kb, 1, 2, [1, 2, 3, 4, 5, 6])
    assert _primary(sel) == "zhouyi:1:extra"     # 乾用九
    sel = select_zhuzi(kb, 2, 1, [1, 2, 3, 4, 5, 6])
    assert _primary(sel) == "zhouyi:2:extra"     # 坤用六


def test_zhuzi_6_moving_other_uses_zhi_guaci():
    sel = select_zhuzi(kb, 3, 50, [1, 2, 3, 4, 5, 6])
    assert _primary(sel) == "zhouyi:50:guaci"


def test_meihua_selection():
    sel = select_meihua(kb, 49, 55, 5)
    assert _primary(sel) == "meihua:2:tiyong"        # 体用生克主断
    ids = [r.cite_id for r in sel.readings]
    assert "zhouyi:49:yao:5" in ids                   # 爻辞为参
    assert "zhouyi:49:guaci" in ids and "zhouyi:55:guaci" in ids
    assert "梅花易数" in sel.rule and sel.tiyong is not None


def test_select_dispatch():
    assert "梅花" in select(kb, "meihua_time", 1, 44, [1]).rule
    assert "朱熹" in select(kb, "coin", 1, 44, [1]).rule


def test_meihua_requires_single_moving():
    with pytest.raises(AssertionError):
        select(kb, "meihua_time", 1, 2, [1, 2])


def test_context_ids_valid():
    for sel in (select_zhuzi(kb, 1, 2, [1, 2, 3, 4, 5, 6]),
                select_meihua(kb, 3, 8, 1),
                select_zhuzi(kb, 29, 30, [])):
        for r in sel.readings:
            assert kb.has(r.cite_id)
            for cid in r.context_ids:
                assert kb.has(cid), cid
