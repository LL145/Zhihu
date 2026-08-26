"""格局判定器（patterns.py）：判定式逐局对照盘面，确定性、可复现。

命例均为真实生辰扫描所得（性别不影响判局所据之星曜宫位）。
"""

from datetime import datetime

import pytest

from tianwen.ziwei import chart as zchart
from tianwen.ziwei import patterns
from tianwen.ziwei.knowledge import ZiweiKB

ZKB = ZiweiKB()


def _matches(dt):
    return patterns.judge(ZKB, zchart.cast(dt, "男"))


def _by_id(ms):
    return {m.cite_id: m for m in ms}


def test_rules_and_skips_cover_all_49_ju():
    assert patterns.RULE_COUNT + patterns.SKIP_COUNT == 49
    ju_ids = {cid for cid in ZKB._records if cid.startswith("ziwei:1:ju:")}
    covered = ({cid for cid, _ in patterns._RULES}
               | {cid for cid, _ in patterns._SKIPPED})
    assert covered == ju_ids


def test_riyue_jiacai_and_zuogui_xianggui():
    # 武曲守命（丑），日月来夹；天魁坐命、天钺对宫相向
    ms = _by_id(_matches(datetime(1955, 1, 1, 0)))
    m = ms["ziwei:1:ju:fu:2"]
    assert m.name == "日月夹财" and m.cat == "定富局"
    assert m.basis == "武曲守命宫（丑），太阳在寅、太阴在子来夹"
    assert ms["ziwei:1:ju:gui:9"].name == "坐贵向贵"


def test_cailu_jiama():
    m = _by_id(_matches(datetime(1959, 3, 21, 20)))["ziwei:1:ju:fu:3"]
    assert m.basis == "天马守命（巳），武曲在辰、禄存在午来夹"


def test_jincan_guanghui_taiyang_alone_in_wu():
    m = _by_id(_matches(datetime(1955, 3, 19, 18)))["ziwei:1:ju:fu:6"]
    assert m.basis == "命宫在午，太阳单守"


def test_junchen_qinghui():
    m = _by_id(_matches(datetime(1955, 12, 8, 20)))["ziwei:1:ju:gui:6"]
    assert m.name == "君臣庆会"
    assert m.basis == "紫微与左辅右弼同守命宫（丑）"


def test_tanhuo_xiangfeng_requires_miaowang():
    m = _by_id(_matches(datetime(1965, 5, 23, 14)))["ziwei:1:ju:gui:17"]
    assert m.basis == "贪狼（庙）火星（庙）同守命宫（戌）"


def test_quanlu_shengfeng():
    m = _by_id(_matches(datetime(1957, 12, 3, 22)))["ziwei:1:ju:gui:22"]
    assert m.basis == "化禄（太阴·庙）化权（天同·旺）同守命宫（子）"


def test_liangchong_huagai():
    m = _by_id(_matches(datetime(1955, 11, 16, 16)))["ziwei:1:ju:pinjian:8"]
    assert m.basis == "禄存与化禄（天机）坐命（卯），同宫遇地空"


def test_riyue_canghui_fanbei_with_jumen():
    # 「逢巨暗」承「生不逢时」句例解作巨门守命（判定式注明）
    m = _by_id(_matches(datetime(1955, 2, 25, 20)))["ziwei:1:ju:pinjian:4"]
    assert m.basis == "太阳（落陷）太阴（落陷）反背，又巨门（暗）守命（巳）"


def test_junzi_zaiye_sisha_split_ming_shen():
    m = _by_id(_matches(datetime(1956, 10, 11, 20)))["ziwei:1:ju:pinjian:7"]
    assert m.basis == ("四杀火星在子（落陷）、铃星在申（落陷），"
                      "分守身命临陷地")


def test_judge_deterministic():
    dt = datetime(1955, 12, 8, 20)
    assert _matches(dt) == _matches(dt)


def test_skip_lines_name_reasons():
    lines = "\n".join(patterns.skip_lines(ZKB))
    assert "见前批注" in lines
    assert "禄马佩印" in lines and "不强解" in lines
    assert "定杂局论限运盛衰" in lines
    # 涉空亡与天刑诸局已随其星安讫解锁，不再以「未安」为由不判
    assert "未安" not in lines


