"""藏书检索层测试：目录、取文、跨库检索与命令行。"""

import pytest

from yijing_agent import corpus


def test_catalog_lists_all_books():
    cat = corpus.catalog()
    keys = [b["key"] for b in cat]
    assert keys == ["zhouyi", "yizhuan", "wangbi", "meihua", "ziwei",
                    "strokes"]
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
    with pytest.raises(ValueError):
        corpus.search("abc123")


def test_cli(capsys):
    assert corpus.main(["--catalog"]) == 0
    assert "藏书" not in capsys.readouterr().err
    assert corpus.main(["--cite", "zagua:1"]) == 0
    assert "乾刚坤柔" in capsys.readouterr().out
    assert corpus.main(["--cite", "nothing:1"]) == 1
    assert corpus.main(["此语必无"]) == 1
    assert corpus.main(["群阴剥阳"]) == 0
