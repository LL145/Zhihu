"""配置加载：config.json（工作目录或仓库根）与环境变量，环境变量优先。

需要的配置（OpenRouter）：
    api_key   OPENROUTER_API_KEY
    model     OPENROUTER_MODEL（默认 anthropic/claude-sonnet-4.5）
    base_url  OPENROUTER_BASE_URL（默认 https://openrouter.ai/api/v1）
"""

import json
import os
import sys
from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-sonnet-5"  # OpenRouter 模型 ID，config.json 可覆盖
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

TEMPLATE = {
    "api_key": "在这里填入你的 OpenRouter API Key（形如 sk-or-v1-...）",
    "model": DEFAULT_MODEL,
    "base_url": DEFAULT_BASE_URL,
}


def _candidates():
    yield Path.cwd() / "config.json"
    if getattr(sys, "frozen", False):  # PyInstaller 打包后：exe 所在目录
        yield Path(sys.executable).resolve().parent / "config.json"
    yield Path(__file__).resolve().parent.parent / "config.json"


def default_path() -> Path:
    """新建配置文件的位置：打包版在 exe 旁，源码版在项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


def ensure_file():
    """各候选位置均无 config.json 时生成待填模板。返回 (路径, 是否新建)。"""
    for candidate in _candidates():
        if candidate.exists():
            return candidate, False
    path = default_path()
    path.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return path, True


def _is_placeholder(key: str) -> bool:
    """空值、含中文或空格的值视为未填写，避免把模板占位文字当真 key 发出。"""
    key = (key or "").strip()
    return not key or " " in key or any("一" <= ch <= "鿿" for ch in key)


def load() -> dict:
    cfg = {"api_key": "", "model": DEFAULT_MODEL, "base_url": DEFAULT_BASE_URL}
    for candidate in _candidates():
        if candidate.exists():
            cfg.update(json.loads(candidate.read_text("utf-8")))
            break
    if os.environ.get("OPENROUTER_API_KEY"):
        cfg["api_key"] = os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("OPENROUTER_MODEL"):
        cfg["model"] = os.environ["OPENROUTER_MODEL"]
    if os.environ.get("OPENROUTER_BASE_URL"):
        cfg["base_url"] = os.environ["OPENROUTER_BASE_URL"]
    if _is_placeholder(cfg["api_key"]):
        cfg["api_key"] = ""
    return cfg
