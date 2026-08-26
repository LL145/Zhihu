"""单一模式门面（service.py）测试：路由、三占同起、语境合参、
主断唯一与结论先行的渲染（ALGORITHM.md）。"""

from datetime import datetime

import pytest

from tianwen import service

WHEN = datetime(2026, 8, 24, 11, 0)
BIRTH = datetime(2000, 9, 14, 12, 0)


def _full(**kw):
    kw.setdefault("name", "李明")
    kw.setdefault("birth_dt", BIRTH)
    kw.setdefault("gender", "男")
    kw.setdefault("when", WHEN)
    return service.prepare(kw.pop("question", "近期换工作是否合适"), **kw)


# ── 路由与三占同起 ────────────────────────


def test_event_primary_routing():
    s = _full()
    assert s.primary == "event"
    assert s.event_cast is not None and s.event_cast is not s.time_cast
    assert s.time_cast is not None and s.name_cast is not None
    assert s.chart is not None
    text = s.render_all()
    assert "所问：近期换工作是否合适" in text
    assert "类别：事业" in text
    assert text.index("【结论】") < text.index("── 卦盘一览")   # 结论先行
    assert "问语卦（主断）" in text and "书写来意" in text
    assert "时间卦（参·当下之势）" in text
    assert "姓名卦（参·论问者之位）" in text
    assert "紫微盘（语境·论禀赋）" in text
    assert "起卦凭证" in text and "排盘凭证" in text
    assert "问语起卦" in text and "字数分之" in text   # 问语卦凭证在列


def test_chart_primary_routing():
    s = _full(question="我今年运势如何")
    assert s.primary == "chart"
    text = s.render_all()
    assert "紫微盘（主断）" in text
    assert "时间卦（参·当下之势）" in text
    assert "巨门" in text                      # 大限入限诀选文
    assert text.index("【结论】") < text.index("── 卦盘一览")


def test_chart_topic_without_birth_falls_back():
    s = service.prepare("我今年运势如何", when=WHEN)
    assert s.primary == "event"
    text = s.render_all()
    assert "生辰不全" in text and "当下之势" in text


def test_missing_inputs_only_reduce_references():
    # 输入不全只减少参照，不改变流程形状（ALGORITHM.md 二）
    s = service.prepare("近期换工作是否合适", when=WHEN)
    assert s.primary == "event"
    assert s.name_cast is None and "未提供姓名" in s.name_note
    assert s.chart is None and "生辰" in s.chart_note
    text = s.render_all()
    assert "未提供姓名" in text and "无紫微盘" in text
    assert "姓名卦" not in text.split("── 卦盘一览")[1].split("──")[0]


def test_name_cast_deterministic_and_book_bound():
    # 姓名卦由字画确定，与时刻无关（meihua:1:qi:zishu）
    a = _full()
    b = _full(when=datetime(2027, 1, 1))
    assert a.name_cast.lines == b.name_cast.lines
    # 单字姓名依书须辨字形左右阴阳画：不起卦，缘由如实展示
    s = _full(name="李")
    assert s.name_cast is None
    assert "阴阳画" in s.name_note or "一字" in s.name_note
    assert s.name_note in s.render_all()


# ── 语境合参：主断唯一 ────────────────────


def test_event_contexts_include_time_name_and_ziwei():
    s = _full()
    titles = [b.title for b in s.contexts]
    assert any("时间卦" in t for t in titles)   # 恒作当下之势之参
    assert any("姓名卦" in t for t in titles)
    assert any("紫微盘" in t for t in titles)
    for b in s.contexts:
        assert b.items, b.title


def test_chart_contexts_include_time_and_name_casts():
    s = _full(question="我今年运势如何")
    titles = [b.title for b in s.contexts]
    assert any("时间卦" in t for t in titles)
    assert any("姓名卦" in t for t in titles)


def test_cast_contexts_span_scripture_commentary_and_notes():
    # 旁征博引之资：卦侧语境经（爻辞、卦辞）、传（小象、彖）、
    # 注（动爻王弼注）各备一体（可引不可断）
    for q in ("近期换工作是否合适", "我今年运势如何"):
        s = _full(question=q)
        for b in s.contexts:
            if "卦" not in b.title:
                continue    # 紫微语境块非卦侧
            cids = [cid for cid, _src, _t in b.items]
            assert any(c.startswith("zhouyi:") for c in cids), b.title
            assert any(c.startswith("xiaoxiang:") for c in cids), b.title
            assert any(c.startswith("tuan:") for c in cids), b.title
            assert any(c.startswith("wangbi:") for c in cids), b.title


def test_single_verdict_in_overview():
    # 吉凶只有一个出处：一览中「主断」标签唯一
    for q in ("近期换工作是否合适", "我今年运势如何"):
        s = _full(question=q)
        assert s.overview_text().count("主断）") == 1


def test_contexts_wired_into_llm(monkeypatch):
    s = _full()
    seen = {}

    def fake_interpret(cfg, kb, question, cast, sel, vd, tp, contexts=(),
                       **kw):
        seen["contexts"] = contexts
        return {"conclusion": "白", "judgment": "断 [x:1]", "reasons": "解",
                "advice": ["议"], "quotes": []}, 1

    monkeypatch.setattr(service, "_interpret", fake_interpret)
    s.interpret({"model": "m"})
    assert seen["contexts"] is s.contexts and len(s.contexts) == 3


