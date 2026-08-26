"""西洋占星第一期测试：语料完整性、星历独立谱系对照、本命盘确定性、
校验器拉丁通道、语境接线（ALGORITHM.md 步骤 5b/10/11）。"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tianwen import corpus, service
from tianwen.astro import ephemeris, natal
from tianwen.knowledge import KnowledgeBase, TETRA_PATH
from tianwen.llm import context_texts
from tianwen.validator import validate
from tianwen.ziwei import llm as zllm

kb = KnowledgeBase()


# ── 语料：《占星四书》 ─────────────────────────────────────────────

def test_tetra_data_integrity():
    d = json.loads(Path(TETRA_PATH).read_text("utf-8"))
    assert d["meta"]["proofread"] is False
    assert d["meta"]["language"] == "en"
    assert "sha256" in d["meta"]
    counts = {}
    for u in d["units"]:
        book = int(u["id"].split(":")[0])
        counts[book] = counts.get(book, 0) + 1
        assert u["text"].strip(), f"空章：{u['id']}"
        assert "[" not in u["text"], f"残留脚注号：{u['id']}"
        assert kb.has(f"tetra:{u['id']}")
    assert counts == {1: 27, 2: 14, 3: 19, 4: 10}


def test_tetra_corpus_layer():
    row = [b for b in corpus.catalog() if b["key"] == "tetra"][0]
    assert row["units"] == 70 and row["proofread"] is False
    c = corpus.get("tetra:1:5")
    assert c["source"] == "《占星四书》卷一·第五章（BENEFICS AND MALEFICS）"
    assert "Jupiter and Venus" in c["text"]
    # 英文检索（拉丁通道）
    hits = corpus.search("benefic, or causers of good", limit=3)
    assert any(h["cite_id"] == "tetra:1:5" for h in hits)


def test_dignity_tables_match_source_text():
    # 本位（tetra:1:20）与擢升/降卑（tetra:1:22）判定表逐星对照原文字样
    t20 = kb.citation("tetra:1:20")["text"]
    for phrase in ("Leo for the Sun", "Cancer for the Moon",
                   "these are Aquarius and Capricorn",       # 土
                   "Sagittarius and Pisces",                 # 木
                   "Aries and Scorpio",                      # 火
                   "Taurus and Libra",                       # 金
                   "Gemini and Virgo"):                      # 水
        assert phrase in t20, phrase
    t22 = kb.citation("tetra:1:22")["text"]
    for phrase in ("determined to be in Aries",              # 日擢升
                   "His fall is placed in Libra",            # 日降卑
                   "his exaltation in Libra, and his fall in Aries",   # 土
                   "her exaltation; while Scorpio",          # 月
                   "his fall in Capricorn",                  # 木
                   "exaltation is therefore placed in Capricorn",      # 火
                   "her fall in Virgo",                      # 金
                   "his exaltation in Virgo"):               # 水
        assert phrase in t22, phrase
    # 表自身自洽：降卑恒为擢升对宫；诸曜本位互不重叠且铺满十二宫
    assert all((natal.EXALTATION[k] + 6) % 12 == natal.FALL[k]
               for k in natal.EXALTATION)
    homes = [s for v in natal.DOMICILE.values() for s in v]
    assert sorted(homes) == list(range(12))


def test_context_chapter_ids_exist():
    ids = set(natal.BASE_CHAPTERS)
    for v in natal.TOPIC_CHAPTERS.values():
        ids.update(v)
    for v in natal.ASPECT_CHAPTERS.values():
        ids.update(v)
    for cid in ids:
        assert kb.has(f"tetra:{cid}"), cid
    # 寿夭疾病生死诸章（红线主题）不得入语境映射
    banned = {"3:9", "3:10", "3:11", "3:12", "3:13", "3:14", "3:15",
              "3:17", "3:19", "4:9"}
    assert not ids & banned


# ── 星历：独立谱系交叉验证（pyephem） ──────────────────────────────

def test_ephemeris_vs_pyephem():
    ephem = pytest.importorskip("ephem")
    names = {"sun": "Sun", "moon": "Moon", "mercury": "Mercury",
             "venus": "Venus", "mars": "Mars", "jupiter": "Jupiter",
             "saturn": "Saturn"}
    dt = datetime(1900, 1, 2)
    while dt.year < 2100:
        lons, _ = ephemeris.apparent_longitudes(dt)
        d = ephem.Date(dt)
        for key, cls in names.items():
            b = getattr(ephem, cls)(d)
            eq = ephem.Equatorial(b.ra, b.dec, epoch=d)
            ref = math.degrees(ephem.Ecliptic(eq).lon)
            diff = abs((lons[key] - ref + 180.0) % 360.0 - 180.0) * 3600.0
            tol = 120.0 if key == "moon" else 20.0
            assert diff <= tol, f"{key} @ {dt}: 偏差 {diff:.1f}″"
        dt += timedelta(days=1723, hours=7)


def test_ephemeris_meta_recorded():
    meta = ephemeris.tables()["meta"]
    assert "VSOP87D" in meta["source"]
    assert "max_error_vs_full_tables" in meta


# ── 本命盘 ─────────────────────────────────────────────────────────

def test_natal_deterministic_and_placements():
    a = natal.cast(datetime(2000, 9, 14, 12))
    b = natal.cast(datetime(2000, 9, 14, 12))
    assert a.repro == b.repro
    # 时辰内不同钟点同时辰 → 同盘（时辰中点约定）
    c = natal.cast(datetime(2000, 9, 14, 11))
    assert c.repro == a.repro
    by = {p.key: p for p in a.placements}
    assert natal.SIGNS[by["sun"].sign_idx] == "室女"
    assert natal.SIGNS[by["moon"].sign_idx] == "双鱼"
    assert ("金星", "本位", "天秤宫") in a.dignities
    assert ("太阳", "月亮", "对分", "不和") in a.aspects
    assert ("水星", "金星", "天秤宫") in a.same_sign
    for key in ("时刻折算", "七曜黄经", "落宫算式", "月亮时辰漂移", "约定"):
        assert key in a.repro


def test_natal_moon_boundary_honesty():
    # 月亮每两日余移一宫，逐时辰扫描必遇两端跨宫之例；跨宫须如实存疑
    dt = datetime(2001, 3, 1, 0)
    found = None
    for i in range(60):
        ch = natal.cast(dt + timedelta(hours=2 * i))
        if ch.moon_uncertain:
            found = ch
            break
    assert found is not None, "60 时辰内未见月亮跨宫，漂移检查疑失效"
    assert any("勿引" in ln for ln in natal.facts_lines(found))
    assert "跨宫" in found.repro["月亮时辰漂移"]


def test_late_zi_shichen_next_day():
    # 23 时属次日子时：中点为次日 0 时
    ch = natal.cast(datetime(2000, 9, 14, 23))
    assert ch.mid_beijing == datetime(2000, 9, 15, 0)
    other = natal.cast(datetime(2000, 9, 15, 0))
    # 同一天文时刻（生辰行如实各记其输入日期）
    assert other.repro["七曜黄经"] == ch.repro["七曜黄经"]
    assert other.repro["时刻折算"] == ch.repro["时刻折算"]


# ── 校验器拉丁通道 ─────────────────────────────────────────────────

def _chart_session(question):
    return service.prepare(question, birth_dt=datetime(2000, 9, 14, 12),
                           gender="男", when=datetime(2026, 8, 24, 15, 30))


def test_validator_latin_channel():
    s = _chart_session("我是什么命")
    allowed = zllm._allowed_texts(s.zkb, s.sel)
    primary = frozenset(allowed)
    allowed = {**allowed, **context_texts(s.contexts)}
    base = {"conclusion": "白话。", "judgment": f"断 [{s.vd['cite_id']}]",
            "reasons": f"理由 [{s.vd['cite_id']}]，亦参 [tetra:1:5]",
            "advice": ["建议"]}
    ok = dict(base, quotes=[{"text": "these are Jupiter and Venus,",
                             "cite_id": "tetra:1:5"}])
    assert validate(ok, allowed, primary) == []
    # 中译不得充引文（拉丁单元规整后为空 → 结构性拒绝）
    zh = dict(base, quotes=[{"text": "吉星是木星与金星",
                             "cite_id": "tetra:1:5"}])
    assert any("原语原文" in e for e in validate(zh, allowed, primary))
    # 篡改英文引文同样拒绝
    bad = dict(base, quotes=[{"text": "these are Jupiter and Mars",
                              "cite_id": "tetra:1:5"}])
    assert validate(bad, allowed, primary)
    # 占星文本不得单独立断（语境侧）
    j = dict(base, judgment="断 [tetra:1:5]",
             quotes=[{"text": "these are Jupiter and Venus",
                      "cite_id": "tetra:1:5"}])
    assert any("主断侧" in e for e in validate(j, allowed, primary))


# ── 第二期：上升与中天、整宫分府（有出生地时） ─────────────────────

def test_sidereal_time_vs_pyephem():
    ephem = pytest.importorskip("ephem")
    dt = datetime(1905, 3, 4, 7, 30)
    while dt.year < 2100:
        gast, _eps = ephemeris.sidereal_obliquity(dt)
        obs = ephem.Observer()
        obs.lon, obs.lat = "0", "0"
        obs.date, obs.pressure = ephem.Date(dt), 0
        ref = math.degrees(float(obs.sidereal_time()))
        diff = abs((gast - ref + 180.0) % 360.0 - 180.0) * 3600.0
        assert diff <= 5.0, f"GAST @ {dt}: 偏差 {diff:.2f}″"
        dt += timedelta(days=2777, hours=13)


def test_angles_on_horizon_and_meridian_vs_pyephem():
    # 上升点定义即黄道与当地东方地平之交点：其高度须≈0 且尚在升侧
    # （时角为负）；中天在子午圈上（时角≈0）。以 pyephem 的恒星时与
    # 黄赤坐标变换独立验证 natal._angles_at 之公式，不与其共享推导。
    ephem = pytest.importorskip("ephem")
    cases = [(datetime(1992, 10, 8, 10), 116.41, 39.90),
             (datetime(2000, 9, 14, 0), 113.26, 23.13),
             (datetime(1950, 1, 1, 0), 87.62, 43.83),
             (datetime(2030, 6, 21, 18), -70.65, -33.45),   # 南半球西经
             (datetime(1980, 12, 25, 12), 121.47, 31.23)]
    for utc, lon, lat in cases:
        asc, mc, _ramc, _eps = natal._angles_at(utc, lon, lat)
        d = ephem.Date(utc)
        obs = ephem.Observer()
        obs.lon, obs.lat = str(lon), str(lat)
        obs.date, obs.pressure = d, 0
        lst = math.degrees(float(obs.sidereal_time()))

        def _radec(lam):
            eq = ephem.Equatorial(
                ephem.Ecliptic(math.radians(lam), 0.0, epoch=d), epoch=d)
            return math.degrees(float(eq.ra)), math.degrees(float(eq.dec))

        ra, dec = _radec(asc)
        h = (lst - ra + 180.0) % 360.0 - 180.0
        alt = math.degrees(math.asin(
            math.sin(math.radians(lat)) * math.sin(math.radians(dec))
            + math.cos(math.radians(lat)) * math.cos(math.radians(dec))
            * math.cos(math.radians(h))))
        assert abs(alt) * 3600.0 <= 60.0, f"asc @ {utc}: 高度 {alt * 3600:.0f}″"
        assert h < 0, f"asc @ {utc}: 时角 {h:.2f}°（应在升侧）"
        ra_mc, _dec_mc = _radec(mc)
        h_mc = (lst - ra_mc + 180.0) % 360.0 - 180.0
        assert abs(h_mc) * 3600.0 <= 60.0, f"mc @ {utc}: 时角 {h_mc:.4f}°"


def test_natal_place_houses_and_strengths():
    # 2000-09-14 辰时·北京：时辰两端上升同在天秤（慢升诸宫）→ 分府可出
    ch = natal.cast(datetime(2000, 9, 14, 8), place=(116.41, 39.90))
    a = ch.angles
    assert not a.asc_uncertain and natal.SIGNS[a.asc_sign] == "天秤"
    assert a.mc_uncertain          # 中天两端跨宫——时辰精度下如实存疑
    by = {k: (h, s) for k, h, s in a.houses}
    assert by["venus"] == (1, "轴宫")   # 金星在天秤，上升宫即第一府
    assert by["mars"] == (11, "续宫")
    assert by["sun"] == (12, "倾宫")
    for p in ch.placements:            # 整宫算式自洽：府序＝宫距＋1
        assert by[p.key][0] == (p.sign_idx - a.asc_sign) % 12 + 1
    lines = natal.facts_lines(ch)
    assert any("上升：天秤宫" in ln for ln in lines)
    assert any("金星第一府（轴宫）" in ln for ln in lines)
    assert any("中天落宫存疑" in ln for ln in lines)
    assert "出生地" in ch.repro and "上升中天" in ch.repro
    assert "机断约定" in ch.repro["分府"]
    same = natal.cast(datetime(2000, 9, 14, 8), place=(116.41, 39.90))
    assert same.repro == ch.repro      # 同输入必同输出


def test_asc_uncertain_honesty():
    # 酉时例：上升时辰内约行 30°，两端跨宫（快升诸宫尤甚）→ 存疑、分府不出
    ch = natal.cast(datetime(1992, 10, 8, 18), place=(116.41, 39.90))
    a = ch.angles
    assert a.asc_uncertain and a.houses is None
    assert any("上升落宫存疑" in ln and "勿引" in ln
               for ln in natal.facts_lines(ch))
    assert "分府不出" in ch.repro["分府"]
    assert "tetra:3:3" in ch.repro["轴点时辰漂移"]


def test_place_validation():
    with pytest.raises(ValueError):    # 极圈：上升无恒常定义，如实拒算
        natal.cast(datetime(2000, 9, 14, 8), place=(25.0, 78.2))
    with pytest.raises(ValueError):    # 经度超界
        natal.cast(datetime(2000, 9, 14, 8), place=(190.0, 30.0))
    ch = natal.cast(datetime(2000, 9, 14, 8))    # 无出生地：行为不变
    assert ch.angles is None
    assert "出生地未填" in ch.repro["约定"]
    assert "出生地" not in ch.repro


def test_place_doctrine_phrases():
    # 轴续倾强弱与中天主职业（tetra:3:4）、生时难准（tetra:3:3）逐句对照
    t34 = kb.citation("tetra:3:4")["text"]
    for phrase in ("transiting an angle or succedent house",
                   "especially those of the ascendant, or of the mid-heaven",
                   "cadent from the angles",
                   "the place of the mid-heaven is adapted to questions "
                   "comprised under the head of employment"):
        assert phrase in t34, phrase
    assert "uncertainty as to the precise time of birth" \
        in kb.citation("tetra:3:3")["text"]


def test_cli_birthplace_parse():
    from tianwen import cli
    assert cli._parse_birthplace("116.41,39.90") == (116.41, 39.90)
    assert cli._parse_birthplace("116.41，39.90") == (116.41, 39.90)
    assert cli._parse_birthplace(" ") is None
    with pytest.raises(SystemExit):
        cli._parse_birthplace("北京")


# ── 接线 ───────────────────────────────────────────────────────────

def test_astro_context_wiring():
    s = _chart_session("我是什么命")
    assert s.primary == "chart" and s.astro is not None
    blk = [b for b in s.contexts if "本命盘" in b.title][0]
    ids = [cid for cid, _s, _t in blk.items]
    assert ids[:4] == ["tetra:1:5", "tetra:1:16", "tetra:1:20", "tetra:1:22"]
    assert "tetra:3:18" in ids            # 命格 → 心性章
    assert any("英文原文" in n for n in blk.notes)
    assert "本命盘凭证" in s.repro_text()
    assert "西洋本命盘" in s.overview_text()
    # 时运带题材：分期章＋财帛章
    s2 = _chart_session("今年财运如何")
    blk2 = [b for b in s2.contexts if "本命盘" in b.title][0]
    ids2 = [cid for cid, _s, _t in blk2.items]
    assert "tetra:4:10" in ids2 and "tetra:4:2" in ids2


def test_astro_place_wiring_and_prompt_nudge():
    s = service.prepare("我是什么命", birth_dt=datetime(2000, 9, 14, 8),
                        gender="男", when=datetime(2026, 8, 24, 15, 30),
                        birth_place=(116.41, 39.90))
    blk = [b for b in s.contexts if "本命盘" in b.title][0]
    ids = [cid for cid, _s, _t in blk.items]
    assert ids[:6] == ["tetra:1:5", "tetra:1:16", "tetra:1:20", "tetra:1:22",
                       "tetra:3:4", "tetra:3:3"]
    assert any("上升：天秤宫" in n for n in blk.notes)
    assert "上升天秤宫" in s.overview_text()
    assert "出生地" in s.repro_text() and "上升中天" in s.repro_text()
    # 无出生地：不附 3:4/3:3，第一期行为不变
    s2 = _chart_session("我是什么命")
    ids2 = [cid for cid, _s, _t in
            [b for b in s2.contexts if "本命盘" in b.title][0].items]
    assert "tetra:3:4" not in ids2 and "tetra:3:3" not in ids2
    # 提示词第 5 条明言宜参及西洋盘盘面事实（补「结构在而修辞不见」之缺）
    assert "西洋本命盘" in zllm._SYSTEM
    assert "至少参及一次" in zllm._SYSTEM
    assert "存疑" in zllm._SYSTEM and "勿引" in zllm._SYSTEM


def test_astro_absent_for_event_primary():
    s = service.prepare("考虑跳槽合适吗", birth_dt=datetime(2000, 9, 14, 12),
                        gender="男", when=datetime(2026, 8, 24, 15, 30))
    assert s.primary == "event"
    assert s.astro is None
    assert not [b for b in s.contexts if "本命盘" in b.title]
    assert "本命盘凭证" not in s.repro_text()


def test_astro_payload_carries_convention():
    s = _chart_session("我是什么命")
    allowed = zllm._allowed_texts(s.zkb, s.sel)
    payload = zllm._payload("我是什么命", s.chart, s.sel, s.vd, allowed,
                            s.zkb, s.tp, s.contexts)
    assert "西洋本命盘" in payload
    assert "七曜落宫" in payload and "tetra:1:5" in payload
    assert "逐字照录英文原文" in payload
