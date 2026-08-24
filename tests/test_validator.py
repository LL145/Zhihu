"""引文校验器测试：幻觉闸门必须挡住不实引文与越界出处。"""

from yijing_agent.validator import normalize, validate, validate_followup

ALLOWED = {
    "zhouyi:1:yao:4": "或跃在渊，无咎。",
    "xiaoxiang:1:4": "“或跃在渊”，进无咎也。",
}


def _ok_result():
    return {
        "translation": "白话",
        "judgment": "宜进，无咎。[zhouyi:1:yao:4]",
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


def test_judgment_required():
    r = _ok_result()
    del r["judgment"]
    assert any("judgment" in e for e in validate(r, ALLOWED))


def test_judgment_without_cite_rejected():
    # 无据不断：占断必须标注所据 cite_id
    r = _ok_result()
    r["judgment"] = "大吉大利，放手去做。"
    assert any("无据不断" in e for e in validate(r, ALLOWED))


def test_judgment_out_of_pool_cite_rejected():
    r = _ok_result()
    r["judgment"] = "宜进。[zhouyi:99:guaci]"
    assert any("占断" in e and "zhouyi:99:guaci" in e
               for e in validate(r, ALLOWED))


def test_empty_quotes_rejected():
    r = _ok_result()
    r["quotes"] = []
    assert validate(r, ALLOWED) != []


# ── 追问回答校验 ──────────────────────────────


def test_followup_valid_with_quote():
    r = {"answer": "回答 [zhouyi:1:yao:4]",
         "quotes": [{"text": "或跃在渊", "cite_id": "zhouyi:1:yao:4"}]}
    assert validate_followup(r, ALLOWED) == []


def test_followup_empty_quotes_allowed():
    r = {"answer": "此问须另占，本卦文本无从作答。", "quotes": []}
    assert validate_followup(r, ALLOWED) == []


def test_followup_fabricated_quote_rejected():
    r = {"answer": "回答",
         "quotes": [{"text": "潜龙勿用", "cite_id": "zhouyi:1:yao:4"}]}
    assert any("原文不符" in e for e in validate_followup(r, ALLOWED))


def test_followup_answer_cite_mark_checked():
    r = {"answer": "回答 [tuan:99]", "quotes": []}
    assert any("tuan:99" in e for e in validate_followup(r, ALLOWED))


def test_followup_missing_answer_rejected():
    assert validate_followup({"quotes": []}, ALLOWED) != []
