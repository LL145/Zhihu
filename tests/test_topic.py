"""问事分类测试：关键词命中、优先级、命理类提示、兜底。"""

from tianwen import topic


def test_career_beats_choice():
    # 含「是否」但先命中事业类关键词
    t = topic.classify("近期换一份工作是否合适")
    assert t.name == "事业" and t.matched == "工作"
    assert t.engine_hint == "event"


def test_study():
    assert topic.classify("今年考研能否顺利").name == "学业"


def test_love():
    assert topic.classify("要不要向她表白").name == "情感"


def test_relation():
    assert topic.classify("和同事的矛盾能否化解").name == "人际"


def test_travel():
    assert topic.classify("下月出差是否顺利").name == "出行"


def test_dwelling():
    assert topic.classify("年底搬家合适吗").name == "居所"


def test_choice_fallback():
    t = topic.classify("两个方向该不该换")
    assert t.name == "决策抉择"


def test_destiny_is_chart():
    t = topic.classify("我是什么命格")
    assert t.name == "命格" and t.engine_hint == "chart"


def test_fortune_is_chart():
    t = topic.classify("最近运气怎么样")
    assert t.name == "时运" and t.engine_hint == "chart"


def test_fortune_beats_domain_keywords():
    # 问「×运/运势」即是问时运，纵带具体题材也走命理（题材由问事分宫处理）
    assert topic.classify("今年事业运势如何").name == "时运"
    assert topic.classify("我的财运怎么样").name == "时运"
    assert topic.classify("今年桃花运如何").name == "时运"
    # 无运字眼的具体事仍走事类
    assert topic.classify("近期换一份工作是否合适").name == "事业"


def test_unmatched_falls_to_other():
    t = topic.classify("明日天气如何")
    assert t.name == "其他" and t.matched == "" and t.engine_hint == "event"


def test_all_rules_have_notes():
    for _, name, hint, keywords, note in topic._RULES:
        assert name and note and keywords
        assert hint in ("event", "chart")
    assert topic._DEFAULT.note


def test_deterministic():
    q = "近期换一份工作是否合适"
    assert topic.classify(q) == topic.classify(q)


def test_by_key_and_categories():
    import pytest
    t = topic.by_key("love", source="user")
    assert t.name == "情感" and t.source == "user" and t.engine_hint == "event"
    assert topic.by_key("other").name == "其他"
    keys = dict(topic.CATEGORIES)
    assert "fortune" in keys and keys["other"] == "其他"
    with pytest.raises(KeyError):
        topic.by_key("nonsense")


def test_classify_source_is_rule():
    assert topic.classify("近期换一份工作是否合适").source == "rule"
