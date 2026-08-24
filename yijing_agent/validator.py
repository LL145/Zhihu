"""引文校验器：LLM 输出展示前的最后一道确定性闸门。

- 每条引文去标点后须逐字包含于其所标 cite_id 的原文之中；
- 占断（judgment）必须以 [cite_id] 标注所据——无据不断；
- 占断所据须含卦爻经传之文（王弼注、说卦取象不得单独立断）；
- 解读中方括号标注的 cite_id 须属于本次给定的文本集合；
- 必填字段齐全。任何一条不过即拒绝本次输出。
"""

import re

_CJK = re.compile(r"[^㐀-鿿]")
_CITE_MARK = re.compile(r"\[([a-z]+:[0-9]+(?::[a-z0-9]+)*)\]")

REQUIRED_FIELDS = ("translation", "judgment", "interpretation", "advice",
                   "quotes")


def normalize(text: str) -> str:
    """仅保留汉字，去除标点、引号、空白——「逐字」以此为准。"""
    return _CJK.sub("", text)


def _check_quotes(quotes, allowed, errors):
    for i, q in enumerate(quotes):
        if not isinstance(q, dict) or "text" not in q or "cite_id" not in q:
            errors.append(f"quotes[{i}] 须含 text 与 cite_id")
            continue
        cid = q["cite_id"]
        if cid not in allowed:
            errors.append(f"quotes[{i}] 的 cite_id 不在本次给定文本之内: {cid}")
            continue
        nq = normalize(q["text"])
        if not nq:
            errors.append(f"quotes[{i}] 引文为空")
        elif nq not in normalize(allowed[cid]):
            errors.append(f"quotes[{i}] 与 {cid} 原文不符（须逐字照抄）: {q['text']}")


def _check_cite_marks(text, allowed, errors, where):
    for cid in _CITE_MARK.findall(text):
        if cid not in allowed:
            errors.append(f"{where}中标注的 cite_id 不在本次给定文本之内: {cid}")


def validate(result: dict, allowed: dict) -> list:
    """allowed: {cite_id: 原文}。返回错误列表，空列表为通过。"""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in result or not result[f]:
            errors.append(f"缺少字段或字段为空: {f}")
    if errors:
        return errors

    if not isinstance(result["quotes"], list) or not result["quotes"]:
        return ["quotes 须为非空数组"]
    if not isinstance(result["advice"], list):
        return ["advice 须为数组"]

    _check_quotes(result["quotes"], allowed, errors)
    marks = _CITE_MARK.findall(result["judgment"])
    if not marks:
        errors.append("占断（judgment）必须以 [cite_id] 标注所据原文——无据不断")
    elif all(m.split(":")[0] in ("wangbi", "shuogua") for m in marks):
        errors.append("占断所据须含卦爻经传之文——王弼注与说卦取象不得单独立断")
    _check_cite_marks(result["judgment"], allowed, errors, "占断")
    _check_cite_marks(result["interpretation"], allowed, errors, "解读")
    return errors


def validate_followup(result: dict, allowed: dict) -> list:
    """追问回答的校验：answer 必填；quotes 须为数组但可为空（追问未必需引文）。"""
    errors = []
    if not isinstance(result.get("answer"), str) or not result.get("answer"):
        errors.append("缺少字段或字段为空: answer")
    if not isinstance(result.get("quotes"), list):
        errors.append("quotes 须为数组（可为空数组）")
    if errors:
        return errors

    _check_quotes(result["quotes"], allowed, errors)
    _check_cite_marks(result["answer"], allowed, errors, "回答")
    return errors
