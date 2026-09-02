"""梅花体用生克（tiyong.py）：五行生克、互变、卦气、总诀明文、占章之句、
定例映射、序卦杂卦逐卦切片、占例召回、校验器主断必据。"""

from datetime import datetime

import pytest

from tianwen import selection, service, tiyong, topic, verdict
from tianwen.knowledge import KnowledgeBase
from tianwen.validator import validate

kb = KnowledgeBase()
WHEN = datetime(2026, 9, 2, 10, 30)     # 农历丙午年七月（秋）


# ── 五行生克 ──────────────────────────


def test_relation_five_cases():
    assert tiyong.relation("离", "震") == "生体"    # 木生火
    assert tiyong.relation("离", "坎") == "克体"    # 水克火
    assert tiyong.relation("离", "坤") == "体生"    # 火生土
    assert tiyong.relation("离", "乾") == "体克"    # 火克金
    assert tiyong.relation("乾", "兑") == "比和"


def test_wuxing_tables_match_corpus():
    # 八宫五行与生克表须与卷一原文逐字相符
    bagong = kb.citation("meihua:1:bagong")["text"]
    for gua, wx in tiyong.WUXING.items():
        assert f"{gua}" in bagong and wx in bagong
    wuxing = kb.citation("meihua:1:wuxing")["text"]
    for a, b in tiyong.SHENG.items():
        assert f"{a}生{b}" in wuxing
    for a, b in tiyong.KE.items():
        assert f"{a}克{b}" in wuxing


def test_zongjue_sentences_verbatim_in_corpus():
    zong = kb.citation("meihua:2:tiyong")["text"]
    for s in tiyong.ZONGJUE.values():
        assert s in zong, s
    for s in tiyong.HU_BIAN_QUOTES + (tiyong.DANG_QUOTE, tiyong.GUAQI_QUOTE):
        assert s in zong, s


def test_guaqi_by_season_and_convention():
    assert tiyong.guaqi("震", 1) == "旺" and tiyong.guaqi("坤", 1) == "衰"
    assert tiyong.guaqi("离", 5) == "旺" and tiyong.guaqi("乾", 5) == "衰"
    assert tiyong.guaqi("兑", 8) == "旺" and tiyong.guaqi("巽", 8) == "衰"
    assert tiyong.guaqi("坎", 11) == "旺" and tiyong.guaqi("离", 11) == "衰"
    # 辰戌丑未月（三六九十二）依「四季之月」条：土旺坎衰，余平
    assert tiyong.guaqi("艮", 3) == "旺" and tiyong.guaqi("坎", 3) == "衰"
    assert tiyong.guaqi("震", 3) == "平"
    assert tiyong.guaqi("离", 7) == "平"


# ── 机断 ──────────────────────────────


def test_analyze_shihe_sample():
    # 噬嗑初九（震下离上，动在下卦）：体离火、用震木→用生体；
    # 互艮坎；变卦坤（震初爻变为坤）
    an = tiyong.analyze(kb, kb.hexagram(21)["binary"], kb.hexagram(35)["binary"],
                        1, month=7, zhan_id="meihua:2:zhan:qiumou")
    assert (an.ti, an.yong, an.rel_yong) == ("离", "震", "用生体")
    assert [o.name for o in an.hu] == ["艮", "坎"]
    assert an.bian.name == "坤" and an.bian.rel == "体生"
    assert an.guaqi_ti == "平" and an.hu_note == ""
    assert an.zongjue == "用生体，有进益之喜"
    assert an.zhan_clause == "用生体。不谋而成"     # 底本标点讹为句号，照录
    names = {o.name for o, _ in an.sheng_ti}
    assert names == {"震"} and {o.name for o, _ in an.ke_ti} == {"坎"}
    zong = kb.citation("meihua:2:tiyong")["text"]
    for _o, s in an.sheng_ti + an.ke_ti:
        assert s and s in zong
    assert any("震卦生体" in s for _o, s in an.sheng_ti)


