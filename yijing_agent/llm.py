"""解读生成层：调用 OpenRouter（OpenAI 兼容接口），只解释、不改判。

生成结果须通过 validator 的逐字引文校验；三次不过则抛出 InterpreterError，
调用方降级为「仅原文 + 结论」的无解读模式。
"""

import json

import requests

from .validator import validate

_SYSTEM = """你是一名严谨的《周易》典籍讲解者。你会收到：用户所问之事、起卦结果、\
依占法规则选定的经文原文（各有 cite_id 编号）、以及由规则确定的结论（verdict 与 action）。

硬性规则：
1. 只可依据【所据文本】中给出的原文进行解读，不得引入其中没有的任何"典籍内容"或古语。
2. 引文必须逐字照抄【所据文本】的文字，并标注其 cite_id。
3. 结论（verdict/action）由规则给定且已向用户展示，你不得改判、弱化或加强——\
不得把「凶」说成「略有不顺」，也不得把「谨」拔高为「大吉」。你的解读只回答\
"这个结论落在用户所问之事上意味着什么、怎么做"。
4. 解读须紧扣用户所问之事，落到可执行的层面；语气如实、克制，不恐吓、不承诺、不故弄玄虚。
5. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - translation: 对主断经文的白话直译（字符串）
   - interpretation: 针对所问之事的解读，两至四段，每段末以 [cite_id] 标注该段依据（字符串）
   - advice: 具体建议，2 到 4 条（字符串数组）
   - quotes: 你实际引用的原文句子，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}"""


class InterpreterError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def _payload(question, cast, selection, verdict, allowed_texts, kb):
    lines = [f"【所问之事】{question}", "", "【起卦结果】"]
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


def interpret(cfg, kb, question, cast, selection, verdict, max_attempts=3, timeout=120):
    """返回 (result, attempts)。校验三次不过抛 InterpreterError。"""
    allowed = {}
    for r in selection.readings:
        allowed[r.cite_id] = kb.citation(r.cite_id)["text"]
        for cid in r.context_ids:
            allowed[cid] = kb.citation(cid)["text"]

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _payload(question, cast, selection, verdict, allowed, kb)},
    ]
    last_errors = []
    for attempt in range(1, max_attempts + 1):
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
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            result = _parse_json(content)
        except (ValueError, json.JSONDecodeError) as e:
            last_errors = [f"JSON 解析失败: {e}"]
        else:
            last_errors = validate(result, allowed)
            if not last_errors:
                return result, attempt
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content":
                         "你的输出未通过校验，问题如下，请改正后重新输出完整 JSON：\n- "
                         + "\n- ".join(last_errors)})
    raise InterpreterError("解读三次未通过引文校验，已拒绝输出", last_errors)
