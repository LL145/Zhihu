"""藏书检索层测试：目录、取文、跨库检索与命令行。"""

import pytest

from tianwen import corpus


def test_catalog_lists_all_books():
    cat = corpus.catalog()
    keys = [b["key"] for b in cat]
    assert keys == ["zhouyi", "yizhuan", "wangbi", "meihua",
                    "jingfang", "huozhulin", "huangjince", "ziwei",
                    "tetra", "strokes"]
    for b in cat:
        assert b["units"] > 0 and b["license"], b["key"]
    by = {b["key"]: b for b in cat}
    assert by["zhouyi"]["units"] == 964      # 经 452 + 彖 64 + 象 448
    assert by["meihua"]["units"] == 71
    # 校对状态如实呈现：典籍均未人工校对完成
    assert not by["zhouyi"]["proofread"] and by["strokes"]["proofread"]


def test_get_spans_both_engines():
    assert corpus.get("zhouyi:1:guaci")["text"] == "元亨利贞。"
    assert "紫微" in corpus.get("ziwei:2:ming:ziwei")["source"]
    with pytest.raises(KeyError):
        corpus.get("nothing:1")


def test_search_punctuation_free():
    # 标点无关：带引号逗号照样命中系辞上九章
    hits = corpus.search("「大衍之数，五十」")
    assert hits[0]["cite_id"] == "xici:shang:9"
    assert "其用四十有九" in hits[0]["snippet"]


def test_search_across_books():
    # 一词横跨两书：王弼注剥卦与《梅花易数》西林寺占例同引「群阴剥阳」
    ids = [h["cite_id"] for h in corpus.search("群阴剥阳")]
    assert "wangbi:23:yao:3" in ids
    assert "meihua:1:li:xilinsi" in ids


def test_search_limit_and_errors():
    assert len(corpus.search("君子", limit=3)) == 3
    assert corpus.search("此语必无") == []
    # 纯拉丁词走英文通道（v3.9《占星四书》），不再报错
    assert corpus.search("thisstringneverappears") == []
    with pytest.raises(ValueError):
        corpus.search("，。！？")


def test_search_traditional_interop():
    # 繁简互通（归一表 data/t2s.json）：繁体检索词命中简体库文
    assert [h["cite_id"] for h in corpus.search("謙謙君子", limit=1)] \
        == ["xiaoxiang:15:1"]
    assert any(h["cite_id"].startswith("ziwei:")
               for h in corpus.search("天樑", limit=3))     # 书写变体 樑
    assert corpus.search("飛鳥遺之音", limit=1)[0]["cite_id"] == "tuan:62"
    assert corpus.search("體用", limit=1)[0]["cite_id"] == "meihua:2:tiyong"
    # 摘要仍取库文原字（归一只用于比对，不改原文）
    assert "谦谦君子" in corpus.search("謙謙君子", limit=1)[0]["snippet"]
    # 书名检索同归一
    assert corpus.find_source("體用總訣") == \
        [("meihua:2:tiyong", "《梅花易数》·卷二·体用总诀")]


def test_t2s_keeps_qian_and_validator_verbatim():
    # 乾为多义保形之字（乾卦库文保繁）：查「乾」中乾、查「干」不误中乾卦
    assert corpus._t2s().get("乾") is None
    ids = [h["cite_id"] for h in corpus.search("乾坤", limit=3)]
    assert "xici:shang:1" in ids
    assert all("乾" not in corpus.get(h["cite_id"])["text"][:60]
               for h in corpus.search("干父", limit=2))
    # 归一只在检索层：引文校验仍逐字，繁体引文照旧不过闸门
    from tianwen.validator import validate
    allowed = {"xiaoxiang:15:1": corpus.get("xiaoxiang:15:1")["text"]}
    r = {"conclusion": "白话。", "judgment": "断 [xiaoxiang:15:1]",
         "reasons": "理由 [xiaoxiang:15:1]", "advice": ["建议"],
         "quotes": [{"text": "謙謙君子", "cite_id": "xiaoxiang:15:1"}]}
    assert any("逐字" in e for e in
               validate(r, allowed, frozenset(allowed)))


def test_t2s_table_integrity():
    import json
    d = json.loads(corpus.T2S_PATH.read_text("utf-8"))
    assert d["meta"]["count"] == len(d["map"]) > 3000
    assert "引文校验不经此表" in d["meta"]["conversion"]
    assert all(len(k) == 1 and len(v) == 1 and k != v
               for k, v in d["map"].items())


def test_find_source_by_book_name(capsys):
    # 对外展示只列古籍原名，故 --cite 也认书名（唯一命中即出全文）
    assert corpus.find_source("体用总诀") == \
        [("meihua:2:tiyong", "《梅花易数》·卷二·体用总诀")]
    assert corpus.main(["--cite", "体用总诀"]) == 0
    assert "体用云者" in capsys.readouterr().out
    # 同名多条：列候选并提示写全，不瞎猜
    assert corpus.main(["--cite", "卦辞"]) == 1
    out = capsys.readouterr().out
    assert "同名" in out and "《周易·履》卦辞" in out


def test_cli(capsys):
    assert corpus.main(["--catalog"]) == 0
    assert "藏书" not in capsys.readouterr().err
    assert corpus.main(["--cite", "zagua:1"]) == 0
    assert "乾刚坤柔" in capsys.readouterr().out
    assert corpus.main(["--cite", "nothing:1"]) == 1
    assert corpus.main(["此语必无"]) == 1
    assert corpus.main(["群阴剥阳"]) == 0
