"""解读生成层测试（mock OpenRouter，不发真实请求）。"""

import json
from datetime import datetime

import pytest

from tianwen import casting, llm, selection, topic, verdict
from tianwen.knowledge import KnowledgeBase

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
        "conclusion": "此事可以放手去做，变革之势对你有利。",
        "judgment": "宜进，其变可孚。[zhouyi:49:yao:5]",
        "reasons": "解读段落。[zhouyi:49:yao:5]",
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


def test_classify_topic(monkeypatch):
    # 占者判类：温度 0、键须在类别表内、任何异常回落 None
    seen = {}

    def fake_post(*a, **k):
        seen["temp"] = k["json"]["temperature"]
        seen["user"] = k["json"]["messages"][1]["content"]
        return _Resp('{"key": "love"}')

    monkeypatch.setattr(llm.requests, "post", fake_post)
    assert llm.classify_topic(CFG, "她最近老不理我怎么办") == "love"
    assert seen["temp"] == 0 and "情感" in seen["user"]

    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp('{"key": "nonsense"}'))
    assert llm.classify_topic(CFG, "问") is None

    def raise_net(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(llm.requests, "post", raise_net)
    assert llm.classify_topic(CFG, "问") is None


def _ziwei_context_block():
    from tianwen.ziwei import chart as zchart
    from tianwen.ziwei import selection as zselection
    from tianwen.ziwei.knowledge import ZiweiKB

    q = "近期换一份工作是否合适"
    tp = topic.classify(q)
    zkb = ZiweiKB()
    csel = zselection.select_context(
        zkb, zchart.cast(datetime(2000, 9, 14, 12, 0), "男"), tp, q)
    items = [(r.cite_id, zkb.citation(r.cite_id)["source"],
              zkb.citation(r.cite_id)["text"]) for r in csel.readings]
    return q, tp, llm.ContextBlock("紫微盘（论秉性禀赋）",
                                   list(csel.notes), items)


def test_context_block_in_payload_and_quotes_validate(monkeypatch):
    # 语境合参（ALGORITHM.md 五）：紫微断语进 payload 作语境，
    # 其引文过混合校验
    cast, sel, vd = _fixture()
    q, tp, blk = _ziwei_context_block()
    cid = blk.items[0][0]
    ztext = blk.items[0][2]

    good = _good_payload()
    good["quotes"].append({"text": ztext[:6], "cite_id": cid})
    seen = {}

    def fake_post(*a, **k):
        seen["payload"] = k["json"]["messages"][1]["content"]
        return _Resp(json.dumps(good, ensure_ascii=False))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    result, attempts = llm.interpret(CFG, kb, q, cast, sel, vd, tp,
                                     contexts=[blk])
    assert attempts == 1
    assert "【语境·紫微盘（论秉性禀赋）】" in seen["payload"]
    assert cid in seen["payload"]
    assert "不得据以改动结论" in seen["payload"]


def test_context_fabricated_quote_rejected(monkeypatch):
    # 语境引文同样逐字校验：伪造的紫微断语不放行
    cast, sel, vd = _fixture()
    q, tp, blk = _ziwei_context_block()
    cid = blk.items[0][0]

    bad = _good_payload()
    bad["quotes"].append({"text": "紫微入官禄大富大贵", "cite_id": cid})
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(json.dumps(bad, ensure_ascii=False)))
    with pytest.raises(llm.InterpreterError):
        llm.interpret(CFG, kb, q, cast, sel, vd, tp, contexts=[blk])


def test_context_cannot_ground_judgment(monkeypatch):
    # 主断唯一：断语只落在语境文本上 → 拒绝（吉凶只有一个出处）
    cast, sel, vd = _fixture()
    q, tp, blk = _ziwei_context_block()
    cid = blk.items[0][0]

    bad = _good_payload()
    bad["judgment"] = f"势强宜进。[{cid}]"
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(json.dumps(bad, ensure_ascii=False)))
    with pytest.raises(llm.InterpreterError) as ei:
        llm.interpret(CFG, kb, q, cast, sel, vd, tp, contexts=[blk])
    assert any("主断侧" in e for e in ei.value.errors)


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