# ── 空亡天刑解锁之六局（截路/旬中空亡、天刑随卷二诀安讫） ─────────


def test_riyue_jiaming_with_lucky_no_kongwang():
    m = _by_id(_matches(datetime(1950, 5, 28, 8)))["ziwei:1:ju:gui:1"]
    assert m.name == "日月夹命" and m.cat == "定贵局"
    assert m.basis == ("太阳在子、太阴在寅夹命（丑），命宫不坐空亡，"
                       "见吉星天魁")


def test_xingqiu_jiayin_ming_and_shen():
    # 天刑＝酉起正月顺至生月，临命唯巳时、临身唯未时（安星诀推演）
    m = _by_id(_matches(datetime(1950, 1, 10, 10)))["ziwei:1:ju:gui:15"]
    assert m.name == "刑囚夹印"
    assert m.basis == "天刑与廉贞（囚）同临命宫（未）"
    m = _by_id(_matches(datetime(1950, 3, 2, 14)))["ziwei:1:ju:gui:15"]
    assert m.basis == "天刑与廉贞（囚）同临身宫（酉）"


def test_shengbufengshi_lianzheng_on_kongwang():
    m = _by_id(_matches(datetime(1950, 2, 5, 8)))["ziwei:1:ju:pinjian:1"]
    assert m.name == "生不逢时"
    assert m.basis == "命宫（酉）坐截路空亡，廉贞守命"


def test_lufeng_liangsha():
    m = _by_id(_matches(datetime(1956, 2, 12, 12)))["ziwei:1:ju:pinjian:2"]
    assert m.basis == ("禄存之宫（巳（子女宫））坐截路空亡、旬中空亡，"
                       "又逢地空、地劫")


def test_maluo_kongwang():
    m = _by_id(_matches(datetime(1951, 2, 11, 0)))["ziwei:1:ju:pinjian:3"]
    assert m.basis == "天马之宫（巳（田宅宫））落截路空亡"


def test_yinyin_gongshen_structurally_never_fires():
    # 荫印拱身「身临田宅」：命身支序恒差偶数（安身命例），身宫只落
    # 命、妻妾、财帛、迁移、官禄、福德六宫，永不临田宅——照诀转码，
    # 不合则不出
    from tianwen.ziwei.chart import ming_shen
    for month in range(1, 13):
        for hz in range(12):
            ming, shen = ming_shen(month, hz)
            assert (ming - shen) % 2 == 0


def test_selection_adds_ju_readings():
    from tianwen.ziwei import selection as zselection
    ch = zchart.cast(datetime(1955, 12, 8, 20), "男")
    sel = zselection.select_destiny(ZKB, ch)
    assert sel.ju and any(m.cite_id == "ziwei:1:ju:gui:6" for m in sel.ju)
    roles = [r.role for r in sel.readings]
    assert any(r.startswith("认局：定贵局·君臣庆会——") for r in roles)
    # 认局只入语境，不改主断
    assert all(not r.primary for r in sel.readings
               if r.role.startswith("认局："))
    assert any("格局判定" in n for n in sel.notes)


def test_service_repro_and_evidence_carry_ju():
    from tianwen import service
    tp = service.resolve_topic("我的命格如何")
    s = service.prepare("我的命格如何", name="",
                        birth_dt=datetime(1955, 12, 8, 20), gender="男")
    assert s.primary == "chart"
    assert "认局：定贵局·君臣庆会" in s.evidence_text()
    repro = s.repro_text()
    assert "── 格局判定（确定性）" in repro
    assert "认出：定贵局·君臣庆会——紫微与左辅右弼同守命宫（丑）" in repro
    assert f"不判 {patterns.SKIP_COUNT} 局" in repro


def test_service_no_ju_recognized_still_notes():
    from tianwen.ziwei import selection as zselection
    # 平盘无局之例：认出为空时凭证与提示语仍如实说明
    for dt in (datetime(1980, 6, 2, 8), datetime(1990, 7, 15, 10),
               datetime(2000, 9, 9, 12)):
        ch = zchart.cast(dt, "女")
        sel = zselection.select_destiny(ZKB, ch)
        if not sel.ju:
            assert any("无一入局" in n for n in sel.notes)
            return
    pytest.skip("样例生辰均认出局，另择无局之例")
