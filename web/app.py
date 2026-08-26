"""网页试用之胶水层：在浏览器内（Pyodide）驱动 service 门面。

与 cli.py 同一门面、同一流程（ALGORITHM.md）：红线→判类→三占同起→
主断唯一→解读过校验闸门；此层只做输入解析与 JSON 进出，不含任何占法
逻辑。API Key 由页面输入、只存于用户浏览器，请求直达 OpenRouter。
"""

import json
import traceback
from datetime import datetime

from tianwen import config as twconfig
from tianwen import service
from tianwen.llm import InterpreterError
from tianwen.trigrams import ZHI

WEB_DEFAULT_MODEL = "z-ai/glm-5.3"

_session = None   # 追问沿用同一会话与配置，不重新起卦（ALGORITHM.md）
_cfg = None


def _birth_dt(p):
    date = (p.get("birth") or "").strip()
    shichen = (p.get("shichen") or "").strip()
    if not date or shichen not in ZHI:
        return None
    y, m, d = (int(x) for x in date.split("-"))
    return datetime(y, m, d, ZHI.index(shichen) * 2)   # 时辰由整点小时唯一确定


def _birth_place(p):
    """出生地经纬（可缺，供西洋盘上升与分府）；只填一项如实报错。"""
    lon = str(p.get("lon") or "").strip()
    lat = str(p.get("lat") or "").strip()
    if not lon and not lat:
        return None
    if not (lon and lat):
        raise ValueError("出生地经纬度须成对填写（或都留空——"
                         "留空则不算上升与分府，余皆照常）")
    return float(lon), float(lat)


def _when(p):
    w = (p.get("when") or "").strip()
    if not w:
        return None    # prepare 缺省取 now_beijing()：按北京时间，可复现
    return datetime.strptime(w[:16], "%Y-%m-%dT%H:%M")


def _gua_viz(s, cast, label):
    """单卦之图形数据：本卦→之卦六爻（自下而上 0/1）与动爻位。"""
    kb = s.kb
    ben, zhi = kb.id_of(cast.ben_binary), kb.id_of(cast.zhi_binary)
    return {"label": label,
            "ben": {"name": kb.full_name(ben), "lines": list(cast.ben_binary)},
            "zhi": {"name": kb.full_name(zhi), "lines": list(cast.zhi_binary)},
            "moving": cast.moving[0]}


def _viz(s):
    """结构化盘卦数据（纯呈现层）：网页据以画卦象图与十二宫盘图。

    只含盘面事实，不含断语与结论——图是文本输出的插图，不是第二来源。"""
    casts = []
    if s.primary == "event" and s.event_cast is not s.time_cast:
        casts.append(_gua_viz(s, s.event_cast, "问语卦（主断）"))
        casts.append(_gua_viz(s, s.time_cast, "时间卦（参·当下之势）"))
    elif s.primary == "event":
        casts.append(_gua_viz(s, s.time_cast, "时间卦（主断·问语无字回落）"))
    else:
        casts.append(_gua_viz(s, s.time_cast, "时间卦（参·当下之势）"))
    if s.name_cast is not None:
        casts.append(_gua_viz(s, s.name_cast,
                              f"姓名卦「{s.name}」（参·论问者之位）"))
    v = {"casts": casts}
    if s.chart is not None:
        ch = s.chart
        v["chart"] = {
            "tag": "主断" if s.primary == "chart" else "语境·论禀赋",
            "ming": ch.ming_branch, "shen": ch.shen_branch,
            "yinyang": ch.yinyang, "ju": ch.wuxing_ju,
            "daxian_dir": "顺" if ch.daxian_forward else "逆",
            "lunar": ch.lunar.description, "solar": ch.solar_desc,
            "palaces": [
                {"name": p.name, "branch": p.branch, "gz": p.gz,
                 "body": p.is_body, "daxian": list(p.daxian),
                 "kong": ch.kong_marks(p.branch),
                 "stars": [{"n": st.name, "k": st.kind, "b": st.brightness,
                            "h": st.sihua} for st in p.stars]}
                for p in ch.palaces],
        }
    return v


def _degraded(s, e, full):
    lines = [f"〔解读不可用〕{e}"]
    lines += [f"  - {err}" for err in e.errors]
    lines.append("已降级为定例断辞与原文的输出。")
    return "\n".join(lines) + "\n\n" + s.render_all(full=full)


def run(payload):
    """起占一次。payload/返回值均为 JSON 字符串（worker 进出）。"""
    global _session, _cfg
    p = json.loads(payload)
    _session = None
    _cfg = {"api_key": (p.get("apiKey") or "").strip(),
            "model": (p.get("model") or "").strip() or WEB_DEFAULT_MODEL,
            # baseUrl 不入界面：端到端测试与自代理之留口
            "base_url": (p.get("baseUrl") or "").strip()
                        or twconfig.DEFAULT_BASE_URL,
            # 思考力度（防深思模型超时）；页面下拉四值 low/medium/high/none
            "reasoning_effort": (p.get("reasoningEffort") or "").strip()
                                or twconfig.DEFAULT_REASONING_EFFORT}
    use_llm = bool(_cfg["api_key"]) and not p.get("noLLM")
    full = bool(p.get("full"))
    try:
        tp = service.resolve_topic(p.get("question"),
                                   cfg=_cfg if use_llm else None)
        s = service.prepare(p.get("question"), name=p.get("name") or "",
                            birth_dt=_birth_dt(p),
                            gender=p.get("gender") or None,
                            when=_when(p), tp=tp,
                            birth_place=_birth_place(p))
    except service.RefusalError as e:
        return json.dumps({"kind": "refusal", "text": str(e)})
    except ValueError as e:
        return json.dumps({"kind": "error", "text": str(e)})
    except Exception:
        return json.dumps({"kind": "error", "text": traceback.format_exc()})
    if not use_llm:
        text = s.render_all(full=full)
        if not p.get("noLLM"):
            text = "（未填 API Key：结论直取定例断辞，无大模型解读。）\n\n" + text
        return json.dumps({"kind": "plain", "text": text, "viz": _viz(s)})
    try:
        text, _attempts = s.interpret(_cfg, full=full)
    except InterpreterError as e:
        return json.dumps({"kind": "plain", "text": _degraded(s, e, full),
                           "viz": _viz(s)})
    except Exception:
        return json.dumps({"kind": "error", "text": traceback.format_exc()})
    _session = s
    return json.dumps({"kind": "llm", "text": text, "viz": _viz(s)})


def followup(ask):
    """就上次解读追问（不重新起卦；逐问过红线）。"""
    if _session is None:
        return json.dumps({"kind": "error",
                           "text": "须先完成一次大模型解读方可追问"})
    try:
        return json.dumps({"kind": "followup",
                           "text": _session.followup(_cfg, ask)})
    except service.RefusalError as e:
        return json.dumps({"kind": "refusal", "text": str(e)})
    except InterpreterError as e:
        lines = [f"〔追问回答不可用〕{e}"] + [f"  - {err}" for err in e.errors]
        return json.dumps({"kind": "error", "text": "\n".join(lines)})
    except Exception:
        return json.dumps({"kind": "error", "text": traceback.format_exc()})
