"""引文校验器测试：幻觉闸门必须挡住不实引文、越界出处与语境立断。"""

from tianwen.validator import normalize, validate, validate_followup

ALLOWED = {
    "zhouyi:1:yao:4": "或跃在渊，无咎。",
    "xiaoxiang:1:4": "“或跃在渊”，进无咎也。",
}


def _ok_result():
    return {
        "conclusion": "现在可以试着往前迈一步，没有大碍。",
        "judgment": "宜进，无咎。[zhouyi:1:yao:4]",
        "reasons": "解读文字 [zhouyi:1:yao:4]",
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


def test_reasons_cite_mark_checked():
    r = _ok_result()
    r["reasons"] = "文字 [tuan:99]"
    assert any("tuan:99" in e for e in validate(r, ALLOWED))


def test_missing_field_rejected():
    r = _ok_result()
    del r["advice"]
    assert any("缺少字段" in e for e in validate(r, ALLOWED))


def test_judgment_required():
    r = _ok_result()
    del r["judgment"]
    assert any("judgment" in e for e in validate(r, ALLOWED))


def test_conclusion_required_and_plain():
    r = _ok_result()
    del r["conclusion"]
    assert any("conclusion" in e for e in validate(r, ALLOWED))
    # 白话结论不得夹带 cite 标注（结论先行，面向不识古文的用户）
    r = _ok_result()
    r["conclusion"] = "可以往前走。[zhouyi:1:yao:4]"
    assert any("纯白话" in e for e in validate(r, ALLOWED))


def test_judgment_without_cite_rejected():
    # 无据不断：断语必须标注所据 cite_id
    r = _ok_result()
    r["judgment"] = "大吉大利，放手去做。"
    assert any("无据不断" in e for e in validate(r, ALLOWED))


def test_judgment_out_of_pool_cite_rejected():
    r = _ok_result()
    r["judgment"] = "宜进。[zhouyi:99:guaci]"
    assert any("断语" in e and "zhouyi:99:guaci" in e
               for e in validate(r, ALLOWED))


def test_judgment_must_ground_in_primary():
    # 主断唯一（ALGORITHM.md 五）：断语所据须落在主断侧文本上，
    # 语境侧（如姓名卦、紫微断语）可引不可断
    allowed = {**ALLOWED, "ziwei:2:ming:ziwei": "紫微守命……"}
    primary = frozenset(ALLOWED)
    r = _ok_result()
    r["judgment"] = "势强宜进。[ziwei:2:ming:ziwei]"
    assert any("主断侧" in e for e in validate(r, allowed, primary))
    # 主断侧有据即可，语境可并引
    r["judgment"] = "宜进。[zhouyi:1:yao:4][ziwei:2:ming:ziwei]"
    assert validate(r, allowed, primary) == []


def test_judgment_shuogua_alone_rejected():
    # 说卦取象不得单独立断（primary 缺省时同样生效）
    allowed = {**ALLOWED, "shuogua:11:li": "离为火……"}
    r = _ok_result()
    r["judgment"] = "宜进。[shuogua:11:li]"
    assert any("不得单独立断" in e for e in validate(r, allowed))


def test_empty_quotes_rejected():
    r = _ok_result()
    r["quotes"] = []
    assert validate(r, ALLOWED) != []


# ── 畸形结构：作校验错误反馈，不得抛异常 ──────────────────────


def test_reasons_as_string_list_coerced():
    # deepseek 等模型常把多段 reasons 输出为字符串数组：语义等同，合并收下
    r = _ok_result()
    r["reasons"] = ["第一段 [zhouyi:1:yao:4]", "第二段 [xiaoxiang:1:4]"]
    assert validate(r, ALLOWED) == []
    assert r["reasons"] == "第一段 [zhouyi:1:yao:4]\n\n第二段 [xiaoxiang:1:4]"


def test_reasons_wrong_type_reported_not_raised():
    for bad in (["段落", ["嵌套数组"]], [{"text": "对象"}], 42, {"a": 1}):
        r = _ok_result()
        r["reasons"] = bad
        assert any("reasons 须为单个字符串" in e for e in validate(r, ALLOWED))


def test_judgment_and_conclusion_wrong_type_reported():
    r = _ok_result()
    r["judgment"] = ["宜进。[zhouyi:1:yao:4]"]
    assert any("judgment 须为单个字符串" in e for e in validate(r, ALLOWED))
    r = _ok_result()
    r["conclusion"] = {"text": "可以走"}
    assert any("conclusion 须为单个字符串" in e for e in validate(r, ALLOWED))


def test_advice_items_must_be_strings():
    r = _ok_result()
    r["advice"] = [{"tip": "建议"}, "建议二"]
    assert validate(r, ALLOWED) == ["advice 须为字符串数组"]


def test_quote_items_wrong_type_reported():
    r = _ok_result()
    r["quotes"] = [{"text": ["或跃在渊"], "cite_id": "zhouyi:1:yao:4"}]
    assert any("须含字符串字段" in e for e in validate(r, ALLOWED))


def test_followup_answer_wrong_type_reported():
    r = {"answer": ["回答"], "quotes": []}
    assert validate_followup(r, ALLOWED) != []


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
