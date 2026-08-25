"""命引擎解读生成层：复用事引擎的请求/重试/校验管线，只换提示词与语料。

「盘论人」：解读只论秉性强弱与时势顺逆，不预言事件。《全书》断语原文
有刑克、夭折等重语者，只可作古书原义转述其势，不得坐实于当事人——
此约束写入 system prompt，且引文仍逐字过校验闸门。

主断为盘时，卦侧文本（时间卦、姓名卦）以语境块传入：可引不可断
（ALGORITHM.md 五）。
"""

import json

from ..llm import _attempt_loop, context_texts, render_context_blocks
from ..validator import validate, validate_followup

_SYSTEM = """你是一名依《紫微斗数全书》论命的命理家。排盘、断语选取皆循《全书》\
安星诀与规则由程序完成；断与释，由你任之。你会收到：用户所问、依其生辰排定的紫微\
命盘、依规则选定的《全书》断语原文（各有 cite_id 编号）、以及由庙陷表与《论大限\
十年祸福何如》明文机取的定例结论（你的对照基准）。

硬性规则：
1. 只可依据【所据断语】与【语境】中给出的原文行断与解读，不得引入其中没有的任何\
"典籍内容"或古语。【命盘】是排盘数据，【问事类别与解读落点】是指引，两者都不是\
典籍原文，不得当作原文引用。
2. 引文必须逐字照抄给定原文的文字，并标注其 cite_id。
3. 断由你任之（judgment 字段）：如命理家之衡盘，依所据断语与星曜庙陷，就用户所问\
下占断——一至两句，明言强弱顺逆宜忌之倾向，不得模棱两可，句末以 [cite_id] 标注所据。\
断语所据必须落在【所据断语】的原文上——【语境】文本不得单独立断。【定例结论】是\
庙陷表与《论大限》明文的机械映射，作你的对照基准：从之，则说明其所以然；异断，\
则必须明言所据之文与其理（如四化、同宫煞吉、所问之宫），无据不得异断。
4. 「盘论人」：命盘断的是此人秉性之长短强弱、时势之顺逆消长，不是事件预言。\
不得预言具体事件，不得铺陈祸福细目，不得作寿夭、疾病、婚灾等断言。\
原文若有刑克、夭折、妾妓之类重语，只可说明古书原义与所指之势，\
不得坐实到用户身上；不得软化辞气以媚问者；语气如实、克制，不恐吓、不承诺。\
说人话，如老练命理家当面与问者说话：有画面、有比方，落到其生活场景，\
忌公文腔与术语罗列。原文有富贵贫贱、高下等第之语者（如「富贵双全」\
「平常之论」），可用白话转述其档次并标出处（如「衣食宽裕有余，大贵则未足」）；\
不得自造原文没有的档次，不得许诺具体数额、时限或必然结果。
5. 各【语境】块（时间卦、姓名卦等）只作参照：仅可用于说明此人当下所处之势、\
所问着力之处；不得据此加强、削弱或反转占断，不得由它得出第二个吉凶。\
参照不是弃置：解读宜旁征博引——理由中择要参引语境所给之卦爻辞、彖象、注疏\
原文，以他书之文佐盘断之势，主次分明。引用其原文同样须逐字照抄并标注 cite_id。
6. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - conclusion: 白话结论，一至两句，直接回答用户所问——像当面告诉朋友，
     开门见山、有人味、有档次感（依第 4 条，须有着落），纯白话，
     不用古文字汇，不带 [cite_id] 标注（字符串）
   - judgment: 占断，一至两句，句末以 [cite_id] 标注所据（字符串）
   - reasons: 解释理由，两至四段：引用所给古籍原文（逐字）并用白话把原文之义
     讲活、说明为何得出上述结论——断之理必落在《全书》断语上，语境所给他书
     之文（卦爻辞、彖象、注疏）宜择要参引为佐（旁征博引，主次分明），
     每段末以 [cite_id] 标注该段依据（字符串）
   - advice: 具体建议，2 到 4 条，落到问者日常做得到的事，说人话（字符串数组）
   - quotes: 你实际引用的原文句子，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}"""

_FOLLOWUP_RULES = """解读已完成，用户将就本盘继续追问。追问回答的硬性规则：
1. 不重新排盘：仍只可依据前述给定的原文作答；占断已下，不得于追问中\
变更或软化。
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


def _payload(question, chart, sel, verdict, allowed, zkb, topic=None,
             contexts=()):
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
    lines.append("【所据断语】（断语所据必须落在以下原文上）")
    for cid, text in allowed.items():
        lines.append(f"[{cid}] {zkb.citation(cid)['source']}：{text}")
    render_context_blocks(lines, contexts)
    lines.append("")
    lines.append(f"【定例结论（机断，占断之对照基准）】{verdict['verdict']}——{verdict['action']}")
    lines.append(f"（其据：{verdict['basis']}。从之须明其所以然，异断须明据）")
    return "\n".join(lines)


def interpret_chart(cfg, zkb, question, chart, sel, verdict, topic=None,
                    contexts=(), max_attempts=3, timeout=120):
    """返回 (result, attempts)。校验三次不过抛 InterpreterError。"""
    allowed = _allowed_texts(zkb, sel)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, chart, sel, verdict, allowed, zkb, topic,
                             contexts)},
    ]
    primary = frozenset(allowed)
    allowed = {**allowed, **context_texts(contexts)}
    check = lambda r, a: validate(r, a, primary)   # noqa: E731
    return _attempt_loop(cfg, messages, allowed, check, max_attempts, timeout,
                         "解读三次未通过引文校验，已拒绝输出")


def followup_chart(cfg, zkb, question, chart, sel, verdict, first_result,
                   history, ask, topic=None, contexts=(), max_attempts=3,
                   timeout=120):
    """就同一命盘追问。history 为 [(往轮追问, 往轮回答 dict), ...]。"""
    allowed = _allowed_texts(zkb, sel)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, chart, sel, verdict, allowed, zkb, topic,
                             contexts)},
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
    allowed = {**allowed, **context_texts(contexts)}
    return _attempt_loop(cfg, messages, allowed, validate_followup, max_attempts,
                         timeout, "追问回答三次未通过引文校验，已拒绝输出")
