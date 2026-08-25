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
    # 模型缺省取网页默认（z-ai/glm-5.3），cfg 在红线前即定
    _run(app)
    assert app._cfg["model"] == app.WEB_DEFAULT_MODEL == "z-ai/glm-5.3"


def test_followup_requires_interpret(app):
    _run(app)
    d = json.loads(app.followup("再细说"))
    assert d["kind"] == "error" and "追问" in d["text"]
