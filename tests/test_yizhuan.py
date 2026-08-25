"""易传补编测试：说卦/文言挂载、体用取象选文、数据完整性。"""

import json
from pathlib import Path

import pytest

from yijing_agent import llm, selection
from yijing_agent.knowledge import YIZHUAN_PATH, KnowledgeBase
from yijing_agent.trigrams import PINYIN
from yijing_agent.validator import validate

kb = KnowledgeBase()


# ── 假数据接线（不依赖真实 yizhuan.json） ──────────────


def _fake_yizhuan(tmp_path):
    data = {
        "meta": {"license": "CC BY-SA 4.0"},
        "shuogua": (
            [{"id": "7", "text": "乾健也坤顺也测试文"}]
            + [{"id": f"11:{py}", "gua": name, "text": f"{name}为测试象文"}
               for name, py in PINYIN.items()]
        ),
        "wenyan": {
            "1:guaci": "元者善之长也测试文",
            "1:yao:3": "君子进德修业测试文",
            "1:extra": "乾元用九测试文",
            "2:guaci": "坤至柔而动也刚测试文",
        },
    }
    f = tmp_path / "yizhuan.json"
    f.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return KnowledgeBase(yizhuan_path=f)


def test_fake_mount_and_labels(tmp_path):
    k = _fake_yizhuan(tmp_path)
    assert k.citation("shuogua:7")["source"] == "《说卦传》第七章"
    assert k.citation("shuogua:11:qian")["source"] == "《说卦传》第十一章·乾"
    assert k.wenyan("zhouyi:1:yao:3")["source"] == "《文言·乾》释三爻"
    assert k.wenyan("zhouyi:1:extra")["source"] == "《文言·乾》释用九"
    assert k.wenyan("zhouyi:2:guaci")["source"] == "《文言·坤》释卦辞"
    assert k.wenyan("zhouyi:3:guaci") is None   # 文言仅乾坤有


def test_tiyong_and_shuogua_readings(tmp_path):
    # 革（离下兑上）：动爻在上卦→兑用离体；在下卦→离用兑体
    assert selection.tiyong(kb, 49, 5) == ("离", "兑")
    assert selection.tiyong(kb, 49, 2) == ("兑", "离")
    k = _fake_yizhuan(tmp_path)
    sel = selection.select_meihua(k, 49, 55, 5)
    ids = [r.cite_id for r in sel.readings]
    assert "shuogua:11:li" in ids and "shuogua:11:dui" in ids
    ti = next(r for r in sel.readings if r.cite_id == "shuogua:11:li")
    assert "体卦离" in ti.role and ti.context_ids == ["shuogua:7"]
    assert not ti.primary
    assert "兑为用、离为体" in sel.rule


def test_no_yizhuan_degrades_silently(tmp_path):
    k = KnowledgeBase(yizhuan_path=tmp_path / "absent.json")
    sel = selection.select_meihua(k, 49, 55, 5)
    assert all(not r.cite_id.startswith("shuogua:") for r in sel.readings)
    assert k.wenyan("zhouyi:1:guaci") is None


def test_wenyan_enters_allowed_texts(tmp_path):
    k = _fake_yizhuan(tmp_path)
    sel = selection.select_zhuzi(k, 1, 44, [3])   # 乾九三主断
    allowed = llm._allowed_texts(k, sel)
    assert "wenyan:1:yao:3" in allowed
    assert "wenyan:1:guaci" in allowed            # 本卦卦辞（参）之文言


def test_judgment_cannot_rest_on_shuogua_alone():
    allowed = {"shuogua:11:qian": "乾为天为圜",
               "zhouyi:1:yao:3": "君子终日乾乾，夕惕若，厉无咎。"}
    base = {"conclusion": "白话结论。", "reasons": "解读。[zhouyi:1:yao:3]",
            "advice": ["建议"],
            "quotes": [{"text": "君子终日乾乾", "cite_id": "zhouyi:1:yao:3"}]}
    bad = dict(base, judgment="宜进。[shuogua:11:qian]")
    assert any("不得单独立断" in e for e in validate(bad, allowed))
    ok = dict(base, judgment="厉而无咎，宜勉力。[zhouyi:1:yao:3][shuogua:11:qian]")
    assert validate(ok, allowed) == []


# ── 真实数据完整性 ──────────────────────────


def test_data_file_integrity():
    d = json.loads(Path(YIZHUAN_PATH).read_text("utf-8"))
    assert d["meta"]["license"] == "CC BY-SA 4.0"
    assert d["meta"]["proofread"] is False   # 校对完成前不得为 True
    ids = {u["id"] for u in d["shuogua"]}
    for ch in range(1, 12):                  # 朱子十一章俱全
        assert any(i == str(ch) or i.startswith(f"{ch}:") for i in ids), ch
    for py in PINYIN.values():               # 广象八卦俱全
        assert f"11:{py}" in ids
    for u in d["shuogua"]:
        assert u["text"].strip(), u["id"]
    # 文言：乾七单元（卦辞+六爻+用九=8）坤七单元（卦辞+六爻）
    for part in ["guaci", "extra"] + [f"yao:{p}" for p in range(1, 7)]:
        assert d["wenyan"].get(f"1:{part}", "").strip(), f"乾文言缺 {part}"
    for part in ["guaci"] + [f"yao:{p}" for p in range(1, 7)]:
        assert d["wenyan"].get(f"2:{part}", "").strip(), f"坤文言缺 {part}"


def test_real_mount_and_selection():
    assert len(kb.shuogua_ids) >= 19         # 11 章（类象章八分）至少 8*1+11
    wy = kb.wenyan("zhouyi:1:yao:3")
    assert wy and "终日乾乾" in wy["text"]    # 文言释九三必引「终日乾乾」
    sel = selection.select_meihua(kb, 49, 55, 5)
    ids = [r.cite_id for r in sel.readings]
    assert "shuogua:11:li" in ids and "shuogua:11:dui" in ids
    assert "泽" in kb.citation("shuogua:11:dui")["text"]  # 兑为泽


def test_xici_xugua_zagua_integrity():
    # 系辞上十二章下九章；大衍筮法在上九，太极两仪在上十一
    d = json.loads(Path(YIZHUAN_PATH).read_text("utf-8"))
    ids = [u["id"] for u in d["xici"]]
    assert ids == [f"shang:{n}" for n in range(1, 13)] + \
        [f"xia:{n}" for n in range(1, 10)]
    assert kb.citation("xici:shang:9")["source"] == "《系辞上传》第九章"
    assert "大衍之数五十" in kb.citation("xici:shang:9")["text"]
    assert "易有太极，是生两仪" in kb.citation("xici:shang:11")["text"]
    assert "古者包牺氏之王天下也" in kb.citation("xici:xia:2")["text"]
    # 序卦上下篇、杂卦
    assert kb.citation("xugua:shang")["text"].startswith("有天地，然后万物生焉")
    assert "既济" in kb.citation("xugua:xia")["text"]
    assert kb.citation("zagua:1")["text"].startswith("乾刚坤柔")


def test_xici_quotes_scripture_verbatim():
    # 库内互证：系辞上八章引爻辞，与 hexagrams.json 经文逐字相合
    x8 = kb.citation("xici:shang:8")["text"]
    assert kb.citation("zhouyi:1:yao:6")["text"][:4] in x8      # 亢龙有悔
    assert kb.citation("zhouyi:61:yao:2")["text"][:4] in x8     # 鸣鹤在阴
