"""命引擎解读生成层：复用事引擎的请求/重试/校验管线，只换提示词与语料。

「盘论人」：解读只论秉性强弱与时势顺逆，不预言事件。《全书》断语原文
有刑克、夭折等重语者，只可作古书原义转述其势，不得坐实于当事人——
此约束写入 system prompt，且引文仍逐字过校验闸门。
"""

import json

from ..llm import _attempt_loop
from ..validator import validate, validate_followup

_SYSTEM = """你是一名严谨的《紫微斗数全书》典籍讲解者。你会收到：用户所问、\
依其生辰排定的紫微命盘、依规则选定的《紫微斗数全书》断语原文（各有 cite_id 编号）、\
以及由规则（庙陷表与《论大限十年祸福何如》明文）确定的结论。

硬性规则：
1. 只可依据【所据断语】中给出的原文进行解读，不得引入其中没有的任何"典籍内容"或古语。\
【命盘】是排盘数据，【问事类别与解读落点】是指引，两者都不是典籍原文，不得当作原文引用。
2. 引文必须逐字照抄【所据断语】的文字，并标注其 cite_id。
3. 结论（verdict/action）由规则给定且已向用户展示，你不得改判、弱化或加强。\
你的解读只回答"这个结论落在用户所问上意味着什么、怎么做"。
4. 「盘论人」：命盘断的是此人秉性之长短强弱、时势之顺逆消长，不是事件预言。\
不得预言具体事件，不得铺陈祸福细目，不得作寿夭、疾病、婚灾等断言。\
原文若有刑克、夭折、妾妓之类重语，只可说明古书原义与所指之势，\
不得坐实到用户身上；语气如实、克制，不恐吓、不承诺。
5. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - translation: 对主断断语的白话直译（字符串）
   - interpretation: 针对所问的解读，两至四段，每段末以 [cite_id] 标注该段依据（字符串）
   - advice: 具体建议，2 到 4 条（字符串数组）
   - quotes: 你实际引用的原文句子，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}"""

_FOLLOWUP_RULES = """解读已完成，用户将就本盘继续追问。追问回答的硬性规则：
1. 不重新排盘：仍只可依据前述【所据断语】的原文作答；结论（verdict/action）不变，\
不得改判、弱化或加强。
2. 引用原文须逐字照抄并标注 cite_id；追问不必强行引书，无合适原文可不引。
3. 追问若超出本盘所据断语可答的范围（问具体某事吉凶当另起卦、追问祸福细目、\
要求预言事实结果），如实说明须另占或无法由本盘断语得出，不得杜撰。
4. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - answer: 针对追问的回答，一至两段（字符串）
   - quotes: 实际引用的原文，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}，可为空数组"""


def _allowed_texts(zkb, sel):
    allowed = {}
    for r in sel.readings:
        allowed[r.cite_id] = zkb.citation(r.cite_id)["text"]
        for cid in r.context_ids:
            allowed[cid] = zkb.citation(cid)["text"]
    return allowed


def _chart_summary(chart):
    lines = [f"{chart.lunar.description}（公历 {chart.solar_desc}），"
             f"{chart.yinyang}，{chart.wuxing_ju}，"
             f"命宫在{chart.ming_branch}，身宫在{chart.shen_branch}"]
    for p in chart.palaces:
        stars = "、".join(
            s.name + (s.brightness or "")
            + (f"化{s.sihua}" if s.sihua else "") for s in p.stars) or "（无星）"
        lines.append(f"{p.name}（{p.gz}，限{p.daxian[0]}-{p.daxian[1]}）：{stars}")
    return lines


def _payload(question, chart, sel, verdict, allowed, zkb, topic=None):
    lines = [f"【所问之事】{question}", ""]
    if topic is not None:
        lines.append("【问事类别与解读落点】（占法指引，非典籍原文，不得作为引文）")
        lines.append(f"{topic.name}：{topic.note}")
        lines.append("")
    lines.append("【命盘】（排盘数据，非典籍原文）")
    lines.extend(_chart_summary(chart))
    for note in sel.notes:
        lines.append(f"※ {note}")
    lines.append("")
    lines.append(f"【选文规则】{sel.rule}")
    lines.append("")
    lines.append("【所据断语】（解读只可使用以下原文）")
    for cid, text in allowed.items():
        lines.append(f"[{cid}] {zkb.citation(cid)['source']}：{text}")
    lines.append("")
    lines.append(f"【结论（规则已定，不得更改）】{verdict['verdict']}——{verdict['action']}")
    lines.append(f"（结论依据：{verdict['basis']}）")
    return "\n".join(lines)


def interpret_chart(cfg, zkb, question, chart, sel, verdict, topic=None,
                    max_attempts=3, timeout=120):
    """返回 (result, attempts)。校验三次不过抛 InterpreterError。"""
    allowed = _allowed_texts(zkb, sel)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, chart, sel, verdict, allowed, zkb, topic)},
    ]
    return _attempt_loop(cfg, messages, allowed, validate, max_attempts, timeout,
                         "解读三次未通过引文校验，已拒绝输出")


def followup_chart(cfg, zkb, question, chart, sel, verdict, first_result,
                   history, ask, topic=None, max_attempts=3, timeout=120):
    """就同一命盘追问。history 为 [(往轮追问, 往轮回答 dict), ...]。"""
    allowed = _allowed_texts(zkb, sel)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, chart, sel, verdict, allowed, zkb, topic)},
        {"role": "assistant", "content": json.dumps(first_result, ensure_ascii=False)},
    ]
    first = True
    for prev_ask, prev_result in history:
        prefix = _FOLLOWUP_RULES + "\n\n" if first else ""
        messages.append({"role": "user", "content": f"{prefix}【追问】{prev_ask}"})
        messages.append({"role": "assistant",
                         "content": json.dumps(prev_result, ensure_ascii=False)})
        first = False
    prefix = _FOLLOWUP_RULES + "\n\n" if first else ""
    messages.append({"role": "user", "content": f"{prefix}【追问】{ask}"})
    return _attempt_loop(cfg, messages, allowed, validate_followup, max_attempts,
                         timeout, "追问回答三次未通过引文校验，已拒绝输出")
