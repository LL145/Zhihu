"""六爻纳甲典籍层（jingfang / huozhulin / huangjince）数据完整性测试。

三书为藏书层：可检索可引用，不参与定例断辞，不入现行选文
（六爻纳甲起卦引擎 v4 级，见 DESIGN.md 路线图）。
"""

import json
from pathlib import Path

import pytest

from tianwen import corpus
from tianwen.knowledge import KnowledgeBase

DATA = Path(__file__).parent.parent / "tianwen" / "data"


@pytest.fixture(scope="module")
def raws():
    return {k: json.loads((DATA / f"{k}.json").read_text("utf-8"))
            for k in ("jingfang", "huozhulin", "huangjince")}


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase()


def test_meta(raws):
    for key, raw in raws.items():
        m = raw["meta"]
        assert "CC BY-SA 4.0" in m["license"], key
        assert m["proofread"] is False, key
        assert m["pages"] and all(isinstance(v, int)
                                  for v in m["pages"].values()), key
        assert m["short"], key


def test_no_markup_residue(raws):
    for key, raw in raws.items():
        for u in raw["units"]:
            assert u["text"], f"{key}:{u['id']}"
            for ch in "{}<>[]=":
                assert ch not in u["text"], f"{key}:{u['id']}"


def test_jingfang_hexagrams(raws, kb):
    units = {u["id"]: u for u in raws["jingfang"]["units"]}
    gua = [u for uid, u in units.items() if uid.isdigit()]
    assert len(gua) == 64                       # 八宫六十四卦全
    hexes = json.loads((DATA / "hexagrams.json").read_text("utf-8"))
    names = {str(h["id"]): h["name"] for h in hexes["hexagrams"]}
    for u in gua:
        assert u["title"] == names[u["id"]]     # 卦名与周易卦序 id 对齐
    assert units["1"]["text"].startswith("纯阳用事")
    assert units["29"]["title"] == "习坎"
    assert units["33"]["title"] == "遁"
    assert {"xia:1", "xia:2", "xia:3"} <= set(units)   # 卷下总说/算法/总结
    # 只取本文不取注：陆绩注语不应在文本中
    blob = json.dumps(raws["jingfang"], ensure_ascii=False)
    assert "壬戌土，癸酉金" not in blob


def test_huozhulin(raws):
    units = raws["huozhulin"]["units"]
    assert len(units) >= 80
    assert units[0]["title"] == "易中明义"
    assert "四营成易" in units[0]["text"]
    assert "注云" in units[0]["text"]           # 原书注文并入正文
    # 页面自注节录之节在校对队列
    assert any("节录" in w for w in raws["huozhulin"]["meta"]["warnings"])


def test_huangjince(raws):
    units = raws["huangjince"]["units"]
    assert len(units) >= 30
    assert units[0]["title"] == "总断千金赋"    # 今人序号已剥离
    assert "动静阴阳" in units[0]["text"]
    assert units[-1]["title"] == "附：何知章"
    blob = json.dumps(raws["huangjince"], ensure_ascii=False)
    assert "应验当下" not in blob               # 今人「注釋」应期块已删
    assert "读者明辨" not in blob               # 今人「註記」按语行已删


def test_kb_and_corpus(kb):
    c = kb.citation("jingfang:1")
    assert c["source"] == "《京氏易传》·乾"
    assert kb.citation("huozhulin:1")["source"].startswith("《火珠林》")
    assert kb.citation("huangjince:1")["source"] == "《黄金策》·总断千金赋"
    keys = {b["key"] for b in corpus.catalog()}
    assert {"jingfang", "huozhulin", "huangjince"} <= keys
    hits = corpus.search("何知一家有二姓")
    assert hits and hits[0]["cite_id"].startswith("huangjince:")
