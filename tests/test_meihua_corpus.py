"""梅花占诀语料测试：数据完整性、挂载、按类附取占章。"""

import json
from pathlib import Path

from yijing_agent import selection, service, topic
from yijing_agent.knowledge import MEIHUA_PATH, KnowledgeBase

kb = KnowledgeBase()


def test_data_file_integrity():
    d = json.loads(Path(MEIHUA_PATH).read_text("utf-8"))
    assert d["meta"]["license"] == "CC BY-SA 4.0"
    assert d["meta"]["proofread"] is False
    assert len(d["units"]) == 19            # 体用总诀 + 十八占
    ids = [u["id"] for u in d["units"]]
    assert ids[0] == "2:tiyong"
    assert len([i for i in ids if i.startswith("2:zhan:")]) == 18
    for u in d["units"]:
        assert u["text"].strip() and u["title"], u["id"]


def test_mount_labels():
    c = kb.citation("meihua:2:tiyong")
    assert c["source"] == "《梅花易数》·卷二·体用总诀"
    assert "体卦为主" in c["text"] or "体为主" in c["text"]
    assert kb.citation("meihua:2:zhan:hunyin")["source"] == "《梅花易数》·卷二·婚姻占"


def test_zhan_attached_by_topic():
    tp = topic.classify("近期换一份工作是否合适")     # career → 求谋占
    sel = selection.select_meihua(kb, 49, 55, 5, tp)
    ids = [r.cite_id for r in sel.readings]
    assert "meihua:2:tiyong" in ids
    assert "meihua:2:zhan:qiumou" in ids
    zhan = next(r for r in sel.readings if r.cite_id == "meihua:2:zhan:qiumou")
    assert "求谋占" in zhan.role and not zhan.primary


def test_tiyong_only_without_topic_match():
    tp = topic.classify("此事如何")                   # other → 无占章
    sel = selection.select_meihua(kb, 49, 55, 5, tp)
    ids = [r.cite_id for r in sel.readings]
    assert "meihua:2:tiyong" in ids
    assert not any(i.startswith("meihua:2:zhan:") for i in ids)


def test_zhuzi_method_attaches_no_meihua():
    # 朱子占法不用梅花占诀（不混占法）
    tp = topic.classify("近期换一份工作是否合适")
    sel = selection.select(kb, "coin", 49, 55, [5], tp)
    assert not any(r.cite_id.startswith(("meihua:", "shuogua:"))
                   for r in sel.readings)


def test_service_event_body_shows_jue():
    s = service.prepare("近期换一份工作是否合适", method="time")
    body = s.body_text()
    assert "体用总诀" in body and "求谋占" in body
    assert "为用、" in s.sel.rule            # 体用之分进了占法标注
