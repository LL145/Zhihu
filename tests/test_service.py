"""双引擎门面（service.py）测试：路由、红线、会话状态与解读接线。"""

from datetime import datetime

import pytest

from yijing_agent import service

WHEN = datetime(2026, 8, 24, 11, 0)
BIRTH = datetime(2000, 9, 14, 12, 0)


def test_event_routing():
    s = service.prepare("近期换工作是否合适", when=WHEN)
    assert isinstance(s, service.EventSession) and s.kind == "event"
    body = s.body_text()
    assert "所问：近期换工作是否合适" in body
    assert "引擎：易经事引擎" in body
    assert "类别：事业" in body
    assert "断辞结论" in body
    assert "起卦凭证" in s.repro_text()


def test_chart_routing_with_birth():
    s = service.prepare("我今年运势如何", when=WHEN, birth_dt=BIRTH, gender="男")
    assert isinstance(s, service.ChartSession) and s.kind == "chart"
    body = s.body_text()
    assert "引擎：紫微命引擎" in body
    assert "命宫·身 己卯" in body          # 十二宫盘面
    assert "巨门入限吉凶诀" in body
    assert "排盘凭证" in s.repro_text()


def test_chart_topic_without_birth_falls_back():
    s = service.prepare("我今年运势如何", when=WHEN)
    assert isinstance(s, service.EventSession)
    assert "欲以紫微命盘作答" in s.body_text()


def test_event_topic_with_birth_gets_hecan_context():
    # 卦断事：问具体事即便给了生辰也走事引擎——命盘只作合参语境（§6.2）
    s = service.prepare("近期换工作是否合适", when=WHEN,
                        birth_dt=BIRTH, gender="男")
    assert isinstance(s, service.EventSession)
    assert s.context is not None
    body = s.body_text()
    assert "合参语境" in body and "官禄宫" in body
    assert "不出第二结论" in body


def test_event_without_birth_has_no_context():
    s = service.prepare("近期换工作是否合适", when=WHEN)
    assert s.context is None
    assert "合参语境" not in s.body_text()


def test_hecan_context_wired_into_llm(monkeypatch):
    s = service.prepare("近期换工作是否合适", when=WHEN,
                        birth_dt=BIRTH, gender="男")
    seen = {}

    def fake_interpret(cfg, kb, question, cast, sel, vd, tp, context=None,
                       **kw):
        seen["context"] = context
        return {"translation": "白", "judgment": "断 [x:1]",
                "interpretation": "解", "advice": ["议"], "quotes": []}, 1

    monkeypatch.setattr(service, "_interpret", fake_interpret)
    s.interpret({"model": "m"})
    assert seen["context"] is s.context and s.context is not None


def test_chart_fortune_aspect_palace():
    # 问财运：命引擎加取财帛宫断语（问事分宫）
    s = service.prepare("我今年财运如何", when=WHEN, birth_dt=BIRTH, gender="男")
    assert isinstance(s, service.ChartSession)
    body = s.body_text()
    assert "所问之宫：财帛宫" in body


def test_refusal_and_empty():
    with pytest.raises(service.RefusalError):
        service.prepare("我该买哪只股票")
    with pytest.raises(ValueError):
        service.prepare("   ")


def test_resolve_topic_three_tiers(monkeypatch):
    # 一级：用户指定最优先，纵关键词命中他类
    t = service.resolve_topic("近期换工作是否合适", override="love")
    assert t.name == "情感" and t.source == "user"
    # 二级：规则命中即不调模型
    def boom(*a, **k):
        raise AssertionError("规则命中时不得调用占者判类")
    monkeypatch.setattr(service, "_classify_topic", boom)
    t = service.resolve_topic("近期换工作是否合适",
                              cfg={"api_key": "k", "model": "m"})
    assert t.name == "事业" and t.source == "rule"
    # 三级：规则未中且配了模型 → 占者判类，来源标注
    monkeypatch.setattr(service, "_classify_topic", lambda cfg, q: "love")
    t = service.resolve_topic("她最近老不理我怎么办",
                              cfg={"api_key": "k", "model": "m"})
    assert t.name == "情感" and t.source == "llm"
    # 判类失败回落「其他」；无 cfg 不调模型
    monkeypatch.setattr(service, "_classify_topic", lambda cfg, q: None)
    assert service.resolve_topic("她最近老不理我怎么办",
                                 cfg={"api_key": "k"}).key == "other"
    monkeypatch.setattr(service, "_classify_topic", boom)
    assert service.resolve_topic("她最近老不理我怎么办").key == "other"
    # 红线仍先行
    with pytest.raises(service.RefusalError):
        service.resolve_topic("我该买哪只股票", override="career")


def test_resolved_topic_flows_into_session():
    tp = service.resolve_topic("她最近老不理我怎么办", override="love")
    s = service.prepare("她最近老不理我怎么办", when=WHEN, tp=tp)
    assert isinstance(s, service.EventSession)
    assert "类别：情感〔用户指定〕" in s.body_text()


def test_coin_method_deterministic():
    a = service.prepare("某事", method="coin", when=WHEN)
    b = service.prepare("某事", method="coin", when=WHEN)
    assert a.body_text() == b.body_text()


def test_followup_requires_interpret():
    s = service.prepare("近期换工作是否合适", when=WHEN)
    with pytest.raises(RuntimeError):
        s.followup({}, "再问一句")


def test_interpret_and_followup_wiring(monkeypatch):
    s = service.prepare("我今年运势如何", when=WHEN, birth_dt=BIRTH, gender="男")
    fake = {"translation": "白话", "judgment": "占断 [ziwei:3:daxian]",
            "interpretation": "解读 [ziwei:3:daxian]",
            "advice": ["建议"], "quotes": []}

    monkeypatch.setattr(service.zllm, "interpret_chart",
                        lambda *a, **k: (fake, 1))
    text, attempts = s.interpret({"model": "m"})
    assert attempts == 1 and "白话" in text
    assert "〔占断〕" in text                       # 占者之断置于解读之首
    assert "占断存证" in text and "SHA-256" in text  # 有条件可复现：输出留痕
    assert s.first_result is fake

    seen = {}

    def fake_fu(cfg, zkb, question, chart, sel, vd, first, history, ask, tp,
                **kw):
        seen["first"], seen["history"], seen["ask"] = first, list(history), ask
        return {"answer": "答", "quotes": []}, 1

    monkeypatch.setattr(service.zllm, "followup_chart", fake_fu)
    out = s.followup({}, "细说")
    assert "答" in out
    assert seen["first"] is fake and seen["ask"] == "细说"
    assert seen["history"] == []
    s.followup({}, "再细说")
    assert seen["history"][0][0] == "细说"    # 历史逐轮累积

    # 追问逐问过红线
    with pytest.raises(service.RefusalError):
        s.followup({}, "帮我看看这个病能不能好")
