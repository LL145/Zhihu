"""注疏层测试：王弼注数据完整性、挂载正确性、进入 LLM 所据文本。"""

import json
from datetime import datetime
from pathlib import Path

from tianwen import casting, llm, selection, topic, verdict
from tianwen.knowledge import KnowledgeBase, WANGBI_PATH, wangbi_id
from tianwen.validator import validate

kb = KnowledgeBase()


def test_data_file_integrity():
    d = json.loads(Path(WANGBI_PATH).read_text("utf-8"))
    assert d["meta"]["license"] == "CC BY-SA 4.0"
    assert d["meta"]["proofread"] is False  # 校对完成前不得为 True
    assert len(d["meta"]["pages"]) == 64
    assert len(d["notes"]) >= 500
    for scid, text in d["notes"].items():
        assert kb.has(scid), f"注挂在未知经文: {scid}"
        assert text.strip(), f"空注: {scid}"


def test_wangbi_id_mapping():
    assert wangbi_id("zhouyi:49:yao:5") == "wangbi:49:yao:5"
    assert wangbi_id("zhouyi:1:guaci") == "wangbi:1:guaci"
    assert wangbi_id("zhouyi:2:extra") == "wangbi:2:extra"
    assert wangbi_id("tuan:49") == "wangbi:49:tuan"
    assert wangbi_id("daxiang:49") == "wangbi:49:daxiang"
    assert wangbi_id("xiaoxiang:49:4") == "wangbi:49:xiaoxiang:4"
    assert wangbi_id("xiaoxiang:1:extra") == "wangbi:1:xiaoxiang:extra"


def test_commentary_lookup():
    # 革九五王弼注：「未占而孚」，合时心也。
    c = kb.commentary("zhouyi:49:yao:5")
    assert c["cite_id"] == "wangbi:49:yao:5"
    assert "合时心" in c["text"]
    assert "王弼" in c["source"]
    # 同一条也可按 cite_id 查（供引文校验）
    assert kb.citation("wangbi:49:yao:5")["text"] == c["text"]
    # 王弼于泰卦辞无注
    assert kb.commentary("zhouyi:11:guaci") is None


def test_kb_xiaoxiang_fix_regression():
    # 导入订正：乾九二小象「见龙再田」→「见龙在田」
    assert "见龙在田" in kb.citation("xiaoxiang:1:2")["text"]


def test_commentary_in_allowed_texts():
    cast = casting.cast_meihua(datetime(2026, 8, 24, 15, 30))  # 革 动爻5
    ben, zhi = kb.id_of(cast.ben_binary), kb.id_of(cast.zhi_binary)
    sel = selection.select(kb, cast.method, ben, zhi, cast.moving)
    allowed = llm._allowed_texts(kb, sel)
    assert "wangbi:49:yao:5" in allowed
    # 王弼注可引用且通过逐字校验
    result = {
        "conclusion": "白话结论。",
        "judgment": "宜进。[zhouyi:49:yao:5]",
        "reasons": "解读 [zhouyi:49:yao:5]，注家亦云 [wangbi:49:yao:5]",
        "advice": ["建议"],
        "quotes": [{"text": "合时心也", "cite_id": "wangbi:49:yao:5"}],
    }
    assert validate(result, allowed) == []


def test_payload_has_annotation_section():
    cast = casting.cast_meihua(datetime(2026, 8, 24, 15, 30))
    ben, zhi = kb.id_of(cast.ben_binary), kb.id_of(cast.zhi_binary)
    sel = selection.select(kb, cast.method, ben, zhi, cast.moving)
    vd = verdict.decide(sel.primary.cite_id, kb.citation(sel.primary.cite_id)["text"])
    allowed = llm._allowed_texts(kb, sel)
    tp = topic.classify("问事")
    payload = llm._payload("问事", cast, sel, vd, allowed, kb, tp)
    assert "【注疏】" in payload and "wangbi:49:yao:5" in payload
    assert "不得据以改动结论" in payload
