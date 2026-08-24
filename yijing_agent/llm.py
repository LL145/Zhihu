"""解读生成层：调用 OpenRouter（OpenAI 兼容接口），只解释、不改判。

生成结果须通过 validator 的逐字引文校验；三次不过则抛出 InterpreterError，
调用方降级为「仅原文 + 结论」的无解读模式。

多轮追问（followup）不重新起卦：同一份【所据文本】、同一 verdict，
每轮回答同样过校验闸门。
"""

import json

import requests

from .validator import validate, validate_followup

_SYSTEM = """你是一名严谨的《周易》典籍讲解者。你会收到：用户所问之事、起卦结果、\
依占法规则选定的经文原文（各有 cite_id 编号）、以及由规则确定的结论（verdict 与 action）。

硬性规则：
1. 只可依据【所据文本】中给出的原文进行解读，不得引入其中没有的任何"典籍内容"或古语。\
【问事类别与解读落点】是占法指引而非典籍原文，只用于确定解读方向，不得当作原文引用。
2. 引文必须逐字照抄【所据文本】的文字，并标注其 cite_id。
3. 结论（verdict/action）由规则给定且已向用户展示，你不得改判、弱化或加强——\
不得把「凶」说成「略有不顺」，也不得把「谨」拔高为「大吉」。你的解读只回答\
"这个结论落在用户所问之事上意味着什么、怎么做"。
4. 解读须紧扣用户所问之事及其类别落点，落到可执行的层面；语气如实、克制，\
不恐吓、不承诺、不故弄玄虚。
5. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - translation: 对主断经文的白话直译（字符串）
   - interpretation: 针对所问之事的解读，两至四段，每段末以 [cite_id] 标注该段依据（字符串）
   - advice: 具体建议，2 到 4 条（字符串数组）
   - quotes: 你实际引用的原文句子，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}"""

_FOLLOWUP_RULES = """解读已完成，用户将就本卦继续追问。追问回答的硬性规则：
1. 不重新起卦：仍只可依据前述【所据文本】的原文作答；结论（verdict/action）不变，\
不得改判、弱化或加强。
2. 引用原文须逐字照抄并标注 cite_id；追问不必强行引经，无合适原文可不引。
3. 追问若超出本卦所据文本可答的范围（另问一事、追问具体祸福细节、要求预言事实结果），\
如实说明须另占或无法由本卦文本得出，不得杜撰。
4. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - answer: 针对追问的回答，一至两段（字符串）
   - quotes: 实际引用的原文，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}，可为空数组"""


class InterpreterError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def _allowed_texts(kb, selection):
    allowed = {}
    for r in selection.readings:
        allowed[r.cite_id] = kb.citation(r.cite_id)["text"]
        for cid in r.context_ids:
            allowed[cid] = kb.citation(cid)["text"]
    return allowed


def _payload(question, cast, selection, verdict, allowed_texts, kb, topic=None):
    lines = [f"【所问之事】{question}", ""]
    if topic is not None:
        lines.append("【问事类别与解读落点】（占法指引，非典籍原文，不得作为引文）")
        lines.append(f"{topic.name}：{topic.note}")
        lines.append("")
    lines.append("【起卦结果】")
    for k, v in cast.reproducibility.items():
        lines.append(f"{k}：{v}")
    lines.append("")
    lines.append(f"【占法】{selection.rule}")
    lines.append("")
    lines.append("【所据文本】（解读只可使用以下原文）")
    for cid, text in allowed_texts.items():
        lines.append(f"[{cid}] {kb.citation(cid)['source']}：{text}")
    lines.append("")
    lines.append(f"【结论（规则已定，不得更改）】{verdict['verdict']}——{verdict['action']}")
    lines.append(f"（结论依据主断经文 [{verdict['cite_id']}] 之断辞）")
    return "\n".join(lines)


def _parse_json(text):
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("输出中未找到 JSON 对象")
    return json.loads(s[start:end + 1])


def _request(cfg, messages, timeout):
    resp = requests.post(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "X-Title": "Zhihu Yijing Agent",
        },
        json={"model": cfg["model"], "messages": messages, "temperature": 0.4},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise InterpreterError(f"OpenRouter 请求失败 HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]


def _attempt_loop(cfg, messages, allowed, check, max_attempts, timeout, fail_msg):
    """请求→解析→校验，不过则带原因重试。messages 会被原地追加。"""
    last_errors = []
    for attempt in range(1, max_attempts + 1):
        content = _request(cfg, messages, timeout)
        try:
            result = _parse_json(content)
        except (ValueError, json.JSONDecodeError) as e:
            last_errors = [f"JSON 解析失败: {e}"]
        else:
            last_errors = check(result, allowed)
            if not last_errors:
                return result, attempt
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content":
                         "你的输出未通过校验，问题如下，请改正后重新输出完整 JSON：\n- "
                         + "\n- ".join(last_errors)})
    raise InterpreterError(fail_msg, last_errors)


def interpret(cfg, kb, question, cast, selection, verdict, topic=None,
              max_attempts=3, timeout=120):
    """返回 (result, attempts)。校验三次不过抛 InterpreterError。"""
    allowed = _allowed_texts(kb, selection)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, cast, selection, verdict, allowed, kb, topic)},
    ]
    return _attempt_loop(cfg, messages, allowed, validate, max_attempts, timeout,
                         "解读三次未通过引文校验，已拒绝输出")


def followup(cfg, kb, question, cast, selection, verdict, first_result,
             history, ask, topic=None, max_attempts=3, timeout=120):
    """就同一卦追问。history 为 [(往轮追问, 往轮回答 dict), ...]。返回 (result, attempts)。"""
    allowed = _allowed_texts(kb, selection)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, cast, selection, verdict, allowed, kb, topic)},
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
