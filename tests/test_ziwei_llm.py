"""命引擎解读层测试：payload 结构、允许文本集合、引文校验联动。"""

from datetime import datetime

import pytest

from yijing_agent.validator import validate, validate_followup
from yijing_agent.ziwei import chart, selection
from yijing_agent.ziwei import llm as zllm
from yijing_agent.ziwei.knowledge import ZiweiKB


@pytest.fixture(scope="module")
def env():
    zkb = ZiweiKB()
    c = chart.cast(datetime(2000, 9, 14, 12, 0), "男")
    at = datetime(2026, 8, 24)
    sel = selection.select_fortune(zkb, c, at)
    vd = selection.decide_fortune(c, at)
    return zkb, c, sel, vd


def test_allowed_texts(env):
    zkb, c, sel, vd = env
    allowed = zllm._allowed_texts(zkb, sel)
    assert "ziwei:2:ming:jumen:xian" in allowed
    assert "ziwei:3:daxian" in allowed
    assert "ziwei:1:wenda:jumen" in allowed


def test_payload_structure(env):
    zkb, c, sel, vd = env
    from yijing_agent import topic
    tp = topic.classify("我今年运势如何")
    allowed = zllm._allowed_texts(zkb, sel)
    p = zllm._payload("我今年运势如何", c, sel, vd, allowed, zkb, tp)
    assert "【命盘】" in p and "非典籍原文" in p
    assert "【所据断语】" in p
    assert "土五局" in p
    assert "命宫（己卯" in p            # 十二宫概要逐宫列出
    assert "[ziwei:2:ming:jumen:xian]" in p
    assert "【结论（规则已定，不得更改）】中" in p
    assert "【问事类别与解读落点】" in p


def test_quote_validation_pass(env):
    zkb, c, sel, vd = env
    allowed = zllm._allowed_texts(zkb, sel)
    result = {
        "translation": "白话",
        "interpretation": "解读段落 [ziwei:3:daxian]",
        "advice": ["建议一", "建议二"],
        "quotes": [{"text": "巨门主限化权星，最喜求谋万事成",
                    "cite_id": "ziwei:2:ming:jumen:xian"}],
    }
    assert validate(result, allowed) == []


def test_quote_validation_rejects_fabrication(env):
    zkb, c, sel, vd = env
    allowed = zllm._allowed_texts(zkb, sel)
    bad = {
        "translation": "白话",
        "interpretation": "解读 [ziwei:3:daxian]",
        "advice": ["建议"],
        "quotes": [{"text": "巨门守财帛必大富", "cite_id": "ziwei:2:ming:jumen:xian"}],
    }
    errs = validate(bad, allowed)
    assert errs and "逐字照抄" in errs[0]


def test_followup_messages(env, monkeypatch):
    zkb, c, sel, vd = env
    captured = {}

    def fake_loop(cfg, messages, allowed, check, *a, **kw):
        captured["messages"] = messages
        captured["check"] = check
        return {"answer": "答", "quotes": []}, 1

    monkeypatch.setattr(zllm, "_attempt_loop", fake_loop)
    first = {"translation": "t", "interpretation": "i", "advice": ["a"],
             "quotes": []}
    zllm.followup_chart({}, zkb, "问", c, sel, vd, first,
                        [("前问", {"answer": "前答", "quotes": []})], "新问")
    msgs = captured["messages"]
    assert captured["check"] is validate_followup
    assert msgs[0]["role"] == "system" and "紫微斗数全书" in msgs[0]["content"]
    # 追问规则只注入第一轮追问
    rules_count = sum(1 for m in msgs if "不重新排盘" in m.get("content", ""))
    assert rules_count == 1
    assert msgs[-1]["content"].endswith("【追问】新问")
