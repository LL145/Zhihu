"""紫微库（data/ziwei.json）数据完整性与查表测试。"""

import json
from pathlib import Path

import pytest

from tianwen.validator import _CITE_MARK
from tianwen.ziwei.knowledge import ZiweiKB

DATA = Path(__file__).parent.parent / "tianwen" / "data" / "ziwei.json"


@pytest.fixture(scope="module")
def raw():
    return json.loads(DATA.read_text("utf-8"))


@pytest.fixture(scope="module")
def zkb():
    return ZiweiKB()


def test_meta(raw):
    m = raw["meta"]
    assert "CC BY-SA 4.0" in m["license"]
    assert m["proofread"] is False
    assert set(m["pages"]) == {"紫微斗數全書/卷一", "紫微斗數全書/卷二",
                               "紫微斗數全書/卷三"}
    assert all(isinstance(v, int) for v in m["pages"].values())
    assert len(m["fixes"]) == 2
    assert m["warnings"]        # 校对队列非空（缺文与疑似今语）


def test_record_counts(raw):
    kinds = {}
    for r in raw["records"].values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    assert kinds["ming"] == 14          # 十四主星命宫论断
    assert kinds["male"] == 14
    assert kinds["female"] == 13        # 底本天梁缺入女命诀
    assert kinds["xian"] == 14
    assert kinds["wenda"] == 30
    assert kinds["lun"] == 2
    assert kinds["gong"] >= 240         # 十一宫逐星断语
    assert kinds["ding"] == 5           # 官禄宫定公卿等
    # 紫微库二期：卷一赋文与格局诸诀
    assert kinds["fu"] == 11            # 太微赋…失陷贫贱论整节条目
    assert kinds["shideng"] == 10       # 定富贵贫贱十等论
    assert kinds["hege"] == 12          # 得地合格诀，十二宫支各一
    assert kinds["poge"] >= 9           # 失陷破格诀（行可兼数宫支）
    assert kinds["ju"] >= 40            # 定富/贵/贫贱/杂局逐局
    assert len(raw["records"]) >= 510


def test_cite_ids_match_validator_regex(raw):
    for cid in raw["records"]:
        assert _CITE_MARK.findall(f"[{cid}]") == [cid], cid


def test_fixes_applied(raw):
    blob = json.dumps(raw["records"], ensure_ascii=False)
    assert "兄弟感情融洽" not in blob    # 贡献者白话已删
    assert "羊玲" not in blob            # 误字已订正
    assert "羊铃克害" in blob


def test_no_markup_residue(raw):
    for cid, r in raw["records"].items():
        assert r["text"]
        for ch in "{}<>[]=":
            assert ch not in r["text"], cid


def test_lookups(zkb):
    assert zkb.citation("ziwei:2:ming:ziwei")["text"].startswith("紫微土")
    assert zkb.ming("太阴") == "ziwei:2:ming:taiyin"
    assert zkb.ming_jue("天梁", "female") is None      # 底本缺
    assert zkb.ming_jue("天梁", "xian") is not None
    assert zkb.gong("财帛", "七杀") is None            # 底本缺文
    assert zkb.gong("财帛", "贪狼") is not None
    # 迁移宫紫微行以「紫微同左右」起（借「同」字起行的真条目）
    assert zkb.citation(zkb.gong("迁移", "紫微"))["text"].startswith("紫微同左右")
    # 合并条目（妻妾宫左辅右弼同一行）两星同指一条
    assert zkb.gong("妻妾", "左辅") == zkb.gong("妻妾", "右弼")
    assert zkb.gong_zonglun("子女") is not None
    assert zkb.gong_zonglun("兄弟") is None
    assert zkb.wenda("天同") is not None
    assert zkb.lun("daxian") is not None
    assert zkb.lun("erxian") is not None


def test_ge_lines_by_branch(zkb):
    lines = zkb.ge_lines("太阴", "卯")
    assert len(lines) == 1
    assert "卯" in zkb.citation(lines[0])["text"]


def test_source_labels(zkb):
    c = zkb.citation("ziwei:1:wenda:jumen")
    assert c["source"].startswith("《紫微斗数全书》")
    assert "问巨门" in c["source"]


def test_fu_sections(raw, zkb):
    """卷一赋文与格局诸诀（紫微库二期）。"""
    c = zkb.citation("ziwei:1:fu:taiwei")
    assert "太微赋" in c["source"]
    assert "斗数至玄至微" in c["text"]
    assert "骨髓赋" in zkb.citation("ziwei:1:fu:gusui")["source"]
    assert "女命骨髓赋" in zkb.citation("ziwei:1:fu:nvgusui")["source"]
    # 合格诀十二宫支齐备，branches 已归一（含底本「戍」）
    for seg, b in [("zi", "子"), ("xu", "戌"), ("hai", "亥")]:
        r = raw["records"][f"ziwei:1:hege:{seg}"]
        assert r["branches"] == [b]
        assert "安命" in r["text"]
    # 破格诀行可兼数宫支
    brs = [b for r in raw["records"].values() if r["kind"] == "poge"
           for b in r["branches"]]
    assert len(brs) == 12 and set(brs) == set("子丑寅卯辰巳午未申酉戌亥")
    # 定局逐局有局名入 source
    gui = [r for cid, r in raw["records"].items()
           if cid.startswith("ziwei:1:ju:gui:")]
    assert len(gui) >= 20
    assert any(r["source"].endswith("君臣庆会") for r in gui)