def test_chart_fortune_aspect_palace():
    # 问财运：命引擎加取财帛宫断语（问事分宫）
    s = _full(question="我今年财运如何")
    assert s.primary == "chart"
    assert "所问之宫：财帛宫" in s.evidence_text()


def test_chart_desk_context_and_repro():
    # 书桌（确定性召回层）：盘为主断时按主断宫主星召回候选断语入语境，
    # 召回规则与命中数进凭证；事为主断时无书桌
    s = _full(question="我今年运势如何")
    [desk] = [b for b in s.contexts if "书桌" in b.title]
    assert desk.items and any("机械召回" in n for n in desk.notes)
    assert {star for star, _h, _t in s.desk} == {"巨门"}   # 大限福德宫主星
    for cid, _src, text in desk.items:
        assert cid.split(":")[2] in ("fu", "shideng", "ju")
        assert "巨门" in text
    repro = s.repro_text()
    assert "书桌召回" in repro and "命中" in repro and "可引不可断" in repro
    s2 = _full()
    assert s2.primary == "event"
    assert not s2.desk and not [b for b in s2.contexts if "书桌" in b.title]


def test_chart_desk_second_phase_palace_term():
    # 书桌二期：问涉具体题材时，所涉之宫名并入召回（按宫/类别）
    s = _full(question="我今年财运如何")
    assert s.primary == "chart"
    assert s.sel.desk_terms == ("财帛",)
    assert "财帛" in {q for q, _h, _t in s.desk}
    _q, hits, total = next(x for x in s.desk if x[0] == "财帛")
    assert total >= 1 and all("财帛" in ln for _cid, ln in hits)
    repro = s.repro_text()
    assert "所涉之宫财帛：命中" in repro
    assert "并所涉之宫名" in repro
    # 无题材之问不加宫名查询
    s2 = _full(question="我今年运势如何")
    assert getattr(s2.sel, "desk_terms", ()) == ()


def test_chart_fortune_liunian_in_evidence():
    # 流年二限（太岁＋小限）如实入所据断语区
    s = _full(question="我今年运势如何")
    ev = s.evidence_text()
    assert "太岁在" in ev and "小限在" in ev
    assert "二限太岁总说" in ev


# ── 问语入卦（v3.5）───────────────────────


def test_same_moment_different_questions_differ():
    # 问语入卦之本旨：同一时刻问不同事，卦随问语而异（字数定卦体）
    a = service.prepare("近期换工作是否合适", when=WHEN)   # 9字→雷风恒
    b = service.prepare("今日出门是否顺利", when=WHEN)     # 8字→震为雷
    assert a.event_cast.ben_binary != b.event_cast.ben_binary
    assert a.sel.primary.cite_id != b.sel.primary.cite_id
    assert a.event_cast.ben_binary != a.time_cast.ben_binary


def test_wenyu_fallback_without_hanzi():
    # 问语无汉字可数：时间卦代主断，缘由如实标注，时间卦语境块不重列
    s = service.prepare("ABC 123", when=WHEN)
    assert s.primary == "event" and s.event_cast is s.time_cast
    text = s.render_all()
    assert "问语卦未起" in text and "时间卦（主断）" in text
    assert not [b for b in s.contexts if "时间卦" in b.title]


# ── 红线、判类与追问 ──────────────────────


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
    assert "类别：情感〔用户指定〕" in s.render_all()


def test_followup_requires_interpret():
    s = service.prepare("近期换工作是否合适", when=WHEN)
    with pytest.raises(RuntimeError):
        s.followup({}, "再问一句")


def test_interpret_and_followup_wiring(monkeypatch):
    s = _full(question="我今年运势如何")
    fake = {"conclusion": "白话结论", "judgment": "占断 [ziwei:3:daxian]",
            "reasons": "解读 [ziwei:3:daxian]",
            "advice": ["建议"], "quotes": []}

    monkeypatch.setattr(service.zllm, "interpret_chart",
                        lambda *a, **k: (fake, 1))
    text, attempts = s.interpret({"model": "m"})
    assert attempts == 1
    assert "【结论】白话结论" in text                # 结论先行
    assert text.index("【结论】") < text.index("【断语】") < text.index("【理由】")
    assert "占断存证" in text and "SHA-256" in text  # 有条件可复现：输出留痕
    # 引文编号只在校验层流转，展示换成古籍原名
    assert "[ziwei:3:daxian]" not in text
    assert "〔《紫微斗数全书》·卷三·论大限十年祸福何如〕" in text
    assert s.first_result is fake

    seen = {}

    def fake_fu(cfg, zkb, question, chart, sel, vd, first, history, ask, tp,
                contexts=(), **kw):
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


def test_degraded_conclusion_first():
    # 无模型：结论直取定例断辞，仍结论先行
    s = _full()
    text = s.render_all()
    assert text.index("【结论】") < text.index("【理由】")
    assert "定例断辞" in text
    assert "── 起卦凭证" in text and "※ " in text


def test_citations_render_as_book_names():
    # 展示层 humanize：内部编号 → 古籍原名；未知编号原样保留不吞不改
    from tianwen import report
    s = _full()
    out = report.humanize("断 [zhouyi:1:guaci]，取象 [shuogua:11:qian]，"
                          "伪 [nothing:9]", s.resolve_cite)
    assert "〔《周易·乾》卦辞〕" in out
    assert "《说卦传》第十一章·乾〕" in out
    assert "[nothing:9]" in out and "[zhouyi:1:guaci]" not in out
    # 所据原文节选与降级输出全程无内部编号
    import re
    assert not re.search(r"\[[a-z]+:[0-9]", s.render_all())
