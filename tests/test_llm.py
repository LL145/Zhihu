"""解读生成层测试（mock OpenRouter，不发真实请求）。"""

import json
from datetime import datetime

import pytest

from yijing_agent import casting, llm, selection, verdict
from yijing_agent.knowledge import KnowledgeBase

kb = KnowledgeBase()
CFG = {"api_key": "test", "model": "test/model", "base_url": "https://example.invalid/api/v1"}


def _fixture():
    cast = casting.cast_meihua(datetime(2026, 8, 24, 15, 30))
    ben, zhi = kb.id_of(cast.ben_binary), kb.id_of(cast.zhi_binary)
    sel = selection.select(kb, cast.method, ben, zhi, cast.moving)
    vd = verdict.decide(sel.primary.cite_id, kb.citation(sel.primary.cite_id)["text"])
    return cast, sel, vd


def _good_payload():
    # 革九五「大人虎变，未占有孚。」
    return {
        "translation": "白话直译",
        "interpretation": "解读段落。[zhouyi:49:yao:5]",
        "advice": ["建议一", "建议二"],
        "quotes": [{"text": "大人虎变", "cite_id": "zhouyi:49:yao:5"}],
    }


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def json(self):
        return {"choices": [{"message": {"content": self._payload}}]}


def test_valid_response_passes(monkeypatch):
    cast, sel, vd = _fixture()
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(json.dumps(_good_payload(), ensure_ascii=False)))
    result, attempts = llm.interpret(CFG, kb, "问事", cast, sel, vd)
    assert attempts == 1
    assert result["quotes"][0]["cite_id"] == "zhouyi:49:yao:5"


def test_fabricated_quote_triggers_retry_then_success(monkeypatch):
    cast, sel, vd = _fixture()
    bad = _good_payload()
    bad["quotes"] = [{"text": "飞龙在天", "cite_id": "zhouyi:49:yao:5"}]
    responses = [json.dumps(bad, ensure_ascii=False),
                 json.dumps(_good_payload(), ensure_ascii=False)]
    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        # 重试请求须携带校验失败原因
        if calls["n"] == 2:
            last = k["json"]["messages"][-1]["content"]
            assert "原文不符" in last
        return _Resp(responses[calls["n"] - 1])

    monkeypatch.setattr(llm.requests, "post", fake_post)
    result, attempts = llm.interpret(CFG, kb, "问事", cast, sel, vd)
    assert attempts == 2


def test_three_failures_raise(monkeypatch):
    cast, sel, vd = _fixture()
    bad = _good_payload()
    bad["quotes"] = [{"text": "编造的引文", "cite_id": "zhouyi:49:yao:5"}]
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(json.dumps(bad, ensure_ascii=False)))
    with pytest.raises(llm.InterpreterError) as ei:
        llm.interpret(CFG, kb, "问事", cast, sel, vd)
    assert ei.value.errors


def test_markdown_fenced_json_parsed(monkeypatch):
    cast, sel, vd = _fixture()
    fenced = "```json\n" + json.dumps(_good_payload(), ensure_ascii=False) + "\n```"
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp(fenced))
    result, attempts = llm.interpret(CFG, kb, "问事", cast, sel, vd)
    assert attempts == 1


def test_http_error_raises(monkeypatch):
    cast, sel, vd = _fixture()

    class _Err:
        status_code = 401
        text = "unauthorized"

    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Err())
    with pytest.raises(llm.InterpreterError):
        llm.interpret(CFG, kb, "问事", cast, sel, vd)
