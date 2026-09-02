"""卦象运算与知识库完整性测试。"""

import pytest

from tianwen import hexagrams
from tianwen.knowledge import KnowledgeBase
from tianwen.trigrams import TRIGRAMS

kb = KnowledgeBase()


def test_all_64_hexagrams_loaded():
    assert len(kb.by_id) == 64
    assert len(kb.by_binary) == 64  # 爻画唯一


def test_binary_roundtrip_all():
    for hid, h in kb.by_id.items():
        assert kb.id_of(h["binary"]) == hid


def test_trigram_consistency_all():
    for h in kb.by_id.values():
        lower, upper = h["trigrams"]
        assert tuple(h["binary"][:3]) == TRIGRAMS[lower]["lines"]
        assert tuple(h["binary"][3:]) == TRIGRAMS[upper]["lines"]


def test_yao_names_match_binary():
    for h in kb.by_id.values():
        for y in h["yao"]:
            expect = "九" if h["binary"][y["pos"] - 1] == 1 else "六"
            assert expect in y["name"], f"{h['name']} {y['name']}"


def test_extra_only_qian_kun():
    for hid, h in kb.by_id.items():
        if hid in (1, 2):
            assert h["extra"] is not None
        else:
            assert h["extra"] is None


def test_full_names():
    assert kb.full_name(1) == "乾为天"
    assert kb.full_name(3) == "水雷屯"    # 上坎水 下震雷
    assert kb.full_name(44) == "天风姤"   # 上乾天 下巽风
    assert kb.full_name(63) == "水火既济"


def test_lines_to_binary_and_moving():
    lines = [9, 7, 8, 8, 6, 7]
    assert hexagrams.lines_to_binary(lines) == [1, 1, 0, 0, 0, 1]
    assert hexagrams.moving_positions(lines) == [1, 5]
    assert hexagrams.zhi_binary(lines) == [0, 1, 0, 0, 1, 1]


def test_hu_binary():
    # 乾（111111）互卦仍为乾；既济（101010）互卦为未济（010101）
    assert hexagrams.hu_binary([1] * 6) == [1] * 6
    assert hexagrams.hu_binary([1, 0, 1, 0, 1, 0]) == [0, 1, 0, 1, 0, 1]


def test_citations_exist():
    c = kb.citation("zhouyi:1:guaci")
    assert c["text"] == "元亨利贞。"
    assert kb.citation("zhouyi:1:extra")["text"] == "见群龙无首，吉。"
    assert kb.has("xiaoxiang:2:extra")
    assert not kb.has("zhouyi:65:guaci")


def test_citation_counts():
    # 卦辞64 + 爻辞384 + 用九用六2 + 彖64 + 大象64 + 小象384 + 用九用六小象2
    extra_ns = ("wangbi:", "shuogua:", "wenyan:", "meihua:",
                "xici:", "xugua:", "zagua:",
                "jingfang:", "huozhulin:", "huangjince:", "tetra:")
    scripture = [c for c in kb._citations
                 if not c.startswith(extra_ns)]
    assert len(scripture) == 64 + 384 + 2 + 64 + 64 + 384 + 2
    # 注疏层（王弼注）逐条可查
    notes = [c for c in kb._citations if c.startswith("wangbi:")]
    assert len(notes) == len(kb._commentary) >= 500
    # 易传补编：说卦 39、文言 15、系辞上 12 + 下 9、序卦 2、杂卦 1
    assert sum(c.startswith("shuogua:") for c in kb._citations) == 39
    assert sum(c.startswith("wenyan:") for c in kb._citations) == 15
    assert sum(c.startswith("xici:shang:") for c in kb._citations) == 12
    assert sum(c.startswith("xici:xia:") for c in kb._citations) == 9
    assert sum(c in ("xugua:shang", "xugua:xia") for c in kb._citations) == 2
    assert "zagua:1" in kb._citations
    # 逐卦切片（运行时自整篇派生）：序卦 61（乾坤与下篇首卦咸无「受之以」
    # 之语）、杂卦 63（旅不居句首）
    assert sum(c.startswith("xugua:") and c.endswith(":gua")
               for c in kb._citations) == 61
    assert sum(c.startswith("zagua:") and c.endswith(":gua")
               for c in kb._citations) == 63
