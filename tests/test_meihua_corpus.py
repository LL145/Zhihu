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
    assert len(d["units"]) == 71            # 卷一 52 + 卷二（总诀 + 十八占）19
    ids = [u["id"] for u in d["units"]]
    assert "2:tiyong" in ids
    assert len([i for i in ids if i.startswith("2:zhan:")]) == 18
    assert len([i for i in ids if i.startswith("1:")]) == 52
    assert len([i for i in ids if i.startswith("1:xiang:wanwu:")]) == 8
    for u in d["units"]:
        assert u["text"].strip() and u["title"], u["id"]


def test_juan1_casting_sources_present():
    # 起卦引擎（casting.py）所引起卦法原文，逐条在库、可引用
    c = kb.citation("meihua:1:qi:shijian")
    assert c["source"] == "《梅花易数》·卷一·年月日时起例"
    assert "年月日为上卦" in c["text"]
    assert "平分" in kb.citation("meihua:1:qi:zi")["text"]
    assert "三才" in kb.citation("meihua:1:qi:zishu")["text"]
    # 西林寺牌额占：字占之占例（李明 → 山地剥 与之同构）
    xilinsi = kb.citation("meihua:1:li:xilinsi")["text"]
    assert "以西字七画为艮" in xilinsi and "山地剥" in xilinsi
    # 万物属类逐卦一单元，供体用取象
    qian = kb.citation("meihua:1:xiang:wanwu:qian")
    assert qian["source"] == "《梅花易数》·卷一·八卦万物属类·乾"
    assert "天时：" in qian["text"]


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
