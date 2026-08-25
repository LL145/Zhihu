"""起卦引擎测试：确定性、可复现性、农历转换。"""

from datetime import datetime, timedelta

import pytest

from tianwen import casting, lunar
from tianwen.knowledge import KnowledgeBase

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


def test_now_beijing_is_utc_plus_8():
    from datetime import timezone
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    diff = lunar.now_beijing() - utc
    assert abs(diff - timedelta(hours=8)) < timedelta(seconds=5)


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


def test_strokes_table_known():
    from tianwen import strokes
    assert strokes.total_strokes("李") == 7
    assert strokes.total_strokes("明") == 8
    assert strokes.total_strokes("林") == 8
    assert strokes.total_strokes("西") == 6   # 古书记七画（西林寺占），约定依今表
    assert strokes.total_strokes("A") is None


def test_zi_two_chars_known():
    # 李7画→艮上卦，明8画→坤下卦，总15画%6=3动爻 → 山地剥
    # （与西林寺牌额占「上七画下八画总十五画……是山地剥卦」同构）
    cast = casting.cast_zi("李明")
    ben_id = kb.id_of(cast.ben_binary)
    assert kb.hexagram(ben_id)["trigrams"] == ["坤", "艮"]  # 下坤上艮 = 山地剥
    assert kb.full_name(ben_id) == "山地剥"
    assert cast.moving == [3]


def test_zi_three_chars_known():
    # 三字为三才：王4画→震上卦；小3+明8=11, 11%8=3→离下卦；总15画%6=3动爻
    cast = casting.cast_zi("王小明")
    ben_id = kb.id_of(cast.ben_binary)
    assert kb.hexagram(ben_id)["trigrams"] == ["离", "震"]  # 下离上震 = 雷火丰
    assert kb.full_name(ben_id) == "雷火丰"
    assert cast.moving == [3]


def test_zi_deterministic_and_time_free():
    # 纯由所占之字确定：与时刻无关，空白忽略
    a, b = casting.cast_zi("李明"), casting.cast_zi(" 李 明 ")
    assert a.lines == b.lines
    assert a.method == "meihua_zi"


def test_zi_lines_valid():
    for name in ("张伟", "王芳", "诸葛亮", "司马光", "龘靐"):
        cast = casting.cast_zi(name)
        assert len(cast.moving) == 1
        assert all(v in (6, 7, 8, 9) for v in cast.lines)
        assert tuple(cast.ben_binary) in kb.by_binary
        assert tuple(cast.zhi_binary) in kb.by_binary


def test_zi_rejects_out_of_scope():
    # 空、一字（须辨左右阴阳画）、四字以上（古法改平仄）、非汉字：如实拒之
    for bad in ("", "李", "欧阳明月", "AB", "李A"):
        with pytest.raises(ValueError):
            casting.cast_zi(bad)


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


# ── 问语起卦（书写来意，以其字占之；v3.5） ──────────────────────────

WHEN = datetime(2026, 8, 24, 11, 0)   # 丙午年七月十二 午时（时数7）


def test_wenyu_nine_chars_known():
    # 「近期换工作是否合适」9字不匀：少一半（4）为上卦→震，多一半（5）
    # 为下卦→巽（雷风恒）；动爻=(9+午7)%6=4（「取爻当以时加之」）
    cast = casting.cast_wenyu("近期换工作是否合适", WHEN)
    assert cast.method == "meihua_wenyu"
    assert kb.full_name(kb.id_of(cast.ben_binary)) == "雷风恒"
    assert cast.moving == [4]
    assert "字数分之" in cast.reproducibility["约定"]


def test_wenyu_even_split_and_non_hanzi_ignored():
    # 8字均平对半：4→震上、4→震下（震为雷）；动爻=(8+7)%6=3
    a = casting.cast_wenyu("今日出门是否顺利", WHEN)
    assert kb.full_name(kb.id_of(a.ben_binary)) == "震为雷"
    assert a.moving == [3]
    # 只数汉字：标点、字母、数字不入数
    b = casting.cast_wenyu("今日出门，是否顺利？OK123", WHEN)
    assert b.lines == a.lines


def test_wenyu_time_enters_moving_only():
    # 同问异时：卦体由字数定（不变），动爻随时辰而动
    a = casting.cast_wenyu("近期换工作是否合适", datetime(2026, 8, 24, 11, 0))
    b = casting.cast_wenyu("近期换工作是否合适", datetime(2026, 8, 24, 15, 30))
    assert a.ben_binary == b.ben_binary
    assert a.moving == [4] and b.moving == [6]   # (9+申9)%6=0→取6


def test_wenyu_two_three_chars_use_strokes():
    # 二三字依字画（同姓名卦法），动爻加时：求7画→艮、财7画→艮
    # （艮为山），动爻=(总14画+午7)%6=3
    cast = casting.cast_wenyu("求财", WHEN)
    assert kb.full_name(kb.id_of(cast.ben_binary)) == "艮为山"
    assert cast.moving == [3]


def test_wenyu_rejects_and_deterministic():
    with pytest.raises(ValueError):
        casting.cast_wenyu("ABC 123", WHEN)      # 无汉字可数
    with pytest.raises(ValueError):
        casting.cast_wenyu("占", WHEN)           # 一字须辨阴阳画
    a = casting.cast_wenyu("明日天气如何", WHEN)
    assert a.lines == casting.cast_wenyu("明日天气如何", WHEN).lines
