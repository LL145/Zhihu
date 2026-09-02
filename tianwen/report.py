"""终端呈现层：结论先行（ALGORITHM.md 六），卦象图、所据原文节选、
复现凭证与免责声明。

内部引文编号（cite_id，如 zhouyi:49:yao:5）只在校验层流转；对外展示
一律换成古籍原名（humanize：〔《周易·革·九五》爻辞〕），编号可用
py -m tianwen.corpus 按书名或编号取全文核对。"""

import re

DISCLAIMER = ("内容源自古代典籍原文及传统占法，属传统文化范畴，仅供参考，"
              "不构成任何现实决策依据。")

_CITE_MARK = re.compile(r"\[([a-z]+:[0-9]+(?::[a-z0-9]+)*)\]")


def humanize(text, resolve):
    """把文中的内部引文编号换成古籍原名：[zhouyi:1:guaci] → 〔《周易·乾》卦辞〕。

    resolve(cite_id) → 出处名或 None（未知编号原样保留，不吞不改）。
    """
    if resolve is None:
        return text

    def _sub(m):
        src = resolve(m.group(1))
        return f"〔{src}〕" if src else m.group(0)

    return _CITE_MARK.sub(_sub, text)

_YANG = "━━━━━━━"
_YIN = "━━━ ━━━"


def render_hexagram(kb, lines, moving):
    """自上而下绘制六爻，动爻加标记。lines 为爻值 6/7/8/9 自下而上。"""
    from . import hexagrams
    ben_id = kb.id_of(hexagrams.lines_to_binary(lines))
    h = kb.hexagram(ben_id)
    rows = []
    for pos in range(6, 0, -1):
        v = lines[pos - 1]
        art = _YANG if v in (7, 9) else _YIN
        name = h["yao"][pos - 1]["name"]
        mark = "  ← 动" if pos in moving else ""
        rows.append(f"  {name} {art}{mark}")
    return "\n".join(rows)


def render_cast(kb, cast):
    from . import hexagrams
    ben_id = kb.id_of(cast.ben_binary)
    zhi_id = kb.id_of(cast.zhi_binary)
    hu_id = kb.id_of(cast.hu_binary)
    ben, zhi, hu = kb.hexagram(ben_id), kb.hexagram(zhi_id), kb.hexagram(hu_id)
    out = []
    out.append(f"本卦：{ben['symbol']} {kb.full_name(ben_id)}"
               + (f"　→　之卦：{zhi['symbol']} {kb.full_name(zhi_id)}" if cast.moving else "（六爻安静）"))
    out.append(f"互卦：{hu['symbol']} {kb.full_name(hu_id)}")
    out.append("")
    out.append(render_hexagram(kb, cast.lines, cast.moving))
    return "\n".join(out)


def render_repro(cast):
    out = ["── 起卦凭证（可复现） " + "─" * 20]
    for k, v in cast.reproducibility.items():
        out.append(f"  {k}：{v}")
    return "\n".join(out)


def render_readings_compact(kb, selection):
    """所据原文节选：主断条目附全文（含所系传文），其余只列古籍原名；
    全文可用 python -m tianwen.corpus --cite <书名> 随时核对。"""
    out = [f"── 所据原文（{selection.rule}；节选，全文见 corpus） " + "─" * 4]
    notes = getattr(selection, "notes", None) or ()
    for note in notes:
        out.append(f"  ※ {note}")
    for r in selection.readings:
        c = kb.citation(r.cite_id)
        if r.primary:
            out.append(f"  ◆ {r.role}")
            excerpt = getattr(r, "excerpt", None)
            if excerpt:
                out.append(f"    {c['source']}：「{excerpt}」（节引）")
            else:
                out.append(f"    {c['source']}：{c['text']}")
            for cid in r.context_ids:
                ctx = kb.citation(cid)
                out.append(f"      · {ctx['source']}：{ctx['text']}")
        else:
            out.append(f"  ◇ {r.role}：{c['source']}")
    return "\n".join(out)


def render_verdict(verdict):
    audited = "（人工审定）" if verdict["audited"] else "（自动提取，待人工审定）"
    return (f"══ 断辞结论（定例·机断） ══════════════\n"
            f"  【{verdict['verdict']}】{verdict['action']}\n"
            f"  依据：{verdict['basis']} {audited}")


_TOPIC_SOURCE = {"llm": "〔占者判类〕", "user": "〔用户指定〕"}


def topic_source_label(topic):
    """判类来源标注：规则命中不注，占者判类/用户指定如实标明。"""
    return _TOPIC_SOURCE.get(getattr(topic, "source", "rule"), "")


def render_followup(result, resolve=None):
    out = ["〔答〕" + humanize(result["answer"], resolve)]
    for q in result.get("quotes", []):
        src = resolve(q["cite_id"]) if resolve else None
        label = src or f"[{q['cite_id']}]"
        out.append(f"    · {label}：「{q['text']}」")
    return "\n".join(out)


def render_interpretation(result, resolve=None):
    """结论先行（ALGORITHM.md 六）：白话结论 → 断语 → 理由 → 建议。

    resolve 供 humanize 把断语与理由中的引文编号换成古籍原名。"""
    out = ["【结论】" + result["conclusion"]]
    out.append("")
    out.append("【断语】" + humanize(result["judgment"], resolve))
    out.append("")
    out.append("【理由】（占者：大模型；引文已逐字校验）")
    out.append(humanize(result["reasons"], resolve))
    out.append("")
    out.append("【建议】")
    for i, a in enumerate(result["advice"], 1):
        out.append(f"  {i}. {humanize(a, resolve)}")
    return "\n".join(out)


def attestation(model, result, attempts):
    """占断存证：有条件可复现的凭证之一。

    起卦/排盘/选文/定例由种子与时刻唯一确定，可重放复算；占断出自模型
    （同问未必同断，如古之占者），以本存证哈希为准——定种子与存证，即定全局。
    """
    import hashlib
    import json
    digest = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ("── 占断存证 " + "─" * 28 + "\n"
            f"  占者模型：{model}；第 {attempts} 次生成通过逐字校验\n"
            f"  输出摘要：SHA-256 {digest}\n"
            "  可复现性：起卦/排盘/选文/定例同种子必同刻可复算；"
            "占断非确定，以本存证为准")
