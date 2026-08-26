"""断辞提取与结论映射测试（以真实经文为用例）。"""

from tianwen import verdict
from tianwen.knowledge import KnowledgeBase

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


def test_duiju_conditional():
    # 显否定式与善辞并见为对举之句，归「条件」，不得被善辞吞没：
    # 蒙上九「不利为寇，利御寇」、蹇卦辞「利西南，不利东北」
    assert _decide("zhouyi:4:yao:6")["verdict"] == "条件"
    assert _decide("zhouyi:39:guaci")["verdict"] == "条件"
    # 与无咎类并见同为对举：临六三「无攸利；既忧之，无咎」
    assert _decide("zhouyi:19:yao:3")["verdict"] == "条件"


def test_variant_tokens():
    # 否定式变体整词归并，不得拆出孤立负字：
    # 小畜初九「何其咎？吉」→ 吉；复初九「无祗悔，元吉」→ 吉；
    # 姤九三「厉，无大咎」→ 谨（厉＋无咎类）
    assert _decide("zhouyi:9:yao:1")["verdict"] == "吉"
    assert _decide("zhouyi:24:yao:1")["verdict"] == "吉"
    assert _decide("zhouyi:44:yao:3")["verdict"] == "谨"


def test_hengyu_is_verb():
    # 「王用亨于西山」之亨为享祀动辞，消耗不计：随上六 → 未著断辞；
    # 升六四「王用亨于岐山，吉无咎」断辞另出 → 仍吉
    assert _decide("zhouyi:17:yao:6")["verdict"] == "未著断辞"
    assert _decide("zhouyi:46:yao:4")["verdict"] == "吉"


def test_feijiu_as_wujiu():
    # 「匪咎」同「何咎」为无咎类，不得拆出「咎」记为戒。
    # 大有初九「无交害，匪咎；艰则无咎。」→ 平
    names = [t for t, _ in verdict.extract_tokens("无交害，匪咎；艰则无咎。")]
    assert "匪咎" in names and "咎" not in names
    assert _decide("zhouyi:14:yao:1")["verdict"] == "平"


def test_audited_overrides():
    # 抽样审定个案（data/verdict_overrides.json）：小人勿用之诫在用人
    v = _decide("zhouyi:7:yao:6")
    assert v["audited"] is True and v["verdict"] == "谨"
    assert _decide("zhouyi:43:yao:3")["verdict"] == "条件"   # 凶/无咎对举


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


def test_audited_flags():
    # 全量审定确认名单（data/verdict_audit.json）：机取维持，audited 置真
    v = _decide("zhouyi:1:guaci")
    assert v["audited"] is True and "全量审定" in v["basis"]
    # 名单与 overrides 之外（如新增经文）仍如实标待审
    assert verdict.decide("x:test", "元吉").get("audited") is False


def test_override(tmp_path, monkeypatch):
    p = tmp_path / "overrides.json"
    p.write_text('{"zhouyi:1:yao:1": {"verdict": "忌", "action": "潜藏勿动", "note": "审定"}}',
                 "utf-8")
    monkeypatch.setattr(verdict, "OVERRIDES_PATH", p)
    v = verdict.decide("zhouyi:1:yao:1", "潜龙，勿用。")
    assert v["audited"] is True and v["action"] == "潜藏勿动"