def test_qiankun_no_hu_uses_bian():
    # 乾初九动→姤：乾坤无互，互其变卦（姤之互为乾乾）
    an = tiyong.analyze(kb, kb.hexagram(1)["binary"], kb.hexagram(44)["binary"], 1)
    assert an.hu_note == "乾坤无互，互其变卦"
    assert [o.name for o in an.hu] == ["乾", "乾"]
    assert an.guaqi_ti is None and "月令未知" in an.guaqi_text()


def test_zhan_qi_and_shixu_for_qiucai():
    # 求财占论应期（「欲知得财之日，生体之卦气定之」）→ 附生体之卦时序
    an = tiyong.analyze(kb, kb.hexagram(21)["binary"], kb.hexagram(35)["binary"],
                        1, month=7, zhan_id="meihua:2:zhan:qiucai")
    assert any("卦气" in s for s in an.zhan_qi)
    assert an.shixu and an.shixu[0][0] == "震"
    assert an.shixu[0][1].startswith("时序：")
    assert an.shixu[0][1] in kb.citation(an.shixu[0][2])["text"]


def test_decide_tiyong_mapping():
    for rel, vd in (("用生体", "吉"), ("体克用", "吉"), ("体用比和", "吉"),
                    ("体生用", "谨"), ("用克体", "凶")):
        an = tiyong.analyze(kb, kb.hexagram(21)["binary"],
                            kb.hexagram(35)["binary"], 1)
        an.rel_yong = rel
        d = verdict.decide_tiyong(an)
        assert d["verdict"] == vd and d["cite_id"] == "meihua:2:tiyong"
        assert d["kind"] == "tiyong" and d["quote"] == tiyong.ZONGJUE[rel]
        assert verdict.audit_label(d) == "总诀明文映射"


def test_xici_definition_verbatim():
    text = kb.citation(verdict.XICI_CITE)["text"]
    for s in verdict.XICI_DEFINITION.values():
        assert s in text
    assert verdict.definition("平") == ("无咎者，善补过也", "xici:shang:3")
    assert verdict.definition("未著断辞") is None


# ── 选文与会话 ─────────────────────────


def test_selection_primary_is_tiyong_and_yao_is_reference():
    tp = topic.classify("近期换一份工作是否合适")
    sel = selection.select_meihua(kb, 21, 35, 1, tp, month=7)
    assert sel.primary.cite_id == "meihua:2:tiyong"
    assert sel.primary_ids == {"meihua:2:tiyong", "meihua:2:zhan:qiumou"}
    assert sel.primary.excerpt == "用生体，有进益之喜"
    yao = next(r for r in sel.readings if r.cite_id == "zhouyi:21:yao:1")
    assert not yao.primary and "易辞" in yao.role
    guaci = next(r for r in sel.readings if r.cite_id == "zhouyi:21:guaci")
    assert "xugua:21:gua" in guaci.context_ids and "zagua:21:gua" in guaci.context_ids
    assert "xici:shang:3" in sel.primary.context_ids
    for r in sel.readings:
        for cid in r.context_ids:
            assert kb.has(cid), cid


def test_zhuzi_primary_carries_xici_definition():
    sel = selection.select_zhuzi(kb, 1, 44, [1])
    assert "xici:shang:3" in sel.primary.context_ids


def test_session_output_and_repro():
    s = service.prepare("我该不该换工作", when=WHEN)
    assert s.sel.tiyong is not None and s.vd["kind"] == "tiyong"
    text = s.render_all()
    assert "【结论】有进益之喜" in text
    assert "总诀明文映射" in text
    assert "体用生克（梅花断法）：体离火／用震木→用生体" in text
    assert "断辞之义：「吉凶者，言乎其失得也」" in text
    assert "体用生克凭证" in text and "互卦艮（土，体生）、坎（水，克体）" in text
    assert "占例召回" in text
    assert s.overview_text().count("主断）") == 1        # 吉凶仍单源
    # 占例语境块：同类生克之例，可引不可断
    li = next(b for b in s.contexts if "占例" in b.title)
    assert 1 <= len(li.items) <= service.Session._LI_CAP
    assert all(cid.startswith("meihua:1:li:") for cid, _s, _t in li.items)


