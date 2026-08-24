"""配置加载测试：模板生成、占位符识别、环境变量优先。"""

import json

from yijing_agent import config


def _isolate(monkeypatch, tmp_path, files=()):
    """把候选位置与默认位置都指到 tmp_path，隔离真实环境。"""
    paths = [tmp_path / name for name in (files or ("config.json",))]
    monkeypatch.setattr(config, "_candidates", lambda: iter(paths))
    monkeypatch.setattr(config, "default_path", lambda: tmp_path / "config.json")
    for var in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_when_no_file(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = config.load()
    assert cfg["api_key"] == ""
    assert cfg["model"] == config.DEFAULT_MODEL
    assert cfg["base_url"] == config.DEFAULT_BASE_URL


def test_ensure_file_creates_template(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    path, created = config.ensure_file()
    assert created and path.exists()
    data = json.loads(path.read_text("utf-8"))
    assert set(data) == {"api_key", "model", "base_url"}
    # 再次调用不覆盖
    path2, created2 = config.ensure_file()
    assert path2 == path and not created2


def test_placeholder_key_treated_as_unset(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    config.ensure_file()  # 生成的模板 api_key 为中文占位文字
    cfg = config.load()
    assert cfg["api_key"] == ""


def test_real_key_loaded(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"api_key": "sk-or-v1-abc123", "model": "some/model"}), "utf-8")
    cfg = config.load()
    assert cfg["api_key"] == "sk-or-v1-abc123"
    assert cfg["model"] == "some/model"
    assert cfg["base_url"] == config.DEFAULT_BASE_URL


def test_env_overrides_file(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"api_key": "sk-or-v1-file", "model": "file/model"}), "utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-env")
    monkeypatch.setenv("OPENROUTER_MODEL", "env/model")
    cfg = config.load()
    assert cfg["api_key"] == "sk-or-v1-env"
    assert cfg["model"] == "env/model"


def test_is_placeholder():
    assert config._is_placeholder("")
    assert config._is_placeholder("  ")
    assert config._is_placeholder("在这里填入你的 OpenRouter API Key（形如 sk-or-v1-...）")
    assert config._is_placeholder("my key with space")
    assert not config._is_placeholder("sk-or-v1-abc123")
