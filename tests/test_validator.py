"""引文校验器测试：幻觉闸门必须挡住不实引文与越界出处。"""

from yijing_agent.validator import normalize, validate

ALLOWED = {
    "zhouyi:1:yao:4": "或跃在渊，无咎。",
    "xiaoxiang:1:4": "“或跃在渊”，进无咎也。",
}


def _ok_result():
    return {
        "translation": "白话",
        "interpretation": "解读文字 [zhouyi:1:yao:4]",
        "advice": ["建议一", "建议二"],
        "quotes": [{"text": "或跃在渊，无咎", "cite_id": "zhouyi:1:yao:4"}],
    }


def test_normalize_strips_punct():
    assert normalize("“或跃在渊”，进无咎也。") == "或跃在渊进无咎也"


def test_valid_passes():
    assert validate(_ok_result(), ALLOWED) == []


def test_quote_substring_ok():
    r = _ok_result()
    r["quotes"] = [{"text": "进无咎也", "cite_id": "xiaoxiang:1:4"}]
    assert validate(r, ALLOWED) == []


def test_fabricated_quote_rejected():
    r = _ok_result()
    r["quotes"] = [{"text": "飞龙在天，利见大人", "cite_id": "zhouyi:1:yao:4"}]
    assert any("原文不符" in e for e in validate(r, ALLOWED))


def test_unknown_cite_id_rejected():
    r = _ok_result()
    r["quotes"][0]["cite_id"] = "zhouyi:2:guaci"
    assert any("不在本次给定文本" in e for e in validate(r, ALLOWED))


def test_interpretation_cite_mark_checked():
    r = _ok_result()
    r["interpretation"] = "文字 [tuan:99]"
    assert any("tuan:99" in e for e in validate(r, ALLOWED))


def test_missing_field_rejected():
    r = _ok_result()
    del r["advice"]
    assert any("缺少字段" in e for e in validate(r, ALLOWED))


def test_empty_quotes_rejected():
    r = _ok_result()
    r["quotes"] = []
    assert validate(r, ALLOWED) != []
