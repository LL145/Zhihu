"""断辞提取与结论映射测试（以真实经文为用例）。"""

from yijing_agent import verdict
from yijing_agent.knowledge import KnowledgeBase

kb = KnowledgeBase()


def _decide(cite_id):
    return verdict.decide(cite_id, kb.citation(cite_id)["text"])


def test_qian_guaci_ji():
    # 乾卦辞「元亨利贞。」→ 吉
    assert _decide("zhouyi:1:guaci")["verdict"] == "吉"


def test_qianlong_wuyong_ji():
    # 乾初九「潜龙，勿用。」→ 忌（不宜行动）
    assert _decide("zhouyi:1:yao:1")["verdict"] == "忌"


def test_li_wujiu_jin():
    # 乾九三「……厉无咎。」→ 谨（厉而有戒则无咎）
    assert _decide("zhouyi:1:yao:3")["verdict"] == "谨"


def test_wujiu_ping():
    # 乾九四「或跃在渊，无咎。」→ 平
    assert _decide("zhouyi:1:yao:4")["verdict"] == "平"


def test_xiong():
    # 恒初六「浚恒，贞凶，无攸利。」→ 凶
    assert _decide("zhouyi:32:yao:1")["verdict"] == "凶"


def test_conditional():
    # 屯九五「屯其膏，小贞吉，大贞凶。」→ 条件（吉凶并见）
    assert _decide("zhouyi:3:yao:5")["verdict"] == "条件"


def test_no_duanci():
    # 坤初六「履霜，坚冰至。」→ 未著断辞
    assert _decide("zhouyi:2:yao:1")["verdict"] == "未著断辞"


def test_huiwang_not_hui():
    # 「悔亡」须整词匹配为轻善，不得拆出「悔」记为戒。睽初九「悔亡；……无咎。」
    tokens = verdict.extract_tokens("悔亡；丧马勿逐，自复；见恶人，无咎。")
    names = [t for t, _ in tokens]
    assert "悔亡" in names and "悔" not in names
    assert _decide("zhouyi:38:yao:1")["verdict"] == "吉"


def test_wubuli_not_buli():
    # 「无不利」整词为善断，不得拆出「不利」
    tokens = verdict.extract_tokens("黄裳元吉，无不利。")
    names = [t for t, _ in tokens]
    assert "无不利" in names and "不利" not in names


def test_all_384_yao_classifiable():
    # 全部爻辞可分类且不抛异常；统计分布仅作观察
    from collections import Counter
    counts = Counter()
    for hid in range(1, 65):
        for pos in range(1, 7):
            v = _decide(f"zhouyi:{hid}:yao:{pos}")
            counts[v["verdict"]] += 1
    assert sum(counts.values()) == 384
    assert set(counts) <= {"吉", "条件", "凶", "危", "谨", "忌", "平", "未著断辞"}


def test_unaudited_flag():
    assert _decide("zhouyi:1:guaci")["audited"] is False


def test_override(tmp_path, monkeypatch):
    p = tmp_path / "overrides.json"
    p.write_text('{"zhouyi:1:yao:1": {"verdict": "忌", "action": "潜藏勿动", "note": "审定"}}',
                 "utf-8")
    monkeypatch.setattr(verdict, "OVERRIDES_PATH", p)
    v = verdict.decide("zhouyi:1:yao:1", "潜龙，勿用。")
    assert v["audited"] is True and v["action"] == "潜藏勿动"
