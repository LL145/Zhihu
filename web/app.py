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
from tianwen.trigrams import TRIGRAMS, ZHI
from tianwen.ziwei import selection as zselection

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
    """单卦之图形数据：本卦→之卦六爻（自下而上 0/1）、上下卦名与动爻位。"""
    kb = s.kb
    ben, zhi = kb.id_of(cast.ben_binary), kb.id_of(cast.zhi_binary)
    return {"label": label,
            "ben": {"name": kb.full_name(ben), "lines": list(cast.ben_binary),
                    "trigrams": list(kb.hexagram(ben)["trigrams"])},
            "zhi": {"name": kb.full_name(zhi), "lines": list(cast.zhi_binary),
                    "trigrams": list(kb.hexagram(zhi)["trigrams"])},
            "moving": cast.moving[0]}


def _tri(name, rel=None, role=None):
    """单卦（三画）之图形数据：卦画（自下而上 0/1）、五行；与体之生克关系
    （生体／克体／体生／体克／比和，卷一八宫五行所推之盘面事实）。"""
    from tianwen import tiyong
    d = {"name": name, "wx": tiyong.WUXING[name],
         "lines": list(TRIGRAMS[name]["lines"])}
    if rel is not None:
        d["rel"] = rel
    if role is not None:
        d["role"] = role
    return d


def _tiyong_viz(an):
    """体用生克图之数据：体、用、互（下互、上互）、变各卦之五行与生克方向，
    体卦卦气。只列关系事实，不含总诀断语（断语见文本主断）。"""
    from tianwen import tiyong
    return {"ti": _tri(an.ti),
            "yong": _tri(an.yong, tiyong.relation(an.ti, an.yong), "用"),
            "rel": an.rel_yong,
            "hu": [_tri(o.name, o.rel, o.role) for o in an.hu],
            "bian": _tri(an.bian.name, an.bian.rel, an.bian.role),
            "hu_note": an.hu_note, "month": an.month,
            "guaqi": an.guaqi_ti or ""}


def _sanfang(branch):
    """三方四正之宫支：对宫与三合两宫（支序相隔六、四、八）。"""
    i = ZHI.index(branch)
    return [ZHI[(i + k) % 12] for k in (4, 8, 6)]


def _chart_focus(s):
    """盘图所标之宫：所论之宫（主断时为命宫／大限宫／所问之宫，语境时为
    问事分宫）及其三方四正；问时运并标现行大限、太岁与小限所在（皆盘面
    事实，与文本凭证同出一算）。"""
    ch = s.chart
    if s.primary == "chart":
        name = s.sel.palace_name
    else:
        name = (zselection.TOPIC_PALACE.get(s.tp.key)
                or zselection.detect_aspect(s.question)[0] or "命宫")
    p = ch.palace_named(name)
    focus = {"palace": name, "branch": p.branch,
             "sanfang": _sanfang(p.branch)}
    if s.primary == "chart" and s.tp.key == "fortune":
        dp, age = ch.current_daxian(s.when)
        focus["daxian"] = dp.branch if dp is not None else None
        focus["taisui"] = ch.year_branch(s.when)
        focus["xiaoxian"] = ch.xiaoxian_branch(age)
        focus["age"] = age
    return focus


def _astro_viz(a):
    """西洋本命盘之图形数据：七曜黄经与落宫、按宫距相位、同宫并列、得位，
    有出生地则并上升中天与整宫分府（皆 natal.cast 所算之盘面事实）。"""
    from tianwen.astro import natal
    v = {"placements": [{"key": p.key, "name": p.name, "lon": round(p.lon, 2),
                         "sign": natal.sign_name(p.sign_idx),
                         "sign_idx": p.sign_idx, "deg": round(p.deg, 2)}
                        for p in a.placements],
         "aspects": [{"a": x, "b": y, "kind": k, "harmony": h}
                     for x, y, k, h in a.aspects],
         "same_sign": [list(t) for t in a.same_sign],
         "dignities": [list(t) for t in a.dignities],
         "moon_uncertain": a.moon_uncertain, "angles": None}
    ang = a.angles
    if ang is not None:
        v["angles"] = {
            "asc_lon": round(ang.asc_lon, 2), "asc_sign": ang.asc_sign,
            "mc_lon": round(ang.mc_lon, 2), "mc_sign": ang.mc_sign,
            "asc_uncertain": ang.asc_uncertain,
            "mc_uncertain": ang.mc_uncertain,
            "houses": ([[k, h, st] for k, h, st in ang.houses]
                       if ang.houses is not None else None)}
    return v


def _viz(s):
    """结构化盘卦数据（纯呈现层）：网页据以画卦象图、体用生克图、
    十二宫盘图与西洋本命盘图。

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
    an = getattr(s.sel, "tiyong", None) if s.primary == "event" else None
    if an is not None:
        v["tiyong"] = _tiyong_viz(an)
    if s.chart is not None:
        ch = s.chart
        v["chart"] = {
            "tag": "主断" if s.primary == "chart" else "语境·论禀赋",
            "focus": _chart_focus(s),
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
    if s.astro is not None:
        v["astro"] = _astro_viz(s.astro)
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
