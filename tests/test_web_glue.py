"""网页试用胶水层（web/app.py）测试：无 LLM 路径与红线路径。

胶水层在浏览器内（Pyodide）驱动 service 门面；此处按普通模块加载，
保证 service 接口变动不致悄然弄坏网页。LLM 路径不在此测（无网络）。
"""

import importlib.util
import json
from pathlib import Path

import pytest

APP_PY = Path(__file__).parent.parent / "web" / "app.py"


@pytest.fixture()
def app():
    spec = importlib.util.spec_from_file_location("web_app", APP_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(app, **kw):
    payload = {"question": "近期换工作是否合适", "name": "李明",
               "birth": "2000-09-14", "shichen": "午", "gender": "男",
               "when": "2026-08-24T11:00", "apiKey": "", "model": ""}
    payload.update(kw)
    return json.loads(app.run(json.dumps(payload)))


def test_no_key_degrades_with_note(app):
    d = _run(app)
    assert d["kind"] == "plain"
    assert "未填 API Key" in d["text"]
    assert "【结论】" in d["text"] and "定例断辞" in d["text"]
    assert "所问：近期换工作是否合适" in d["text"]


def test_explicit_no_llm_and_chart_primary(app):
    d = _run(app, question="我今年运势如何", noLLM=True)
    assert d["kind"] == "plain"
    assert "未填 API Key" not in d["text"]
    assert "紫微盘（主断）" in d["text"]
    assert "巨门" in d["text"]            # 大限入限诀（确定性，同 CLI）


def test_incomplete_inputs_still_run(app):
    d = _run(app, name="", birth="", shichen="", gender="")
    assert d["kind"] == "plain"
    assert "未提供姓名" in d["text"] and "无紫微盘" in d["text"]


def test_refusal_and_default_model(app):
    d = _run(app, question="我该买哪只股票")
    assert d["kind"] == "refusal"
    # 模型缺省取网页默认（z-ai/glm-5.3），cfg 在红线前即定；
    # 思考力度缺省 low（防深思模型超时），页面下拉可覆盖
    _run(app)
    assert app._cfg["model"] == app.WEB_DEFAULT_MODEL == "z-ai/glm-5.3"
    assert app._cfg["reasoning_effort"] == "low"
    _run(app, reasoningEffort="none")
    assert app._cfg["reasoning_effort"] == "none"


def test_viz_structured_data(app):
    # 卦象图与十二宫图之数据（纯呈现层：只含盘面事实，不含断语）
    d = _run(app, noLLM=True)   # 事类：问语卦主断，盘作语境
    v = d["viz"]
    labels = [c["label"] for c in v["casts"]]
    assert labels[0] == "问语卦（主断）"
    assert any(l.startswith("时间卦") for l in labels)
    assert any(l.startswith("姓名卦") for l in labels)
    c0 = v["casts"][0]
    assert len(c0["ben"]["lines"]) == 6 and set(c0["ben"]["lines"]) <= {0, 1}
    assert 1 <= c0["moving"] <= 6 and c0["ben"]["name"]
    assert v["chart"]["tag"] == "语境·论禀赋"
    assert len(v["chart"]["palaces"]) == 12
    ming = next(p for p in v["chart"]["palaces"] if p["name"] == "命宫")
    assert ming["branch"] == v["chart"]["ming"]
    assert all("stars" in p and "kong" in p for p in v["chart"]["palaces"])

    d = _run(app, question="我的命格如何", noLLM=True)   # 命理：盘主断
    assert d["viz"]["chart"]["tag"] == "主断"


def test_viz_tiyong_figure_data(app):
    # 体用生克图：体、用、互（下互、上互）、变之卦画与五行，关系为事实字样
    d = _run(app, noLLM=True)
    t = d["viz"]["tiyong"]
    rels = {"生体", "克体", "体生", "体克", "比和"}
    assert t["ti"]["name"] and t["ti"]["wx"] in "金木水火土"
    assert len(t["ti"]["lines"]) == 3 and "rel" not in t["ti"]
    assert t["yong"]["rel"] in rels and t["yong"]["role"] == "用"
    assert [h["role"] for h in t["hu"]] == ["下互", "上互"]
    assert t["bian"]["role"] == "变" and t["bian"]["rel"] in rels
    assert t["rel"].startswith(("用", "体")) and t["guaqi"] in ("旺", "衰", "平")
    assert t["month"] == 7                     # 2026-08-24 为农历七月
    assert "zongjue" not in t and "verdict" not in t   # 纯呈现：不含断语
    assert d["viz"]["casts"][0]["ben"]["trigrams"][0] in "乾兑离震巽坎艮坤"
    # 盘作语境时所论之宫为问事分宫（事业→官禄）及其三方四正
    fo = d["viz"]["chart"]["focus"]
    assert fo["palace"] == "官禄" and len(fo["sanfang"]) == 3
    assert fo["branch"] not in fo["sanfang"] and "daxian" not in fo
    # 盘主断（时运）：并标现行大限、太岁、小限
    d = _run(app, question="我今年运势如何", noLLM=True)
    fo = d["viz"]["chart"]["focus"]
    assert fo["daxian"] and fo["taisui"] and fo["xiaoxian"] and fo["age"] > 0
    assert fo["palace"] == next(p["name"] for p in d["viz"]["chart"]["palaces"]
                                if p["branch"] == fo["daxian"])
    assert "tiyong" not in d["viz"]            # 盘主断：无体用之图


def test_viz_astro_wheel_data(app):
    # 西洋本命盘图：只随命理主断出；七曜黄经落宫、相位、上升中天与分府
    d = _run(app, noLLM=True)
    assert "astro" not in d["viz"]
    d = _run(app, question="我的命格如何", noLLM=True)
    a = d["viz"]["astro"]
    assert [p["key"] for p in a["placements"]] == [
        "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
    for p in a["placements"]:
        assert 0 <= p["lon"] < 360 and p["sign_idx"] == int(p["lon"] // 30)
        assert p["sign"].endswith("宫") and 0 <= p["deg"] < 30
    assert all(x["harmony"] in ("和", "不和") for x in a["aspects"])
    assert a["angles"] is None                 # 未填出生地：无上升分府
    d = _run(app, question="我的命格如何", noLLM=True,
             shichen="辰", lon="116.41", lat="39.90")
    ang = d["viz"]["astro"]["angles"]
    assert 0 <= ang["asc_lon"] < 360 and ang["asc_sign"] == int(ang["asc_lon"] // 30)
    assert ang["houses"] is None or (
        len(ang["houses"]) == 7 and all(1 <= h <= 12 for _k, h, _s in ang["houses"]))


def test_birthplace_pair_and_ascendant(app):
    # 出生地成对填写 → 命理主断凭证含上升中天与出生地
    d = _run(app, question="我的命格如何", noLLM=True,
             shichen="辰", lon="116.41", lat="39.90")
    assert d["kind"] == "plain"
    assert "出生地" in d["text"] and "上升中天" in d["text"]
    # 只填一项：如实报错，不猜另一半
    d = _run(app, question="我的命格如何", noLLM=True, lon="116.41")
    assert d["kind"] == "error" and "成对" in d["text"]


def test_followup_requires_interpret(app):
    _run(app)
    d = json.loads(app.followup("再细说"))
    assert d["kind"] == "error" and "追问" in d["text"]
