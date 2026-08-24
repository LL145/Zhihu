"""卦盘并占（两问两断）测试：路由、并陈结构、两池隔离、降级与追问。"""

from datetime import datetime

import pytest

from yijing_agent import selection, service, topic
from yijing_agent.llm import InterpreterError

BIRTH = datetime(2000, 9, 14, 12)
WHEN = datetime(2026, 8, 24, 15, 30)
CFG = {"api_key": "k", "model": "test/model", "base_url": "https://x.invalid"}


def _dual():
    return service.prepare("我今年财运如何", when=WHEN,
                           birth_dt=BIRTH, gender="男", both=True)


def _fake_event_result():
    return {"translation": "白话", "judgment": "宜守。[zhouyi:1:yao:1]",
            "interpretation": "解读。[zhouyi:1:yao:1]", "advice": ["建议"],
            "quotes": [{"text": "潜龙勿用", "cite_id": "zhouyi:1:yao:1"}]}


def _fake_chart_result():
    return {"translation": "白话", "judgment": "势平。[ziwei:3:daxian]",
            "interpretation": "解读。[ziwei:3:daxian]", "advice": ["建议"],
            "quotes": [{"text": "成败不一", "cite_id": "ziwei:3:daxian"}]}


# ── 路由 ────────────────────────────────


def test_routing():
    s = _dual()
    assert s.kind == "dual"
    # 不开开关 → 照常盘断
    assert service.prepare("我今年财运如何", when=WHEN, birth_dt=BIRTH,
                           gender="男").kind == "chart"
    # 事问开了开关也不并占（合参已覆盖该场景）
    assert service.prepare("近期换工作是否合适", when=WHEN, birth_dt=BIRTH,
                           gender="男", both=True).kind == "event"
    # 命理问缺生辰 → 开关静默不生效，照常退回事引擎
    assert service.prepare("我今年财运如何", when=WHEN,
                           both=True).kind == "event"


# ── 并陈结构与两池隔离 ────────────────────


def test_body_structure():
    s = _dual()
    body = s.body_text()
    assert "并陈，不合断" in body
    assert "盘断其势" in body and "卦断其事" in body
    assert body.count("断辞结论（定例·机断）") == 2   # 两份定例对照
    assert "合参语境" not in body                      # 卦侧不再附盘语境
    assert "欲以紫微命盘作答" not in body              # 生辰提示不出现
    assert "所问：" in body and body.count("所问：") == 1
    repro = s.repro_text()
    assert "排盘凭证" in repro and "起卦凭证" in repro


def test_event_side_gets_zhan_by_aspect():
    # 时运类无占章映射，按题材（财→财帛）回落到求财占
    s = _dual()
    ids = [r.cite_id for r in s.event.sel.readings]
    assert "meihua:2:zhan:qiucai" in ids
    # 直接验证回落函数：占者判类出的时运 + 发财问法
    sel = selection.select_meihua(
        s.event.kb, 49, 55, 5, topic.by_key("fortune", source="llm"),
        "我能发财吗")
    assert any(r.cite_id == "meihua:2:zhan:qiucai" for r in sel.readings)


def test_pools_are_isolated(monkeypatch):
    """两侧解读各自调用、各在各的池：盘侧只见紫微文本，卦侧只见易文本。"""
    seen = {}

    def fake_event(cfg, kb, q, cast, sel, vd, tp=None, context=None, **kw):
        seen["event_ctx"] = context
        return _fake_event_result(), 1

    def fake_chart(cfg, zkb, q, chart, sel, vd, tp=None, **kw):
        seen["chart"] = True
        return _fake_chart_result(), 1

    monkeypatch.setattr(service, "_interpret", fake_event)
    monkeypatch.setattr(service.zllm, "interpret_chart", fake_chart)
    s = _dual()
    text, attempts = s.interpret(CFG)
    assert seen["event_ctx"] is None      # 卦侧不带盘语境
    assert seen["chart"]
    assert attempts == 2
    assert "【盘·占断（论势）】" in text and "【卦·占断（断事）】" in text
    assert text.count("占断存证") == 2     # 各自存证


def test_one_side_failure_degrades(monkeypatch):
    monkeypatch.setattr(service, "_interpret",
                        lambda *a, **k: (_ for _ in ()).throw(
                            InterpreterError("卦侧三次未过")))
    monkeypatch.setattr(service.zllm, "interpret_chart",
                        lambda *a, **k: (_fake_chart_result(), 1))
    s = _dual()
    text, attempts = s.interpret(CFG)
    assert "本侧降级" in text and "势平" in text
    assert s.first_result is not None     # 盘侧成功即可追问


def test_both_sides_failure_raises(monkeypatch):
    boom = lambda *a, **k: (_ for _ in ()).throw(InterpreterError("未过"))
    monkeypatch.setattr(service, "_interpret", boom)
    monkeypatch.setattr(service.zllm, "interpret_chart", boom)
    with pytest.raises(InterpreterError):
        _dual().interpret(CFG)


def test_followup_answers_both(monkeypatch):
    monkeypatch.setattr(service, "_interpret",
                        lambda *a, **k: (_fake_event_result(), 1))
    monkeypatch.setattr(service.zllm, "interpret_chart",
                        lambda *a, **k: (_fake_chart_result(), 1))
    s = _dual()
    s.interpret(CFG)
    monkeypatch.setattr(service, "_followup",
                        lambda *a, **k: ({"answer": "卦答", "quotes": []}, 1))
    monkeypatch.setattr(service.zllm, "followup_chart",
                        lambda *a, **k: ({"answer": "盘答", "quotes": []}, 1))
    out = s.followup(CFG, "那要注意什么")
    assert "【盘】" in out and "【卦】" in out
    assert "盘答" in out and "卦答" in out


def test_followup_redline_refused():
    s = _dual()
    with pytest.raises(service.RefusalError):
        s.followup(CFG, "我该吃什么药能治好病")