def test_session_deterministic_same_input():
    a = service.prepare("我该不该换工作", when=WHEN)
    b = service.prepare("我该不该换工作", when=WHEN)
    assert a.sel.tiyong.lines() == b.sel.tiyong.lines()
    assert a.render_all() == b.render_all()


# ── 校验器：断语至少须据主断明文 ───────────


def _ok():
    return {"conclusion": "白话", "judgment": "宜进。[meihua:2:tiyong]",
            "reasons": "理由。[zhouyi:21:yao:1]", "advice": ["议"],
            "quotes": [{"text": "用生体，有进益之喜", "cite_id": "meihua:2:tiyong"}]}


def test_validator_must_cite_primary_text():
    tp = topic.classify("近期换一份工作是否合适")
    sel = selection.select_meihua(kb, 21, 35, 1, tp, month=7)
    allowed = {r.cite_id: kb.citation(r.cite_id)["text"] for r in sel.readings}
    primary = frozenset(allowed)
    assert validate(_ok(), allowed, primary, sel.primary_ids) == []
    bad = _ok()
    bad["judgment"] = "宜进。[zhouyi:21:yao:1]"     # 只据爻辞：不得单独立断
    errs = validate(bad, allowed, primary, sel.primary_ids)
    assert any("主断明文" in e for e in errs)
    both = _ok()
    both["judgment"] = "宜进。[meihua:2:zhan:qiumou][zhouyi:21:yao:1]"
    assert validate(both, allowed, primary, sel.primary_ids) == []


def test_prompt_mentions_narrative_and_daxiang_advice():
    from tianwen import llm
    assert "用为事之端" in llm._SYSTEM and "君子以" in llm._SYSTEM
    tp = topic.classify("近期换一份工作是否合适")
    sel = selection.select_meihua(kb, 21, 35, 1, tp, month=7)
    an = sel.tiyong
    vd = verdict.decide_tiyong(an)
    allowed = llm._allowed_texts(kb, sel)
    from tianwen import casting
    cast = casting.cast_wenyu("我该不该换工作", WHEN)
    p = llm._payload("我该不该换工作", cast, sel, vd, allowed, kb, tp)
    assert "【体用生克】" in p and "〔主断〕《梅花易数》·卷二·体用总诀" in p
    assert "用生体——总诀「用生体，有进益之喜」" in p


@pytest.mark.parametrize("hid", [1, 2, 21, 29, 30, 59, 63, 64])
def test_xugua_zagua_slices_are_verbatim_lines(hid):
    whole_xu = kb.citation("xugua:shang")["text"] + kb.citation("xugua:xia")["text"]
    whole_za = kb.citation("zagua:1")["text"]
    name = kb.hexagram(hid)["name"]
    if kb.has(f"xugua:{hid}:gua"):
        c = kb.citation(f"xugua:{hid}:gua")
        assert c["text"] in whole_xu
        assert c["source"].endswith(name.replace("习坎", "坎"))
    if kb.has(f"zagua:{hid}:gua"):
        c = kb.citation(f"zagua:{hid}:gua")
        assert c["text"] in whole_za


def test_zagua_subject_rules():
    assert kb.citation("zagua:30:gua")["text"] == "离上，而坎下也。"   # 非「涣离也」
    assert kb.citation("zagua:29:gua")["text"] == "离上，而坎下也。"   # 「而」字起
    assert kb.citation("zagua:7:gua")["text"] == "乾刚坤柔，比乐师忧。"  # 四字两卦
    assert kb.citation("zagua:20:gua")["text"].startswith("临、观之义")
    assert kb.citation("xugua:63:gua")["text"] == "有过物者，必济，故受之既济。"
    assert not kb.has("xugua:1:gua") and not kb.has("xugua:31:gua")
