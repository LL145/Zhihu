"""解读生成层测试（mock OpenRouter，不发真实请求）。"""

import json
from datetime import datetime

import pytest

from yijing_agent import casting, llm, selection, topic, verdict
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


def test_topic_note_in_payload_and_marked_non_scripture(monkeypatch):
    cast, sel, vd = _fixture()
    tp = topic.classify("近期换一份工作是否合适")
    seen = {}

    def fake_post(*a, **k):
        seen["payload"] = k["json"]["messages"][1]["content"]
        return _Resp(json.dumps(_good_payload(), ensure_ascii=False))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    llm.interpret(CFG, kb, "近期换一份工作是否合适", cast, sel, vd, tp)
    assert "事业" in seen["payload"] and tp.note in seen["payload"]
    assert "非典籍原文" in seen["payload"]


def test_hecan_context_in_payload_and_quotes_validate(monkeypatch):
    # 合参（§6.2）：紫微断语进 payload 作语境，其引文过两库混合校验
    from yijing_agent.ziwei import chart as zchart
    from yijing_agent.ziwei import selection as zselection
    from yijing_agent.ziwei.knowledge import ZiweiKB

    cast, sel, vd = _fixture()
    q = "近期换一份工作是否合适"
    tp = topic.classify(q)
    zkb = ZiweiKB()
    csel = zselection.select_context(
        zkb, zchart.cast(datetime(2000, 9, 14, 12, 0), "男"), tp, q)
    cid = csel.readings[0].cite_id
    ztext = zkb.citation(cid)["text"]

    good = _good_payload()
    good["quotes"].append({"text": ztext[:6], "cite_id": cid})
    seen = {}

    def fake_post(*a, **k):
        seen["payload"] = k["json"]["messages"][1]["content"]
        return _Resp(json.dumps(good, ensure_ascii=False))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    result, attempts = llm.interpret(CFG, kb, q, cast, sel, vd, tp,
                                     context=(zkb, csel))
    assert attempts == 1
    assert "【合参语境】" in seen["payload"] and cid in seen["payload"]
    assert "不得据以改动结论" in seen["payload"]


def test_hecan_fabricated_ziwei_quote_rejected(monkeypatch):
    # 合参引文同样逐字校验：伪造的紫微断语不放行
    from yijing_agent.ziwei import chart as zchart
    from yijing_agent.ziwei import selection as zselection
    from yijing_agent.ziwei.knowledge import ZiweiKB

    cast, sel, vd = _fixture()
    q = "近期换一份工作是否合适"
    tp = topic.classify(q)
    zkb = ZiweiKB()
    csel = zselection.select_context(
        zkb, zchart.cast(datetime(2000, 9, 14, 12, 0), "男"), tp, q)
    cid = csel.readings[0].cite_id

    bad = _good_payload()
    bad["quotes"].append({"text": "紫微入官禄大富大贵", "cite_id": cid})
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(json.dumps(bad, ensure_ascii=False)))
    with pytest.raises(llm.InterpreterError):
        llm.interpret(CFG, kb, q, cast, sel, vd, tp, context=(zkb, csel))


# ── 多轮追问 ──────────────────────────────


def _good_followup():
    return {"answer": "追问回答。[zhouyi:49:yao:5]",
            "quotes": [{"text": "未占有孚", "cite_id": "zhouyi:49:yao:5"}]}


def test_followup_valid_passes(monkeypatch):
    cast, sel, vd = _fixture()
    seen = {}

    def fake_post(*a, **k):
        seen["messages"] = k["json"]["messages"]
        return _Resp(json.dumps(_good_followup(), ensure_ascii=False))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    result, attempts = llm.followup(CFG, kb, "问事", cast, sel, vd,
                                    _good_payload(), [], "如果拖到年底再动呢")
    assert attempts == 1 and result["answer"]
    # 会话须含：原始解读（assistant）、追问规则、本轮追问
    assert seen["messages"][2]["role"] == "assistant"
    assert "追问回答的硬性规则" in seen["messages"][3]["content"]
    assert "如果拖到年底再动呢" in seen["messages"][3]["content"]


def test_followup_empty_quotes_ok(monkeypatch):
    cast, sel, vd = _fixture()
    resp = {"answer": "此问须另占，本卦文本无从作答。", "quotes": []}
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(json.dumps(resp, ensure_ascii=False)))
    result, attempts = llm.followup(CFG, kb, "问事", cast, sel, vd,
                                    _good_payload(), [], "另一件事如何")
    assert attempts == 1


def test_followup_fabricated_quote_retries(monkeypatch):
    cast, sel, vd = _fixture()
    bad = {"answer": "回答", "quotes": [{"text": "飞龙在天", "cite_id": "zhouyi:49:yao:5"}]}
    responses = [json.dumps(bad, ensure_ascii=False),
                 json.dumps(_good_followup(), ensure_ascii=False)]
    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            assert "原文不符" in k["json"]["messages"][-1]["content"]
        return _Resp(responses[calls["n"] - 1])

    monkeypatch.setattr(llm.requests, "post", fake_post)
    result, attempts = llm.followup(CFG, kb, "问事", cast, sel, vd,
                                    _good_payload(), [], "追问")
    assert attempts == 2


def test_followup_history_in_conversation(monkeypatch):
    cast, sel, vd = _fixture()
    seen = {}

    def fake_post(*a, **k):
        seen["messages"] = k["json"]["messages"]
        return _Resp(json.dumps(_good_followup(), ensure_ascii=False))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    history = [("上一轮追问", {"answer": "上一轮回答", "quotes": []})]
    llm.followup(CFG, kb, "问事", cast, sel, vd, _good_payload(), history, "本轮追问")
    contents = [m["content"] for m in seen["messages"]]
    assert any("上一轮追问" in c for c in contents)
    assert any("上一轮回答" in c for c in contents)
    assert "本轮追问" in contents[-1]
    # 追问规则只在首轮追问出现一次
    assert sum("追问回答的硬性规则" in c for c in contents) == 1
