"""起卦引擎测试：确定性、可复现性、农历转换。"""

from datetime import datetime, timedelta

import pytest

from yijing_agent import casting, lunar
from yijing_agent.knowledge import KnowledgeBase

kb = KnowledgeBase()


def test_lunar_known_date():
    # 2026-08-24 为农历丙午年七月十二（cnlunar 与 zhdate 双库核对过）
    lm = lunar.from_datetime(datetime(2026, 8, 24, 15, 30))
    assert lm.year_gz == "丙午"
    assert lm.year_zhi_num == 7   # 午
    assert lm.month_num == 7
    assert lm.day_num == 12
    assert lm.shichen_zhi == "申"
    assert lm.shichen_num == 9


def test_lunar_midnight_shichen():
    # 23 点为子时（不换日约定：农历日仍取当日）
    lm = lunar.from_datetime(datetime(2026, 8, 24, 23, 10))
    assert lm.shichen_zhi == "子"
    assert lm.shichen_num == 1
    assert lm.day_num == 12


def test_meihua_deterministic():
    dt = datetime(2026, 8, 24, 15, 30)
    a, b = casting.cast_meihua(dt), casting.cast_meihua(dt)
    assert a.lines == b.lines


def test_meihua_known_case():
    # 丙午年七月十二申时：年支7+月7+日12=26, 26%8=2→兑（上卦）
    # 26+时9=35, 35%8=3→离（下卦）; 35%6=5→动爻五
    cast = casting.cast_meihua(datetime(2026, 8, 24, 15, 30))
    ben_id = kb.id_of(cast.ben_binary)
    assert kb.hexagram(ben_id)["trigrams"] == ["离", "兑"]  # 下离上兑 = 泽火革
    assert kb.full_name(ben_id) == "泽火革"
    assert cast.moving == [5]


def test_meihua_always_one_moving():
    dt = datetime(2025, 1, 1, 0, 0)
    for i in range(50):
        cast = casting.cast_meihua(dt + timedelta(hours=i * 7, days=i * 3))
        assert len(cast.moving) == 1
        assert all(v in (6, 7, 8, 9) for v in cast.lines)


def test_coin_deterministic_by_seed():
    dt = datetime(2026, 8, 24, 15, 30, 0)
    a = casting.cast_coin("问某事", dt)
    b = casting.cast_coin("问某事", dt)
    c = casting.cast_coin("问另一事", dt)
    assert a.lines == b.lines
    assert a.reproducibility["种子"] == b.reproducibility["种子"]
    assert c.reproducibility["种子"] != a.reproducibility["种子"]


def test_coin_lines_valid():
    dt = datetime(2026, 8, 24, 15, 30, 0)
    for i in range(30):
        cast = casting.cast_coin(f"问题{i}", dt)
        assert len(cast.lines) == 6
        assert all(v in (6, 7, 8, 9) for v in cast.lines)
        assert tuple(cast.ben_binary) in kb.by_binary
        assert tuple(cast.zhi_binary) in kb.by_binary


def test_cross_check_with_zhdate():
    zhdate = pytest.importorskip("zhdate")
    for d in (datetime(2024, 2, 10), datetime(2025, 6, 1), datetime(2026, 8, 24),
              datetime(2026, 1, 1), datetime(2027, 3, 15)):
        lm = lunar.from_datetime(d)
        z = zhdate.ZhDate.from_datetime(d)
        assert (z.lunar_month, z.lunar_day) == (lm.month_num, lm.day_num), d
