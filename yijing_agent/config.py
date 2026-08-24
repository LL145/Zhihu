"""配置加载：config.json（工作目录或仓库根）与环境变量，环境变量优先。

需要的配置（OpenRouter）：
    api_key   OPENROUTER_API_KEY
    model     OPENROUTER_MODEL（默认 anthropic/claude-sonnet-4.5）
    base_url  OPENROUTER_BASE_URL（默认 https://openrouter.ai/api/v1）
"""

import json
import os
from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def load() -> dict:
    cfg = {"api_key": "", "model": DEFAULT_MODEL, "base_url": DEFAULT_BASE_URL}
    for candidate in (Path.cwd() / "config.json",
                      Path(__file__).resolve().parent.parent / "config.json"):
        if candidate.exists():
            cfg.update(json.loads(candidate.read_text("utf-8")))
            break
    if os.environ.get("OPENROUTER_API_KEY"):
        cfg["api_key"] = os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("OPENROUTER_MODEL"):
        cfg["model"] = os.environ["OPENROUTER_MODEL"]
    if os.environ.get("OPENROUTER_BASE_URL"):
        cfg["base_url"] = os.environ["OPENROUTER_BASE_URL"]
    return cfg
